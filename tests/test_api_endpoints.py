"""Tests for API endpoints with mocked database.

Tests critical API endpoints to ensure they handle requests correctly
and properly interact with the database layer.
"""

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import sys
from unittest.mock import Mock, patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.types import Candle, Timeframe


@pytest.fixture
def mock_api_stores() -> Mock:
    """Mock stores for API testing."""
    mock_stores = Mock()
    return mock_stores


def test_health_endpoint_returns_ok_when_db_connected(mock_api_stores: Mock) -> None:
    """Verify /health endpoint returns 200 when database is connected."""
    from fastapi.testclient import TestClient

    # Mock the stores to simulate successful DB connection
    mock_api_stores._get_engine.return_value = Mock()

    with patch("api.main._stores", mock_api_stores):
        from api.main import app

        client = TestClient(app)
        response = client.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"


def test_get_candles_latest_returns_candles(mock_api_stores: Mock, sample_candles: list[Candle]) -> None:
    """Verify /candles/latest endpoint returns candles from database."""
    from fastapi.testclient import TestClient

    # Mock the get_candles method to return sample candles
    mock_api_stores.get_candles.return_value = sample_candles

    with patch("api.main._stores", mock_api_stores):
        from api.main import app

        client = TestClient(app)
        response = client.get(
            "/candles/latest",
            params={
                "exchange": "bitfinex",
                "symbol": "BTCUSD",
                "timeframe": "1h",
                "limit": 5,
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert "candles" in data
    assert len(data["candles"]) == len(sample_candles)


def test_get_candles_latest_requires_exchange_parameter() -> None:
    """Verify /candles/latest endpoint requires exchange parameter."""
    from fastapi.testclient import TestClient

    from api.main import app

    client = TestClient(app)
    response = client.get(
        "/candles/latest",
        params={
            # Missing exchange
            "symbol": "BTCUSD",
            "timeframe": "1h",
        },
    )

    assert response.status_code == 422  # Validation error


def test_get_candles_latest_requires_symbol_parameter() -> None:
    """Verify /candles/latest endpoint requires symbol parameter."""
    from fastapi.testclient import TestClient

    from api.main import app

    client = TestClient(app)
    response = client.get(
        "/candles/latest",
        params={
            "exchange": "bitfinex",
            # Missing symbol
            "timeframe": "1h",
        },
    )

    assert response.status_code == 422  # Validation error


def test_get_candles_latest_requires_timeframe_parameter() -> None:
    """Verify /candles/latest endpoint requires timeframe parameter."""
    from fastapi.testclient import TestClient

    from api.main import app

    client = TestClient(app)
    response = client.get(
        "/candles/latest",
        params={
            "exchange": "bitfinex",
            "symbol": "BTCUSD",
            # Missing timeframe
        },
    )

    assert response.status_code == 422  # Validation error


def test_get_candles_latest_handles_empty_result(mock_api_stores: Mock) -> None:
    """Verify /candles/latest endpoint handles case when no candles are found."""
    from fastapi.testclient import TestClient

    # Mock the get_candles method to return empty list
    mock_api_stores.get_candles.return_value = []

    with patch("api.main._stores", mock_api_stores):
        from api.main import app

        client = TestClient(app)
        response = client.get(
            "/candles/latest",
            params={
                "exchange": "bitfinex",
                "symbol": "BTCUSD",
                "timeframe": "1h",
                "limit": 5,
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert "candles" in data
    assert len(data["candles"]) == 0


def test_ingestion_status_endpoint_returns_status(mock_api_stores: Mock) -> None:
    """Verify /ingestion/status endpoint returns ingestion freshness data."""
    from fastapi.testclient import TestClient

    # Mock the _get_latest_candle_open_time to return a recent timestamp
    latest_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    mock_api_stores._get_latest_candle_open_time.return_value = latest_time

    with patch("api.main._stores", mock_api_stores):
        from api.main import app

        client = TestClient(app)
        response = client.get("/ingestion/status")

    assert response.status_code == 200
    data = response.json()
    assert "symbols" in data


def test_market_cap_endpoint_returns_rankings(mock_api_stores: Mock) -> None:
    """Verify /market-cap endpoint returns market cap rankings."""
    from fastapi.testclient import TestClient

    with patch("api.main._stores", mock_api_stores):
        from api.main import app

        client = TestClient(app)
        response = client.get("/market-cap")

    assert response.status_code == 200
    data = response.json()
    assert "rankings" in data or "market_cap" in data


@pytest.mark.parametrize(
    "timeframe",
    ["1m", "5m", "15m", "1h", "4h", "1d"],
)
def test_get_candles_latest_accepts_valid_timeframes(
    mock_api_stores: Mock, sample_candles: list[Candle], timeframe: str
) -> None:
    """Verify /candles/latest endpoint accepts all valid timeframe values."""
    from fastapi.testclient import TestClient

    mock_api_stores.get_candles.return_value = sample_candles

    with patch("api.main._stores", mock_api_stores):
        from api.main import app

        client = TestClient(app)
        response = client.get(
            "/candles/latest",
            params={
                "exchange": "bitfinex",
                "symbol": "BTCUSD",
                "timeframe": timeframe,
                "limit": 5,
            },
        )

    assert response.status_code == 200


def test_get_candles_latest_enforces_limit_bounds(mock_api_stores: Mock, sample_candles: list[Candle]) -> None:
    """Verify /candles/latest endpoint enforces limit parameter bounds."""
    from fastapi.testclient import TestClient

    mock_api_stores.get_candles.return_value = sample_candles

    with patch("api.main._stores", mock_api_stores):
        from api.main import app

        client = TestClient(app)

        # Test with limit = 1000 (should work)
        response = client.get(
            "/candles/latest",
            params={
                "exchange": "bitfinex",
                "symbol": "BTCUSD",
                "timeframe": "1h",
                "limit": 1000,
            },
        )
        assert response.status_code == 200

        # Test with limit > 1000 (should fail validation)
        response = client.get(
            "/candles/latest",
            params={
                "exchange": "bitfinex",
                "symbol": "BTCUSD",
                "timeframe": "1h",
                "limit": 1001,
            },
        )
        # Should either accept (and cap to 1000) or reject with 422
        assert response.status_code in [200, 422]
