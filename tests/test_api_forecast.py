"""API contract tests for the /forecast endpoints (service mocked, no torch).

Follows the conventions of the other tests/test_api_*.py modules: import the
FastAPI app, patch the route-module singletons/data access and assert on the
HTTP contract.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.forecasting.service import MODEL_ID_DEFAULT, TimesFMConfig
from core.forecasting.cache import get_forecast_cache


# ----------------------------------------------------------------------
# Fixtures and fakes
# ----------------------------------------------------------------------


class _FakeTimesFMService:
    """Deterministic service stand-in: counts calls, returns fixed bands."""

    def __init__(self) -> None:
        self.config = TimesFMConfig(
            model_id=MODEL_ID_DEFAULT,
            device="cpu",
            max_context=1024,
            max_horizon=256,
        )
        self.device = "cpu"
        self.forecast_calls = 0
        self.last_series: list[np.ndarray] = []

    def load(self) -> None:
        """No-op: the fake is always 'loaded'."""

    def status(self) -> dict[str, Any]:
        return {
            "loaded": True,
            "model_id": self.config.model_id,
            "device": self.device,
            "ready": True,
        }

    def forecast(self, series: list[np.ndarray], horizon: int) -> list[list[tuple[float, float, float]]]:
        self.forecast_calls += 1
        self.last_series = list(series)
        batch = []
        for index, values in enumerate(series):
            offset = 1000.0 * (index + 1) + float(values[-1])
            batch.append(
                [
                    (
                        offset + step - 5.0,  # p10
                        offset + step,  # p50
                        offset + step + 5.0,  # p90
                    )
                    for step in range(int(horizon))
                ]
            )
        return batch


_BASE_OPEN_MS = 1_704_067_200_000  # 2024-01-01T00:00:00Z


def _fake_fetch_closes(n_candles: int, price: float = 50_000.0):
    """Build a replacement for api.routes.forecast._fetch_closes."""

    def _fetch(exchange: str, symbol: str, timeframe: str, limit: int):
        opens = [_BASE_OPEN_MS + i * 3_600_000 for i in range(n_candles)]
        closes = np.full(n_candles, price, dtype=np.float32)
        return opens, closes

    return _fetch


@pytest.fixture
def fake_service():
    """Route module wired to the fake service and fake candle data."""
    import api.routes.forecast as forecast_routes

    original_get_service = forecast_routes._get_service
    original_fetch_closes = forecast_routes._fetch_closes
    service = _FakeTimesFMService()
    forecast_routes._get_service = lambda: service  # type: ignore[method-assign]
    forecast_routes._fetch_closes = _fake_fetch_closes(100)  # type: ignore[assignment]
    get_forecast_cache().clear()
    yield service
    forecast_routes._get_service = original_get_service  # type: ignore[method-assign]
    forecast_routes._fetch_closes = original_fetch_closes  # type: ignore[assignment]
    forecast_routes._service = None  # restore lazy init for other tests
    get_forecast_cache().clear()


@pytest.fixture
def client():
    """TestClient without lifespan (mirrors the conftest.api_client fixture)."""
    from fastapi.testclient import TestClient

    from api.main import app

    return TestClient(app)


# ----------------------------------------------------------------------
# Route registration
# ----------------------------------------------------------------------


def test_forecast_routes_registered(client):
    """All three forecast endpoints are mounted on the app."""
    from api.main import app

    paths = [route.path for route in app.routes]
    assert "/forecast" in paths
    assert "/forecast/batch" in paths
    assert "/forecast/status" in paths


# ----------------------------------------------------------------------
# POST /forecast
# ----------------------------------------------------------------------


def test_forecast_success_shape(client, fake_service):
    """Valid request returns the documented response contract."""
    response = client.post(
        "/forecast",
        json={"symbol": "BTCUSD", "timeframe": "1h", "horizon": 24},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["symbol"] == "BTCUSD"
    assert data["timeframe"] == "1h"
    assert data["horizon"] == 24
    assert data["model_id"] == MODEL_ID_DEFAULT
    assert data["cache"] == "miss"
    assert isinstance(data["latency_ms"], float)
    assert data["context_len"] == 100
    assert len(data["points"]) == 24

    first = data["points"][0]
    assert set(first.keys()) == {"ts", "p10", "p50", "p90"}
    assert first["p10"] <= first["p50"] <= first["p90"]
    # 100 candles: the last closed candle opens at base + 99h, so the first
    # forecast point is the candle opening one hour later at base + 100h.
    assert first["ts"].startswith("2024-01-05T04:00:00")
    timestamps = [p["ts"] for p in data["points"]]
    assert timestamps == sorted(timestamps)


def test_forecast_cache_hit_on_second_call(client, fake_service):
    """The second identical request within the same candle is a cache hit."""
    payload = {"symbol": "BTCUSD", "timeframe": "1h", "horizon": 24}

    first = client.post("/forecast", json=payload)
    second = client.post("/forecast", json=payload)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["cache"] == "miss"
    assert second.json()["cache"] == "hit"
    # The model ran exactly once; the hit serves the identical points.
    assert fake_service.forecast_calls == 1
    assert second.json()["points"] == first.json()["points"]


def test_forecast_rejects_insufficient_history(client, fake_service):
    """Fewer than 32 closed candles is a 422 with a clear error."""
    import api.routes.forecast as forecast_routes

    forecast_routes._fetch_closes = _fake_fetch_closes(20)  # type: ignore[assignment]

    response = client.post(
        "/forecast",
        json={"symbol": "BTCUSD", "timeframe": "1h", "horizon": 24},
    )

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["error"] == "insufficient_data"
    assert detail["available"] == 20
    assert detail["required"] == 32


def test_forecast_rejects_unknown_series(client, fake_service):
    """No candles at all surfaces the 404 from the data access layer."""
    import api.routes.forecast as forecast_routes
    from fastapi import HTTPException

    def _raise(exchange: str, symbol: str, timeframe: str, limit: int):
        raise HTTPException(
            status_code=404,
            detail={"error": "no_data", "message": "No candles found"},
        )

    forecast_routes._fetch_closes = _raise  # type: ignore[assignment]

    response = client.post(
        "/forecast",
        json={"symbol": "FOOUSD", "timeframe": "1h", "horizon": 24},
    )

    assert response.status_code == 404
    assert response.json()["detail"]["error"] == "no_data"


def test_forecast_rejects_out_of_range_horizon(client, fake_service):
    """A horizon above TIMESFM_MAX_HORIZON is a 422 before any model call."""
    response = client.post(
        "/forecast",
        json={"symbol": "BTCUSD", "timeframe": "1h", "horizon": 999},
    )

    assert response.status_code == 422
    assert response.json()["detail"]["error"] == "horizon_out_of_range"
    assert fake_service.forecast_calls == 0


# ----------------------------------------------------------------------
# POST /forecast/batch
# ----------------------------------------------------------------------


def test_forecast_batch_single_model_call(client, fake_service):
    """All symbols are forecast with ONE batched model.forecast call."""
    response = client.post(
        "/forecast/batch",
        json={"symbols": ["BTCUSD", "ETHUSD"], "timeframe": "1h", "horizon": 12},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["timeframe"] == "1h"
    assert data["horizon"] == 12
    assert data["errors"] == {}
    assert set(data["results"].keys()) == {"BTCUSD", "ETHUSD"}
    assert fake_service.forecast_calls == 1
    assert len(fake_service.last_series) == 2
    for symbol, payload in data["results"].items():
        assert payload["symbol"] == symbol
        assert payload["cache"] == "miss"
        assert len(payload["points"]) == 12


def test_forecast_batch_partial_errors(client, fake_service):
    """Symbols without enough history land in `errors`, the rest still forecast."""
    import api.routes.forecast as forecast_routes

    def _fetch(exchange: str, symbol: str, timeframe: str, limit: int):
        if symbol == "BADUSD":
            return _fake_fetch_closes(10)(exchange, symbol, timeframe, limit)
        return _fake_fetch_closes(100)(exchange, symbol, timeframe, limit)

    forecast_routes._fetch_closes = _fetch  # type: ignore[assignment]

    response = client.post(
        "/forecast/batch",
        json={"symbols": ["BTCUSD", "BADUSD"], "timeframe": "1h", "horizon": 6},
    )

    assert response.status_code == 200
    data = response.json()
    assert set(data["results"].keys()) == {"BTCUSD"}
    assert set(data["errors"].keys()) == {"BADUSD"}
    assert data["errors"]["BADUSD"]["error"] == "insufficient_data"
    assert fake_service.forecast_calls == 1


# ----------------------------------------------------------------------
# GET /forecast/status
# ----------------------------------------------------------------------


def test_forecast_status_shape(client, fake_service):
    """Status reports the loaded model identity and readiness."""
    response = client.get("/forecast/status")

    assert response.status_code == 200
    data = response.json()
    assert set(data.keys()) == {"loaded", "model_id", "device", "ready"}
    assert data["loaded"] is True
    assert data["ready"] is True
    assert data["model_id"] == MODEL_ID_DEFAULT
    assert data["device"] == "cpu"
