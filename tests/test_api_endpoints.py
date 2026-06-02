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


def test_database_url_loads_from_runtime_env_file(tmp_path, monkeypatch) -> None:
    """Verify DATABASE_URL falls back to the configured runtime env file."""
    from api import main

    env_file = tmp_path / ".env"
    env_file.write_text("DATABASE_URL=postgresql://local:test@127.0.0.1:5432/cryptotrader\n")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("CRYPTOTRADER_ENV_FILE", str(env_file))

    assert main._get_database_url() == "postgresql://local:test@127.0.0.1:5432/cryptotrader"


def test_database_url_env_var_wins_over_runtime_env_file(tmp_path, monkeypatch) -> None:
    """Verify an explicit DATABASE_URL is never overwritten by .env loading."""
    from api import main

    env_file = tmp_path / ".env"
    env_file.write_text("DATABASE_URL=postgresql://file:test@127.0.0.1:5432/cryptotrader\n")
    monkeypatch.setenv("DATABASE_URL", "postgresql://explicit:test@127.0.0.1:5432/cryptotrader")
    monkeypatch.setenv("CRYPTOTRADER_ENV_FILE", str(env_file))

    assert main._get_database_url() == "postgresql://explicit:test@127.0.0.1:5432/cryptotrader"


# Regression: empty DATABASE_URL must still allow runtime env fallback loading.
def test_database_url_empty_falls_back_to_runtime_env_file(tmp_path, monkeypatch) -> None:
    """Verify DATABASE_URL present but empty falls back to runtime env file."""
    from api import main

    env_file = tmp_path / ".env"
    env_file.write_text("DATABASE_URL=postgresql://fallback:test@127.0.0.1:5432/cryptotrader\n")
    monkeypatch.setenv("DATABASE_URL", "")  # Empty string
    monkeypatch.setenv("CRYPTOTRADER_ENV_FILE", str(env_file))

    assert main._get_database_url() == "postgresql://fallback:test@127.0.0.1:5432/cryptotrader"


def test_database_url_whitespace_only_falls_back_to_runtime_env_file(tmp_path, monkeypatch) -> None:
    """Verify DATABASE_URL with only whitespace falls back to runtime env file."""
    from api import main

    env_file = tmp_path / ".env"
    env_file.write_text("DATABASE_URL=postgresql://whitespace:test@127.0.0.1:5432/cryptotrader\n")
    monkeypatch.setenv("DATABASE_URL", "   ")  # Whitespace only
    monkeypatch.setenv("CRYPTOTRADER_ENV_FILE", str(env_file))

    assert main._get_database_url() == "postgresql://whitespace:test@127.0.0.1:5432/cryptotrader"


def test_get_candles_latest_uses_default_exchange(api_client) -> None:
    """Verify /candles/latest endpoint uses default exchange when not provided.

    The endpoint should accept requests without an exchange parameter and use
    the default value of 'bitfinex'. This test verifies the endpoint doesn't
    return a 422 validation error when exchange is omitted.
    """
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

    Note: The API does not enforce timeframe validation at the endpoint level.
    When an invalid timeframe is used, the database query returns no results,
    leading to a 404 status. In case of database errors, a 500 may be returned.
    This test accepts either status code as both are valid error responses.
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
