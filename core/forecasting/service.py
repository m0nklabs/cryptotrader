"""TimesFM forecast service (lazy, thread-safe model wrapper).

Supports two backends behind one interface:

- ``timesfm2_5``: the ``timesfm`` module's ``TimesFM_2p5_200M_torch`` PyTorch
  stack, loading ``google/timesfm-2.5-200m-pytorch`` (Apache-2.0 weights).
- ``timesfm3`` (default): the ``timesfm3`` module's ``TimesFM3Evaluator``
  stack, loading ``google/timesfm-3.0-pytorch``.

LICENSE NOTE: ``google/timesfm-3.0-pytorch`` weights carry
``timesfm-non-commercial-license-v1.0`` ("commercial or production use of the
default pretrained weights is not permitted") — selected deliberately by the
operator on 2026-09-06 for this personal, self-hosted deployment. TimesFM 2.5
(Apache-2.0) remains selectable via ``TIMESFM_MODEL_ID`` / ``TIMESFM_BACKEND``.

Backend selection: ``TIMESFM_BACKEND`` = ``auto`` | ``timesfm2_5`` |
``timesfm3`` (default ``auto``). With ``auto``, the backend is derived from
``TIMESFM_MODEL_ID`` (an id containing ``timesfm-3`` selects 3.0); an explicit
value always wins.

Design notes:
- ``timesfm``/``timesfm3``/``torch`` are imported lazily inside
  :meth:`TimesFMService.load` so importing this module (and the whole API app)
  never pulls torch.
- 2.5: ``from_pretrained(..., torch_compile=False)`` is mandatory: upstream
  issue google-research/timesfm#328 reports flat-line predictions when
  ``torch_compile=True`` (which is also the class default), so it is never
  enabled here. The 3.0 stack has no compile step (plain eval-mode torch).
- 3.0: one ``TimesFM3Evaluator.predict_batch`` call per :meth:`forecast`
  (it is the batched API) with ``return_quantiles=True``,
  ``use_symmetric_averaging=False`` and ``make_positive=True`` (closes are
  non-negative; the clamp only engages when the input context is too).
- Inference device follows ``TIMESFM_DEVICE`` (``auto`` | ``cpu`` | ``cuda``).
  With ``auto``, CUDA is preferred when available; if loading/inference on
  CUDA fails (e.g. out of VRAM on a shared GPU) the service fails open by
  retrying once on CPU.
"""

from __future__ import annotations

import logging
import os
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

# Defaults (overridable through environment variables, see load_config_from_env).
# The 3.0 model id is the default (operator decision, 2026-09-06); it carries a
# non-commercial weight license — see the LICENSE NOTE in the module docstring.
MODEL_ID_DEFAULT_2_5 = "google/timesfm-2.5-200m-pytorch"
MODEL_ID_DEFAULT_3_0 = "google/timesfm-3.0-pytorch"
MODEL_ID_DEFAULT = MODEL_ID_DEFAULT_3_0
MAX_CONTEXT_DEFAULT = 1024
MAX_HORIZON_DEFAULT = 256

# Backend identifiers (TIMESFM_BACKEND). "auto" derives the backend from the
# model id (an id containing "timesfm-3" -> timesfm3, else timesfm2_5); an
# explicit value always wins.
BACKEND_AUTO = "auto"
BACKEND_TIMESFM2_5 = "timesfm2_5"
BACKEND_TIMESFM3 = "timesfm3"
_VALID_BACKENDS = (BACKEND_AUTO, BACKEND_TIMESFM2_5, BACKEND_TIMESFM3)

# Model-id substring that selects the 3.0 backend under "auto".
_BACKEND_3_0_MODEL_ID_MARKER = "timesfm-3"

# timesfm3 per-core batch size (series per forward pass inside predict_batch;
# it chunks automatically for larger batches). Value from the upstream README
# example; only matters when many symbols are forecast in one batch.
PER_CORE_BATCH_SIZE_3_0 = 32

# The model needs a minimum history length to produce meaningful forecasts
# (upstream guidance: context must be >= 32 data points).
MIN_CONTEXT_POINTS = 32

# Both backends need ~2 GB of free VRAM (200M-parameter checkpoints). On
# shared GPUs with less headroom, "auto" goes straight to CPU instead of
# OOM-thrashing CUDA.
MIN_FREE_VRAM_BYTES = 2 * 1024**3

# Seconds a failed model load is remembered before the next load attempt.
LOAD_FAILURE_COOLDOWN_SECONDS = 30.0

# Layout of the last axis of TimesFM 2.5's quantile_forecast
# (batch, horizon, 10): index 0 = mean, 1 = q10, ..., 5 = median (= point
# forecast), ..., 9 = q90.
QUANTILE_MEAN_IDX = 0
QUANTILE_P10_IDX = 1
QUANTILE_P50_IDX = 5
QUANTILE_P90_IDX = 9

# Layout of the last axis of TimesFM 3.0's ForecastOutput.quantiles
# (horizon, 9): quantiles 0.1..0.9 sorted ascending, so 0 = q10, 4 = median
# (= point forecast) and 8 = q90. Confirmed from the installed timesfm3
# source (median_quantile_index=4) and the checkpoint's config.json.
QUANTILE_P10_IDX_3_0 = 0
QUANTILE_P50_IDX_3_0 = 4
QUANTILE_P90_IDX_3_0 = 8

_VALID_DEVICES = ("auto", "cpu", "cuda")


def resolve_backend(model_id: str, backend: str) -> str:
    """Resolve the requested backend to a concrete backend identifier.

    Args:
        model_id: Hugging Face model id (used for ``auto`` detection).
        backend: Requested backend: ``auto``, ``timesfm2_5`` or ``timesfm3``.

    Returns:
        ``BACKEND_TIMESFM3`` or ``BACKEND_TIMESFM2_5``.

    Raises:
        ValueError: If ``backend`` is not one of auto/timesfm2_5/timesfm3.
    """
    if backend == BACKEND_TIMESFM3:
        return BACKEND_TIMESFM3
    if backend == BACKEND_TIMESFM2_5:
        return BACKEND_TIMESFM2_5
    if backend == BACKEND_AUTO:
        marker = _BACKEND_3_0_MODEL_ID_MARKER
        return BACKEND_TIMESFM3 if marker in model_id.lower() else BACKEND_TIMESFM2_5
    raise ValueError(f"TIMESFM_BACKEND must be one of {_VALID_BACKENDS}, got {backend!r}")


@dataclass(frozen=True)
class TimesFMConfig:
    """Immutable service configuration (parsed from environment variables).

    Attributes:
        model_id: Hugging Face model id.
        backend: Requested backend (``auto`` | ``timesfm2_5`` | ``timesfm3``);
            ``auto`` is resolved against ``model_id`` by the service.
        device: ``auto`` | ``cpu`` | ``cuda``.
        max_context: Maximum context length in candles (data-side limit and,
            for 2.5, ``ForecastConfig.max_context``; timesfm rounds it up
            internally to a multiple of the patch size).
        max_horizon: Maximum forecast horizon in steps (also
            ``ForecastConfig.max_horizon`` for 2.5; timesfm rounds it up
            internally to a multiple of the output patch size).
    """

    model_id: str = MODEL_ID_DEFAULT
    backend: str = BACKEND_AUTO
    device: str = "auto"
    max_context: int = MAX_CONTEXT_DEFAULT
    max_horizon: int = MAX_HORIZON_DEFAULT


def load_config_from_env(env: dict[str, str] | None = None) -> TimesFMConfig:
    """Build a :class:`TimesFMConfig` from environment variables.

    Args:
        env: Environment mapping to read; defaults to ``os.environ``.

    Returns:
        Parsed configuration.

    Raises:
        ValueError: If ``TIMESFM_DEVICE`` is not one of auto/cpu/cuda, if
            ``TIMESFM_BACKEND`` is not one of auto/timesfm2_5/timesfm3 or if
            the numeric settings are not positive integers.
    """
    source = os.environ if env is None else env

    model_id = source.get("TIMESFM_MODEL_ID", MODEL_ID_DEFAULT).strip() or MODEL_ID_DEFAULT

    backend = source.get("TIMESFM_BACKEND", BACKEND_AUTO).strip().lower() or BACKEND_AUTO
    if backend not in _VALID_BACKENDS:
        raise ValueError(f"TIMESFM_BACKEND must be one of {_VALID_BACKENDS}, got {backend!r}")

    device = source.get("TIMESFM_DEVICE", "auto").strip().lower() or "auto"
    if device not in _VALID_DEVICES:
        raise ValueError(f"TIMESFM_DEVICE must be one of {_VALID_DEVICES}, got {device!r}")

    def _positive_int(name: str, default: int) -> int:
        raw = source.get(name, "").strip()
        if not raw:
            return default
        try:
            value = int(raw)
        except ValueError as exc:
            raise ValueError(f"{name} must be an integer, got {raw!r}") from exc
        if value <= 0:
            raise ValueError(f"{name} must be a positive integer, got {value}")
        return value

    max_context = _positive_int("TIMESFM_MAX_CONTEXT", MAX_CONTEXT_DEFAULT)
    max_horizon = _positive_int("TIMESFM_MAX_HORIZON", MAX_HORIZON_DEFAULT)

    return TimesFMConfig(
        model_id=model_id,
        backend=backend,
        device=device,
        max_context=max_context,
        max_horizon=max_horizon,
    )


def extract_quantile_band(
    quantile_forecast: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Map a TimesFM 2.5 quantile array to the (p10, p50, p90) band.

    Args:
        quantile_forecast: Array of shape ``(batch, horizon, 10)`` as returned
            by ``model.forecast``. Index 0 is the mean, 1 is q10, 5 is the
            median (equal to the point forecast) and 9 is q90.

    Returns:
        Tuple ``(p10, p50, p90)`` arrays of shape ``(batch, horizon)``.
    """
    band = np.asarray(quantile_forecast)
    return band[..., QUANTILE_P10_IDX], band[..., QUANTILE_P50_IDX], band[..., QUANTILE_P90_IDX]


def extract_quantile_band_3_0(
    quantiles: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Map a TimesFM 3.0 quantile array to the (p10, p50, p90) band.

    Args:
        quantiles: Array of shape ``(horizon, 9)`` as returned by
            ``TimesFM3Evaluator.predict_batch(..., return_quantiles=True)``
            for a 1-D input series. The last axis holds the sorted quantiles
            0.1..0.9, so index 0 is q10, 4 the median and 8 q90. Any leading
            batch dimensions are also supported.

    Returns:
        Tuple ``(p10, p50, p90)`` arrays shaped like ``quantiles`` without its
        last axis.
    """
    band = np.asarray(quantiles)
    if band.shape[-1] != 9:
        raise ValueError(f"TimesFM 3.0 quantiles must have 9 columns (0.1..0.9), got shape {band.shape}")
    return (
        band[..., QUANTILE_P10_IDX_3_0],
        band[..., QUANTILE_P50_IDX_3_0],
        band[..., QUANTILE_P90_IDX_3_0],
    )


def _max_free_vram_bytes() -> int | None:
    """Return the largest free-VRAM amount across all GPUs, or ``None`` if unknown.

    Prefers ``nvidia-smi`` (a pure driver query that does not create a CUDA
    context); falls back to ``torch.cuda.mem_get_info`` when the binary is
    missing. Callers must treat ``None`` as "unknown", not as "no GPU".
    """
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=memory.free",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            timeout=5.0,
            check=True,
        )
        free_mib = [int(line) for line in result.stdout.decode().split()]
        if free_mib:
            return max(free_mib) * 1024 * 1024
    except (OSError, subprocess.SubprocessError, ValueError):
        pass

    try:
        import torch

        if torch.cuda.is_available():
            return max(torch.cuda.mem_get_info(device)[0] for device in range(torch.cuda.device_count()))
    except Exception:
        pass
    return None


class TimesFMService:
    """Lazy singleton wrapper around a TimesFM model (2.5 or 3.0 backend).

    The heavy work (model load + inference) is synchronous and must be run
    from a worker thread; the API layer does this through a ThreadPoolExecutor
    so the FastAPI event loop is never blocked.
    """

    def __init__(self, config: TimesFMConfig | None = None) -> None:
        """Create an unloaded service instance.

        Args:
            config: Service configuration; defaults to the environment-derived
                config (see :func:`load_config_from_env`).

        Raises:
            ValueError: If the configured backend value is invalid.
        """
        self._config = config if config is not None else load_config_from_env()
        self._backend = resolve_backend(self._config.model_id, self._config.backend)
        self._model: Any | None = None
        self._device: str | None = None
        self._load_lock = threading.Lock()
        self._load_failure: tuple[float, Exception] | None = None

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    @property
    def config(self) -> TimesFMConfig:
        """Active configuration."""
        return self._config

    @property
    def backend(self) -> str:
        """Resolved backend (``timesfm2_5`` or ``timesfm3``)."""
        return self._backend

    @property
    def loaded(self) -> bool:
        """Whether the model is loaded and ready for inference."""
        return self._model is not None

    @property
    def device(self) -> str | None:
        """Device the model was loaded on (``None`` while unloaded)."""
        return self._device

    def status(self) -> dict[str, Any]:
        """Status payload for ``GET /forecast/status``."""
        return {
            "loaded": self.loaded,
            "model_id": self._config.model_id,
            "device": self._device,
            "ready": self.loaded,
        }

    # ------------------------------------------------------------------
    # Model lifecycle
    # ------------------------------------------------------------------

    def load(self) -> None:
        """Load and compile the model (idempotent, thread-safe).

        Device policy: ``auto`` pre-checks the free VRAM of every GPU and goes
        straight to CPU when no GPU has enough headroom, so a shared/oversubscribed
        GPU is never OOM-thrashed. A failed load is remembered for
        :data:`LOAD_FAILURE_COOLDOWN_SECONDS` and re-raised cheaply in that
        window instead of retrying the heavy load per request.
        """
        if self._model is not None:
            return
        with self._load_lock:
            if self._model is not None:
                return
            if self._load_failure is not None:
                failed_at, error = self._load_failure
                if time.monotonic() - failed_at < LOAD_FAILURE_COOLDOWN_SECONDS:
                    raise RuntimeError("TimesFM model load failed recently; retry later") from error
                self._load_failure = None
            try:
                device = self._resolve_device()
                self._model, self._device = self._load_model(device)
            except Exception as exc:
                self._load_failure = (time.monotonic(), exc)
                raise

    def _resolve_device(self) -> str:
        """Resolve the requested device to an actual placement.

        Returns:
            ``"cuda"`` only when the request allows CUDA, CUDA is available and
            at least one GPU has enough free VRAM; otherwise ``"cpu"``.

        Raises:
            RuntimeError: When ``cuda`` was requested explicitly but is
                unavailable.
        """
        import torch

        if self._config.device == "cpu":
            return "cpu"
        if not torch.cuda.is_available():
            if self._config.device == "cuda":
                raise RuntimeError("TIMESFM_DEVICE=cuda but CUDA is not available")
            return "cpu"

        free_bytes = _max_free_vram_bytes()
        if free_bytes is not None and free_bytes < MIN_FREE_VRAM_BYTES:
            if self._config.device == "cuda":
                raise RuntimeError(
                    "TIMESFM_DEVICE=cuda but no GPU has enough free VRAM "
                    f"({free_bytes} bytes free, need {MIN_FREE_VRAM_BYTES})"
                )
            logger.info(
                "TimesFM: largest GPU has only %d free bytes (< %d); using CPU",
                free_bytes,
                MIN_FREE_VRAM_BYTES,
            )
            return "cpu"
        return "cuda"

    def _load_model(self, device_request: str) -> tuple[Any, str]:
        """Load the checkpoint for the resolved backend.

        Args:
            device_request: Resolved device request (``cpu`` or ``cuda``).

        Returns:
            Tuple (model, device-name) where device-name is ``"cpu"``/``"cuda"``.
        """
        if self._backend == BACKEND_TIMESFM3:
            return self._load_model_3_0(device_request)
        return self._load_model_2_5(device_request)

    def _load_model_2_5(self, device_request: str) -> tuple[Any, str]:
        """Import timesfm, load the 2.5 checkpoint and compile the decode path.

        Args:
            device_request: Resolved device request (``cpu`` or ``cuda``).

        Returns:
            Tuple (model, device-name) where device-name is ``"cpu"``/``"cuda"``.
        """
        import timesfm
        import torch

        use_cuda = device_request == "cuda"
        torch.set_float32_matmul_precision("high")

        logger.info("Loading TimesFM model %s on %s", self._config.model_id, device_request)
        # torch_compile=False is REQUIRED: torch_compile=True (the class default)
        # triggers upstream issue #328 (flat-line predictions).
        # When CPU is requested we hide CUDA for the duration of from_pretrained:
        # the underlying module hard-codes device placement from
        # torch.cuda.is_available() in its constructor and would otherwise move
        # the weights onto cuda:0 regardless of the caller's intent.
        original_is_available = torch.cuda.is_available
        if not use_cuda and original_is_available():
            torch.cuda.is_available = lambda: False  # type: ignore[method-assign]
        try:
            model = timesfm.TimesFM_2p5_200M_torch.from_pretrained(
                self._config.model_id,
                torch_compile=False,
            )
        finally:
            torch.cuda.is_available = original_is_available  # type: ignore[method-assign]

        model.compile(
            timesfm.ForecastConfig(
                max_context=self._config.max_context,
                max_horizon=self._config.max_horizon,
                normalize_inputs=True,
                use_continuous_quantile_head=True,
                force_flip_invariance=True,
                infer_is_positive=True,
                fix_quantile_crossing=True,
            )
        )
        logger.info("TimesFM model ready on %s", device_request)
        return model, device_request

    def _load_model_3_0(self, device_request: str) -> tuple[Any, str]:
        """Import timesfm3 and construct the 3.0 evaluator (no compile step).

        The evaluator manages normalization (CPM RevIN), quantile sorting
        (crossing fix) and device placement itself; ``ModelConfig.device`` is
        the resolved device request. Context/horizon caps stay data-side
        (the evaluator supports up to 15,360 context points internally).

        Args:
            device_request: Resolved device request (``cpu`` or ``cuda``).

        Returns:
            Tuple (evaluator, device-name) where device-name is
            ``"cpu"``/``"cuda"``.
        """
        import timesfm3

        logger.info("Loading TimesFM 3.0 model %s on %s", self._config.model_id, device_request)
        evaluator = timesfm3.TimesFM3Evaluator(
            timesfm3.ModelConfig(
                checkpoint_path=self._config.model_id,
                per_core_batch_size=PER_CORE_BATCH_SIZE_3_0,
                device=device_request,
            )
        )
        logger.info("TimesFM 3.0 model ready on %s", device_request)
        return evaluator, device_request

    def ensure_loaded(self) -> None:
        """Alias of :meth:`load` for status endpoints that trigger the load."""
        self.load()

    # ------------------------------------------------------------------
    # Inference
    # ------------------------------------------------------------------

    def forecast(
        self,
        series: list[np.ndarray],
        horizon: int,
    ) -> list[list[tuple[float, float, float]]]:
        """Forecast one batch of series with a single backend model call.

        One batched call per invocation regardless of backend: 2.5 uses
        ``model.forecast(horizon, inputs)``; 3.0 uses
        ``TimesFM3Evaluator.predict_batch`` (which chunks internally).

        Args:
            series: One 1-D array of historical closes per series (any numeric
                dtype; converted to ``np.float32``).
            horizon: Number of steps to forecast (1..max_horizon).

        Returns:
            One list per input series of ``(p10, p50, p90)`` tuples, one tuple
            per horizon step. Timestamps are assigned by the caller (route
            layer), which owns the candle clock.

        Raises:
            ValueError: On an empty batch, an out-of-range horizon or an empty
                series.
        """
        self.load()  # idempotent; guarantees inference always has a model
        if not series:
            raise ValueError("series must contain at least one array")
        if not 1 <= int(horizon) <= self._config.max_horizon:
            raise ValueError(f"horizon must be between 1 and {self._config.max_horizon}, got {horizon}")

        inputs = [np.asarray(s, dtype=np.float32) for s in series]
        for idx, values in enumerate(inputs):
            if values.size == 0:
                raise ValueError(f"series[{idx}] is empty")

        started = time.perf_counter()
        if self._backend == BACKEND_TIMESFM3:
            outputs = list(
                self._model.predict_batch(
                    contexts=inputs,
                    horizon=int(horizon),
                    return_quantiles=True,
                    use_symmetric_averaging=False,
                    # Closes are non-negative; the evaluator only clamps a
                    # series whose input context is non-negative as well.
                    make_positive=True,
                )
            )
            if len(outputs) != len(inputs):
                raise RuntimeError(f"TimesFM 3.0 returned {len(outputs)} outputs for {len(inputs)} inputs")
            per_series_bands = [extract_quantile_band_3_0(np.asarray(output.quantiles)) for output in outputs]
        else:
            _, quantile_forecast = self._model.forecast(
                horizon=int(horizon),
                inputs=inputs,
            )
            p10_all, p50_all, p90_all = extract_quantile_band(np.asarray(quantile_forecast))
            per_series_bands = [(p10_all[idx], p50_all[idx], p90_all[idx]) for idx in range(len(inputs))]
        latency_ms = (time.perf_counter() - started) * 1000.0
        logger.debug(
            "TimesFM forecast: backend=%s batch=%d horizon=%d latency_ms=%.1f",
            self._backend,
            len(inputs),
            horizon,
            latency_ms,
        )

        results: list[list[tuple[float, float, float]]] = []
        for p10, p50, p90 in per_series_bands:
            results.append(
                [
                    (
                        float(p10[step]),
                        float(p50[step]),
                        float(p90[step]),
                    )
                    for step in range(int(horizon))
                ]
            )
        return results
