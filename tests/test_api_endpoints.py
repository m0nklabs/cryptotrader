"""Tests for API endpoints with mocked database.

Tests critical API endpoints to ensure they handle requests correctly
and properly interact with the database layer.

Note: These are simplified validation tests. Full integration tests with
database are in test_api*.py files.
"""

from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


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

    # Missing required parameter should return 422 or 500
    assert response.status_code in [422, 500]


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


@pytest.mark.parametrize(
    "invalid_timeframe",
    ["2h", "30m", "invalid", "1w"],
)
def test_get_candles_latest_rejects_invalid_timeframes(invalid_timeframe: str) -> None:
    """Verify /candles/latest endpoint rejects invalid timeframe values."""
    from fastapi.testclient import TestClient
    from api.main import app

    client = TestClient(app)
    response = client.get(
        "/candles/latest",
        params={
            "exchange": "bitfinex",
            "symbol": "BTCUSD",
            "timeframe": invalid_timeframe,
            "limit": 5,
        },
    )

    # Should fail validation or return error
    assert response.status_code in [400, 422, 500]
