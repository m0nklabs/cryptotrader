"""Tests for the TimesFM forecasting service (no torch required).

Covers:
- quantile-index extraction for both backends (2.5: p10=idx1, p50=idx5,
  p90=idx9; 3.0: p10=idx0, p50=idx4, p90=idx8),
- the full forecast path against stubbed models (dtype handling, batching,
  predict_batch kwargs for 3.0),
- backend selection (auto-detect from model id, explicit override, invalid),
- the forecast cache keyed on the last closed candle timestamp,
- environment-driven configuration,
- the on-demand lifecycle: unload(), idle watchdog unload after a TTL and the
  transparent reload of the first forecast after an unload.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.forecasting.cache import ForecastCache, get_forecast_cache
from core.forecasting.models import ForecastResult
from core.forecasting.service import (
    BACKEND_AUTO,
    BACKEND_TIMESFM2_5,
    BACKEND_TIMESFM3,
    MAX_CONTEXT_DEFAULT,
    MAX_HORIZON_DEFAULT,
    MIN_CONTEXT_POINTS,
    MODEL_ID_DEFAULT,
    MODEL_ID_DEFAULT_2_5,
    MODEL_ID_DEFAULT_3_0,
    QUANTILE_P10_IDX,
    QUANTILE_P10_IDX_3_0,
    QUANTILE_P50_IDX,
    QUANTILE_P50_IDX_3_0,
    QUANTILE_P90_IDX,
    QUANTILE_P90_IDX_3_0,
    TimesFMConfig,
    TimesFMService,
    extract_quantile_band,
    extract_quantile_band_3_0,
    load_config_from_env,
    resolve_backend,
)


# ----------------------------------------------------------------------
# Quantile index mapping
# ----------------------------------------------------------------------


def test_quantile_index_constants():
    """The quantile contract: 0=mean, 1=q10, 5=median, 9=q90."""
    assert QUANTILE_P10_IDX == 1
    assert QUANTILE_P50_IDX == 5
    assert QUANTILE_P90_IDX == 9
    assert MIN_CONTEXT_POINTS == 32


def test_extract_quantile_band_indices():
    """p10/p50/p90 map to quantile indices 1/5/9 of the last axis."""
    # Value at [..., i] encodes the quantile index for easy assertions.
    quantiles = np.arange(10, dtype=np.float64)[None, None, :].repeat(4, axis=1)
    p10, p50, p90 = extract_quantile_band(quantiles)
    assert p10.shape == (1, 4)
    assert np.all(p10 == QUANTILE_P10_IDX)
    assert np.all(p50 == QUANTILE_P50_IDX)
    assert np.all(p90 == QUANTILE_P90_IDX)


# ----------------------------------------------------------------------
# TimesFM 3.0 quantile index mapping
# ----------------------------------------------------------------------


def test_quantile_index_constants_3_0():
    """The 3.0 quantile contract: 9 sorted columns 0.1..0.9, median at 4."""
    assert QUANTILE_P10_IDX_3_0 == 0
    assert QUANTILE_P50_IDX_3_0 == 4
    assert QUANTILE_P90_IDX_3_0 == 8


def test_extract_quantile_band_3_0_indices():
    """p10/p50/p90 map to quantile indices 0/4/8 of the last axis."""
    # Value at [..., i] encodes the quantile index for easy assertions.
    quantiles = np.arange(9, dtype=np.float64)[None, :].repeat(4, axis=0)
    p10, p50, p90 = extract_quantile_band_3_0(quantiles)
    assert p10.shape == (4,)
    assert np.all(p10 == 0)
    assert np.all(p50 == 4)
    assert np.all(p90 == 8)


def test_extract_quantile_band_3_0_rejects_wrong_width():
    """A quantile array without 9 columns is rejected loudly."""
    with pytest.raises(ValueError, match="9 columns"):
        extract_quantile_band_3_0(np.zeros((4, 10)))


# ----------------------------------------------------------------------
# Forecast path against a stubbed model
# ----------------------------------------------------------------------


class _StubTimesFM:
    """Minimal stand-in for the compiled timesfm model."""

    def __init__(self, point: np.ndarray, quantiles: np.ndarray):
        self.calls: list[dict] = []
        self._point = point
        self._quantiles = quantiles

    def forecast(self, horizon: int, inputs: list[np.ndarray]):
        self.calls.append({"horizon": horizon, "inputs": inputs})
        return self._point, self._quantiles


def _make_service(backend: str = BACKEND_TIMESFM2_5) -> TimesFMService:
    """Service with a fixed config; the model is injected manually.

    Defaults to the 2.5 backend (matching the 2.5 stubs below); pass
    ``BACKEND_TIMESFM3`` for the 3.0 stubs.
    """
    return TimesFMService(
        config=TimesFMConfig(
            model_id=MODEL_ID_DEFAULT_2_5,
            backend=backend,
            device="cpu",
            max_context=1024,
            max_horizon=256,
        )
    )


def test_forecast_maps_quantiles_to_band():
    """forecast() returns (p10, p50, p90) per step, taken from indices 1/5/9."""
    horizon = 3
    point = np.array([[10.0, 11.0, 12.0]])
    quantiles = np.zeros((1, horizon, 10))
    quantiles[0, :, 1] = [9.0, 10.0, 11.0]  # p10
    quantiles[0, :, 5] = [10.0, 11.0, 12.0]  # p50 == point forecast
    quantiles[0, :, 9] = [11.0, 12.0, 13.0]  # p90

    service = _make_service()
    stub = _StubTimesFM(point, quantiles)
    service._model = stub  # noqa: SLF001  (bypass the lazy torch load)

    bands = service.forecast([np.arange(64)], horizon=horizon)

    assert len(bands) == 1
    assert bands[0] == [
        (9.0, 10.0, 11.0),
        (10.0, 11.0, 12.0),
        (11.0, 12.0, 13.0),
    ]
    # Exactly one batched model call with the requested horizon.
    assert len(stub.calls) == 1
    assert stub.calls[0]["horizon"] == horizon
    # Input series are converted to np.float32.
    assert stub.calls[0]["inputs"][0].dtype == np.float32


def test_forecast_batch_is_one_model_call():
    """Multiple series share a single model.forecast call."""
    horizon = 2
    point = np.zeros((3, horizon))
    quantiles = np.zeros((3, horizon, 10))
    service = _make_service()
    stub = _StubTimesFM(point, quantiles)
    service._model = stub  # noqa: SLF001

    series = [np.arange(64), np.arange(100), np.arange(32)]
    bands = service.forecast(series, horizon=horizon)

    assert len(bands) == 3
    assert len(stub.calls) == 1
    assert len(stub.calls[0]["inputs"]) == 3


def test_forecast_validates_horizon_and_series():
    """Invalid horizon / empty inputs raise ValueError before any model call."""
    service = _make_service()
    stub = _StubTimesFM(np.zeros((1, 2)), np.zeros((1, 2, 10)))
    service._model = stub  # noqa: SLF001

    with pytest.raises(ValueError):
        service.forecast([np.arange(64)], horizon=0)
    with pytest.raises(ValueError):
        service.forecast([np.arange(64)], horizon=257)
    with pytest.raises(ValueError):
        service.forecast([], horizon=2)
    with pytest.raises(ValueError):
        service.forecast([np.array([])], horizon=2)
    assert stub.calls == []


# ----------------------------------------------------------------------
# TimesFM 3.0 forecast path against a stubbed evaluator
# ----------------------------------------------------------------------


class _StubForecastOutput:
    """Minimal stand-in for ``timesfm3.ForecastOutput``."""

    def __init__(self, quantiles: np.ndarray):
        self.quantiles = quantiles


class _StubTimesFM3Evaluator:
    """Minimal stand-in for ``TimesFM3Evaluator.predict_batch``.

    Returns one ``(horizon, 9)`` quantile array per input series, in order.
    """

    def __init__(self, quantiles_per_series: list[np.ndarray]):
        self.calls: list[dict] = []
        self._quantiles = quantiles_per_series

    def predict_batch(
        self,
        contexts: list[np.ndarray],
        horizon: int,
        return_quantiles: bool = False,
        use_symmetric_averaging: bool = False,
        make_positive: bool = False,
        **kwargs,
    ):
        self.calls.append(
            {
                "contexts": contexts,
                "horizon": horizon,
                "return_quantiles": return_quantiles,
                "use_symmetric_averaging": use_symmetric_averaging,
                "make_positive": make_positive,
            }
        )
        return iter([_StubForecastOutput(q) for q in self._quantiles])


def _make_service_3_0() -> TimesFMService:
    """Service pinned to the 3.0 backend; the evaluator is injected manually."""
    return _make_service(backend=BACKEND_TIMESFM3)


def test_forecast_3_0_maps_quantiles_to_band():
    """forecast() on 3.0 returns (p10, p50, p90) per step from indices 0/4/8."""
    horizon = 3
    # Column i holds value 10 + i so the extracted band is unambiguous.
    quantiles = (10.0 + np.arange(9, dtype=np.float64))[None, :].repeat(horizon, axis=0)

    service = _make_service_3_0()
    stub = _StubTimesFM3Evaluator([quantiles])
    service._model = stub  # noqa: SLF001  (bypass the lazy torch load)

    bands = service.forecast([np.arange(64)], horizon=horizon)

    assert len(bands) == 1
    # p10 = col 0 (10.0), p50 = col 4 (14.0), p90 = col 8 (18.0).
    assert bands[0] == [
        (10.0, 14.0, 18.0),
        (10.0, 14.0, 18.0),
        (10.0, 14.0, 18.0),
    ]
    # Exactly one predict_batch call with the canonical kwargs.
    assert len(stub.calls) == 1
    assert stub.calls[0]["horizon"] == horizon
    assert stub.calls[0]["return_quantiles"] is True
    assert stub.calls[0]["use_symmetric_averaging"] is False
    assert stub.calls[0]["make_positive"] is True
    # Input series are converted to np.float32.
    assert stub.calls[0]["contexts"][0].dtype == np.float32


def test_forecast_3_0_batch_is_one_predict_batch_call():
    """Multiple series share a single predict_batch call, extracted per series."""
    horizon = 2
    base = (10.0 + np.arange(9, dtype=np.float64))[None, :].repeat(horizon, axis=0)
    shifted = base + 100.0
    service = _make_service_3_0()
    stub = _StubTimesFM3Evaluator([base, shifted, base + 200.0])
    service._model = stub  # noqa: SLF001

    series = [np.arange(64), np.arange(100), np.arange(32)]
    bands = service.forecast(series, horizon=horizon)

    assert len(bands) == 3
    assert len(stub.calls) == 1
    assert len(stub.calls[0]["contexts"]) == 3
    # Per-series extraction: each series' band comes from its own quantiles.
    assert bands[0][0] == (10.0, 14.0, 18.0)
    assert bands[1][0] == (110.0, 114.0, 118.0)
    assert bands[2][0] == (210.0, 214.0, 218.0)


def test_forecast_3_0_validates_horizon_and_series():
    """Validation runs before the 3.0 model call as well."""
    service = _make_service_3_0()
    stub = _StubTimesFM3Evaluator([np.zeros((2, 9))])
    service._model = stub  # noqa: SLF001

    with pytest.raises(ValueError):
        service.forecast([np.arange(64)], horizon=257)
    with pytest.raises(ValueError):
        service.forecast([], horizon=2)
    assert stub.calls == []


# ----------------------------------------------------------------------
# Cache behaviour
# ----------------------------------------------------------------------


def _make_result(symbol: str = "BTCUSD") -> ForecastResult:
    return ForecastResult(
        symbol=symbol,
        timeframe="1h",
        horizon=24,
        generated_at="2024-01-01T00:00:00+00:00",
        model_id=MODEL_ID_DEFAULT,
        context_len=100,
        points=[],
        meta={"device": "cpu", "cache": "miss", "latency_ms": 1.0},
    )


def test_cache_roundtrip():
    """A stored result is returned for the exact same key."""
    cache = ForecastCache(ttl_seconds=60.0)
    result = _make_result()
    cache.set("BTCUSD", "1h", 24, 1_700_000_000_000, result)
    assert cache.get("BTCUSD", "1h", 24, 1_700_000_000_000) is result


def test_cache_invalidated_by_new_candle():
    """A new last-closed-candle timestamp changes the key (cache miss)."""
    cache = ForecastCache(ttl_seconds=60.0)
    result = _make_result()
    cache.set("BTCUSD", "1h", 24, 1_700_000_000_000, result)

    assert cache.get("BTCUSD", "1h", 24, 1_700_000_000_000) is result
    # Next candle opens an hour later -> different key -> miss.
    assert cache.get("BTCUSD", "1h", 24, 1_700_003_600_000) is None
    # Different horizon/timeframe are also different keys.
    assert cache.get("BTCUSD", "1h", 12, 1_700_000_000_000) is None
    assert cache.get("BTCUSD", "5m", 24, 1_700_000_000_000) is None


def test_cache_symbol_normalization():
    """Keys are case-insensitive on the symbol."""
    cache = ForecastCache(ttl_seconds=60.0)
    result = _make_result()
    cache.set("btcusd", "1h", 24, 1_700_000_000_000, result)
    assert cache.get("BTCUSD", "1h", 24, 1_700_000_000_000) is result


def test_cache_ttl_expiry(monkeypatch: pytest.MonkeyPatch):
    """Entries older than the TTL are evicted on read."""
    cache = ForecastCache(ttl_seconds=60.0)
    result = _make_result()
    now = 1000.0
    monkeypatch.setattr("core.forecasting.cache.time.time", lambda: now)
    cache.set("BTCUSD", "1h", 24, 1_700_000_000_000, result)
    assert cache.get("BTCUSD", "1h", 24, 1_700_000_000_000) is result

    now += 61.0  # past the TTL
    assert cache.get("BTCUSD", "1h", 24, 1_700_000_000_000) is None
    assert len(cache) == 0


def test_get_forecast_cache_singleton():
    """The module-level cache is a process-wide singleton."""
    import core.forecasting.cache as cache_module

    original = cache_module._cache
    try:
        cache_module._cache = None
        first = get_forecast_cache()
        second = get_forecast_cache()
        assert first is second
    finally:
        cache_module._cache = original


# ----------------------------------------------------------------------
# Configuration from environment
# ----------------------------------------------------------------------


def test_config_defaults():
    """Sane defaults without any env vars set: 3.0 backend by default."""
    config = load_config_from_env(env={})
    assert config.model_id == MODEL_ID_DEFAULT == MODEL_ID_DEFAULT_3_0
    assert config.backend == "auto"
    assert config.device == "auto"
    assert config.max_context == MAX_CONTEXT_DEFAULT == 1024
    assert config.max_horizon == MAX_HORIZON_DEFAULT == 256


def test_config_from_env(monkeypatch: pytest.MonkeyPatch):
    """All knobs are read from the environment."""
    monkeypatch.setenv("TIMESFM_MODEL_ID", "google/timesfm-2.5-200m-pytorch")
    monkeypatch.setenv("TIMESFM_DEVICE", "cpu")
    monkeypatch.setenv("TIMESFM_MAX_CONTEXT", "512")
    monkeypatch.setenv("TIMESFM_MAX_HORIZON", "128")

    config = load_config_from_env()
    assert config.model_id == "google/timesfm-2.5-200m-pytorch"
    assert config.device == "cpu"
    assert config.max_context == 512
    assert config.max_horizon == 128


def test_config_rejects_invalid_values(monkeypatch: pytest.MonkeyPatch):
    """Invalid device / backend / numeric values raise a clear ValueError."""
    monkeypatch.setenv("TIMESFM_DEVICE", "tpu")
    with pytest.raises(ValueError, match="TIMESFM_DEVICE"):
        load_config_from_env()

    monkeypatch.setenv("TIMESFM_DEVICE", "cpu")
    monkeypatch.setenv("TIMESFM_MAX_CONTEXT", "abc")
    with pytest.raises(ValueError, match="TIMESFM_MAX_CONTEXT"):
        load_config_from_env()

    monkeypatch.setenv("TIMESFM_MAX_CONTEXT", "0")
    with pytest.raises(ValueError, match="positive"):
        load_config_from_env()


# ----------------------------------------------------------------------
# Backend selection
# ----------------------------------------------------------------------


def test_resolve_backend_auto_detects_from_model_id():
    """auto: an id containing 'timesfm-3' selects 3.0, anything else 2.5."""
    assert resolve_backend("google/timesfm-3.0-pytorch", "auto") == BACKEND_TIMESFM3
    assert resolve_backend("google/timesfm-3.0-pytorch", BACKEND_AUTO) == BACKEND_TIMESFM3
    assert resolve_backend("google/timesfm-2.5-200m-pytorch", "auto") == BACKEND_TIMESFM2_5


def test_resolve_backend_explicit_wins():
    """An explicit backend value overrides the model-id derivation."""
    assert resolve_backend("google/timesfm-2.5-200m-pytorch", BACKEND_TIMESFM3) == BACKEND_TIMESFM3
    assert resolve_backend("google/timesfm-3.0-pytorch", BACKEND_TIMESFM2_5) == BACKEND_TIMESFM2_5


def test_resolve_backend_rejects_invalid_value():
    """An unknown backend value raises ValueError."""
    with pytest.raises(ValueError, match="TIMESFM_BACKEND"):
        resolve_backend("google/timesfm-3.0-pytorch", "timesfm1")


def test_config_backend_from_env(monkeypatch: pytest.MonkeyPatch):
    """TIMESFM_BACKEND is parsed and validated."""
    monkeypatch.setenv("TIMESFM_BACKEND", "timesfm3")
    config = load_config_from_env()
    assert config.backend == "timesfm3"

    monkeypatch.setenv("TIMESFM_BACKEND", "TIMESFM2_5")  # case-insensitive
    assert load_config_from_env().backend == "timesfm2_5"

    monkeypatch.setenv("TIMESFM_BACKEND", "bogus")
    with pytest.raises(ValueError, match="TIMESFM_BACKEND"):
        load_config_from_env()


def test_service_resolves_backend_at_construction():
    """The service resolves auto against the model id up front."""
    default = TimesFMService(config=TimesFMConfig(model_id=MODEL_ID_DEFAULT_3_0))
    assert default.backend == BACKEND_TIMESFM3

    legacy = TimesFMService(config=TimesFMConfig(model_id=MODEL_ID_DEFAULT_2_5))
    assert legacy.backend == BACKEND_TIMESFM2_5

    forced = TimesFMService(config=TimesFMConfig(model_id=MODEL_ID_DEFAULT_2_5, backend=BACKEND_TIMESFM3))
    assert forced.backend == BACKEND_TIMESFM3

    with pytest.raises(ValueError, match="TIMESFM_BACKEND"):
        TimesFMService(config=TimesFMConfig(model_id=MODEL_ID_DEFAULT_3_0, backend="bogus"))


# ----------------------------------------------------------------------
# Device resolution (torch stubbed, no real torch import)
# ----------------------------------------------------------------------


class _FakeCuda:
    """Stub for the torch.cuda namespace."""

    def __init__(self, available: bool):
        self._available = available
        self.empty_cache_calls = 0

    def is_available(self) -> bool:
        return self._available

    def empty_cache(self) -> None:
        self.empty_cache_calls += 1


class _FakeTorch:
    """Stub for the torch module used by TimesFMService._resolve_device."""

    def __init__(self, available: bool):
        self.cuda = _FakeCuda(available)


def test_resolve_device_auto_falls_back_to_cpu_on_low_vram(monkeypatch: pytest.MonkeyPatch):
    """auto + visible CUDA but < 2 GB free VRAM -> CPU (no OOM attempts)."""
    import core.forecasting.service as service_module

    monkeypatch.setitem(sys.modules, "torch", _FakeTorch(available=True))
    monkeypatch.setattr(service_module, "_max_free_vram_bytes", lambda: 512 * 1024 * 1024)
    service = TimesFMService(config=TimesFMConfig(device="auto"))
    assert service._resolve_device() == "cpu"


def test_resolve_device_auto_uses_cuda_with_enough_vram(monkeypatch: pytest.MonkeyPatch):
    """auto + enough free VRAM -> CUDA."""
    import core.forecasting.service as service_module

    monkeypatch.setitem(sys.modules, "torch", _FakeTorch(available=True))
    monkeypatch.setattr(service_module, "_max_free_vram_bytes", lambda: 8 * 1024**3)
    service = TimesFMService(config=TimesFMConfig(device="auto"))
    assert service._resolve_device() == "cuda"


def test_resolve_device_auto_cpu_when_no_gpu(monkeypatch: pytest.MonkeyPatch):
    """auto + CUDA unavailable -> CPU."""
    monkeypatch.setitem(sys.modules, "torch", _FakeTorch(available=False))
    service = TimesFMService(config=TimesFMConfig(device="auto"))
    assert service._resolve_device() == "cpu"


def test_resolve_device_explicit_cpu(monkeypatch: pytest.MonkeyPatch):
    """cpu request stays on CPU even when CUDA is available."""
    monkeypatch.setitem(sys.modules, "torch", _FakeTorch(available=True))
    service = TimesFMService(config=TimesFMConfig(device="cpu"))
    assert service._resolve_device() == "cpu"


def test_resolve_device_explicit_cuda_unavailable_raises(monkeypatch: pytest.MonkeyPatch):
    """An explicit cuda request fails loudly when CUDA is unavailable."""
    monkeypatch.setitem(sys.modules, "torch", _FakeTorch(available=False))
    service = TimesFMService(config=TimesFMConfig(device="cuda"))
    with pytest.raises(RuntimeError, match="CUDA is not available"):
        service._resolve_device()


def test_resolve_device_explicit_cuda_low_vram_raises(monkeypatch: pytest.MonkeyPatch):
    """An explicit cuda request fails loudly when no GPU has headroom."""
    import core.forecasting.service as service_module

    monkeypatch.setitem(sys.modules, "torch", _FakeTorch(available=True))
    monkeypatch.setattr(service_module, "_max_free_vram_bytes", lambda: 100 * 1024 * 1024)
    service = TimesFMService(config=TimesFMConfig(device="cuda"))
    with pytest.raises(RuntimeError, match="free VRAM"):
        service._resolve_device()


# ----------------------------------------------------------------------
# On-demand lifecycle: unload + idle watchdog
# ----------------------------------------------------------------------


def _make_on_demand_service(idle_unload_seconds: float = 0.0) -> TimesFMService:
    """Service with a fixed 2.5 config and the given idle-unload TTL."""
    return TimesFMService(
        config=TimesFMConfig(
            model_id=MODEL_ID_DEFAULT_2_5,
            backend=BACKEND_TIMESFM2_5,
            device="cpu",
            max_context=1024,
            max_horizon=256,
            idle_unload_seconds=idle_unload_seconds,
        )
    )


def _patch_lazy_load(
    service: TimesFMService,
    stub: _StubTimesFM,
    loads: list[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Route the service's lazy load to a stub (no torch, no timesfm import)."""

    def _fake_load_model(device_request: str):
        loads.append(device_request)
        return stub, device_request

    monkeypatch.setattr(service, "_resolve_device", lambda: "cpu")
    monkeypatch.setattr(service, "_load_model", _fake_load_model)


def test_unload_frees_model_and_is_idempotent():
    """unload() drops model/device/failure/last-used state and is safe to repeat."""
    service = _make_on_demand_service()
    service._model = _StubTimesFM(np.zeros((1, 2)), np.zeros((1, 2, 10)))  # noqa: SLF001
    service._device = "cpu"  # noqa: SLF001
    service._load_failure = (time.monotonic(), RuntimeError("boom"))  # noqa: SLF001
    service._last_used_monotonic = time.monotonic()  # noqa: SLF001

    service.unload()

    assert not service.loaded
    assert service.device is None
    assert service._model is None  # noqa: SLF001
    assert service._load_failure is None  # noqa: SLF001
    assert service._last_used_monotonic is None  # noqa: SLF001
    status = service.status()
    assert status["loaded"] is False
    assert status["idle_seconds"] is None
    assert status["idle_unload_seconds"] == 0.0

    service.unload()  # idempotent: no error, state stays clean
    assert not service.loaded
    assert service._model is None  # noqa: SLF001


def test_forecast_refreshes_last_used():
    """A successful forecast stamps the last-use time used by the watchdog."""
    service = _make_on_demand_service()
    stub = _StubTimesFM(np.zeros((1, 2)), np.zeros((1, 2, 10)))
    service._model = stub  # noqa: SLF001  (bypass the lazy torch load)
    assert service._last_used_monotonic is None  # noqa: SLF001

    service.forecast([np.arange(64)], horizon=2)

    assert service._last_used_monotonic is not None  # noqa: SLF001
    assert service._last_used_monotonic <= time.monotonic()  # noqa: SLF001


def test_idle_watchdog_unloads_after_ttl(monkeypatch: pytest.MonkeyPatch):
    """A tiny TTL makes the watchdog drop the model without forecast traffic."""
    service = _make_on_demand_service(idle_unload_seconds=0.2)
    loads: list[str] = []
    stub = _StubTimesFM(np.zeros((1, 2)), np.zeros((1, 2, 10)))
    _patch_lazy_load(service, stub, loads, monkeypatch)

    service.load()
    assert service.loaded
    watchdog = service._idle_watchdog  # noqa: SLF001
    assert watchdog is not None
    assert watchdog.daemon is True
    assert watchdog.is_alive()

    # Poll interval is min(30 s, ttl / 4) = 50 ms: 0.6 s is ~12 polls, 3x TTL.
    time.sleep(0.6)

    assert not service.loaded
    assert service._model is None  # noqa: SLF001
    assert service._device is None  # noqa: SLF001
    assert service._last_used_monotonic is None  # noqa: SLF001
    assert service.status()["idle_seconds"] is None
    assert loads == ["cpu"]  # the watchdog unloads; it never reloads


def test_idle_watchdog_spares_recently_used_model(monkeypatch: pytest.MonkeyPatch):
    """The watchdog re-checks under the lock and spares a fresh model."""
    service = _make_on_demand_service(idle_unload_seconds=5.0)
    loads: list[str] = []
    stub = _StubTimesFM(np.zeros((1, 2)), np.zeros((1, 2, 10)))
    _patch_lazy_load(service, stub, loads, monkeypatch)

    service.load()
    assert service._unload_if_idle(5.0) is False  # noqa: SLF001
    assert service.loaded


def test_forecast_after_unload_reloads(monkeypatch: pytest.MonkeyPatch):
    """After an unload the next forecast transparently reloads the model."""
    horizon = 2
    point = np.zeros((1, horizon))
    quantiles = np.zeros((1, horizon, 10))
    service = _make_on_demand_service()
    stub = _StubTimesFM(point, quantiles)
    loads: list[str] = []
    _patch_lazy_load(service, stub, loads, monkeypatch)

    service.load()
    service.forecast([np.arange(64)], horizon=horizon)
    assert service.loaded
    assert len(loads) == 1

    service.unload()
    assert not service.loaded

    bands = service.forecast([np.arange(64)], horizon=horizon)
    assert service.loaded
    assert len(loads) == 2  # transparent reload through the lazy-load path
    assert len(bands) == 1
    assert len(stub.calls) == 2


def test_unload_releases_cuda_cache(monkeypatch: pytest.MonkeyPatch):
    """Unloading a CUDA model hands the cached blocks back to the driver."""

    fake_torch = _FakeTorch(available=True)
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    service = _make_on_demand_service()
    service._model = object()  # any loaded-model stand-in  # noqa: SLF001
    service._device = "cuda"  # noqa: SLF001

    service.unload()

    assert not service.loaded
    assert fake_torch.cuda.empty_cache_calls == 1


def test_unload_skips_cuda_cache_release_on_cpu(monkeypatch: pytest.MonkeyPatch):
    """A CPU model unload does not touch the CUDA cache path."""

    fake_torch = _FakeTorch(available=True)
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    service = _make_on_demand_service()
    service._model = object()  # noqa: SLF001
    service._device = "cpu"  # noqa: SLF001

    service.unload()

    assert not service.loaded
    assert fake_torch.cuda.empty_cache_calls == 0


def test_forecast_retries_load_when_unload_races(monkeypatch: pytest.MonkeyPatch):
    """An unload racing the load() fast path is absorbed by a reload, not a crash."""
    horizon = 2
    point = np.zeros((1, horizon))
    quantiles = np.zeros((1, horizon, 10))
    service = _make_on_demand_service()
    stub = _StubTimesFM(point, quantiles)
    loads: list[str] = []
    _patch_lazy_load(service, stub, loads, monkeypatch)
    service._model = stub  # noqa: SLF001  (pre-loaded: forecast() takes the fast path)

    real_load = service.load

    def racy_load() -> None:
        # First invocation: drop the model like a concurrent watchdog would;
        # later invocations delegate to the real lazy load.
        if service._model is not None:
            service.unload()
            return
        real_load()

    monkeypatch.setattr(service, "load", racy_load)

    bands = service.forecast([np.arange(64)], horizon=horizon)

    assert service.loaded
    assert loads == ["cpu"]  # the race triggered exactly one reload
    assert len(bands) == 1
    assert len(stub.calls) == 1


def test_idle_watchdog_not_started_when_disabled(monkeypatch: pytest.MonkeyPatch):
    """idle_unload_seconds=0 (the default) never spawns a watchdog thread."""
    service = _make_on_demand_service(idle_unload_seconds=0.0)
    loads: list[str] = []
    stub = _StubTimesFM(np.zeros((1, 2)), np.zeros((1, 2, 10)))
    _patch_lazy_load(service, stub, loads, monkeypatch)

    service.load()
    assert service.loaded
    assert service._idle_watchdog is None  # noqa: SLF001


def test_status_reports_idle_fields(monkeypatch: pytest.MonkeyPatch):
    """status() exposes idle_seconds (since last use) and idle_unload_seconds."""
    service = _make_on_demand_service(idle_unload_seconds=900.0)
    loads: list[str] = []
    stub = _StubTimesFM(np.zeros((1, 2)), np.zeros((1, 2, 10)))
    _patch_lazy_load(service, stub, loads, monkeypatch)

    status = service.status()  # unloaded
    assert status["idle_seconds"] is None
    assert status["idle_unload_seconds"] == 900.0

    service.load()
    status = service.status()
    assert status["loaded"] is True
    assert isinstance(status["idle_seconds"], float)
    assert status["idle_seconds"] < 1.0
    assert status["idle_unload_seconds"] == 900.0


def test_config_idle_unload_from_env(monkeypatch: pytest.MonkeyPatch):
    """TIMESFM_IDLE_UNLOAD parses seconds; 0 (default) disables the unload."""
    config = load_config_from_env(env={})
    assert config.idle_unload_seconds == 0.0

    monkeypatch.setenv("TIMESFM_IDLE_UNLOAD", "900")
    assert load_config_from_env().idle_unload_seconds == 900.0

    monkeypatch.setenv("TIMESFM_IDLE_UNLOAD", "0")
    assert load_config_from_env().idle_unload_seconds == 0.0

    monkeypatch.setenv("TIMESFM_IDLE_UNLOAD", "abc")
    with pytest.raises(ValueError, match="TIMESFM_IDLE_UNLOAD"):
        load_config_from_env()

    monkeypatch.setenv("TIMESFM_IDLE_UNLOAD", "-5")
    with pytest.raises(ValueError, match="TIMESFM_IDLE_UNLOAD"):
        load_config_from_env()
