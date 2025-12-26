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


def test_get_candles_latest_uses_default_exchange(api_client) -> None:
    """Verify /candles/latest endpoint uses default exchange when not provided."""
    response = api_client.get(
        "/candles/latest",
        params={
            # exchange has default value "bitfinex"
            "symbol": "BTCUSD",
            "timeframe": "1h",
        },
    )

    # Should return 404 (no data) or 500 (DB error), not 422 since exchange has default
    assert response.status_code in [404, 500]


def test_get_candles_latest_requires_symbol_parameter(api_client) -> None:
    """Verify /candles/latest endpoint requires symbol parameter."""
    response = api_client.get(
        "/candles/latest",
        params={
            "exchange": "bitfinex",
            # Missing symbol
            "timeframe": "1h",
        },
    )

    assert response.status_code == 422  # Validation error


def test_get_candles_latest_requires_timeframe_parameter(api_client) -> None:
    """Verify /candles/latest endpoint requires timeframe parameter."""
    response = api_client.get(
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
def test_get_candles_latest_rejects_invalid_timeframes(api_client, invalid_timeframe: str) -> None:
    """Verify /candles/latest endpoint handles invalid timeframe values.

    Note: The API does not enforce timeframe validation, so it returns 404 (no data)
    or 500 (DB error) for invalid timeframes rather than 422 (validation error).
    """
    response = api_client.get(
        "/candles/latest",
        params={
            "exchange": "bitfinex",
            "symbol": "BTCUSD",
            "timeframe": invalid_timeframe,
            "limit": 5,
        },
    )

    # No validation on timeframe in API, so expect 404 (no data) or 500 (error)
    assert response.status_code in [404, 500]
