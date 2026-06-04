"""Tests for API endpoints with mocked database.

Tests critical API endpoints to ensure they handle requests correctly
and properly interact with the database layer.

Note: These are simplified validation tests. Full integration tests with
database are in test_api*.py files.
"""

import os
import tempfile
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


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


# ---------------------------------------------------------------------------
# DATABASE_URL fallback and precedence regression tests
# ---------------------------------------------------------------------------


def _clear_stores():
    """Reset the global _stores and _ENV_PATH so tests start fresh."""
    import api.main as main_mod

    main_mod._stores = None
    # Re-resolve _ENV_PATH in case _PROJECT_ROOT was affected
    main_mod._ENV_PATH = main_mod._PROJECT_ROOT / ".env"


def _set_env_file(env_path: Path, content: str) -> None:
    """Write *content* to *env_path* (as a flat KEY=VALUE file)."""
    env_path.write_text(content)


def _unset_env_var(name: str) -> None:
    """Remove an environment variable if present."""
    os.environ.pop(name, None)


class TestDatabaseUrlFallback:
    """Regression tests for DATABASE_URL resolution in _get_stores().

    Resolution order:
    1. Process environment variable (systemd/container overrides win)
    2. Repo-local .env file (safe fallback via load_dotenv with override=False)
    """

    def test_missing_env_file_raises_runtime_error(self, tmp_path, monkeypatch):
        """When no DATABASE_URL in process env and no .env file, _get_stores raises RuntimeError."""
        from api.main import _get_stores

        _clear_stores()
        monkeypatch.setenv("DATABASE_URL", "")
        _unset_env_var("DATABASE_URL")

        # Point _ENV_PATH at tmp_path (empty, no .env file)
        import api.main as main_mod

        main_mod._ENV_PATH = tmp_path / ".env"
        main_mod._stores = None

        with pytest.raises(RuntimeError, match="DATABASE_URL environment variable is required"):
            _get_stores()

    def test_present_env_file_provides_fallback(self, tmp_path, monkeypatch):
        """When .env exists with DATABASE_URL and process env is unset, load_dotenv provides fallback."""
        from api.main import _get_stores

        _clear_stores()
        _unset_env_var("DATABASE_URL")

        env_file = tmp_path / ".env"
        _set_env_file(env_file, "DATABASE_URL=postgresql://fallback:5432/testdb\n")

        import api.main as main_mod

        main_mod._ENV_PATH = env_file
        main_mod._stores = None

        stores = _get_stores()
        assert stores._config.database_url == "postgresql://fallback:5432/testdb"

    def test_process_env_overrides_env_file(self, tmp_path, monkeypatch):
        """When DATABASE_URL is set in process env, it takes precedence over .env value."""
        from api.main import _get_stores

        _clear_stores()

        env_file = tmp_path / ".env"
        _set_env_file(env_file, "DATABASE_URL=postgresql://fallback:5432/testdb\n")

        # Set process env to a different value
        monkeypatch.setenv("DATABASE_URL", "postgresql://process:5432/proddb")

        import api.main as main_mod

        main_mod._ENV_PATH = env_file
        main_mod._stores = None

        stores = _get_stores()
        # Process env should win over .env fallback
        assert stores._config.database_url == "postgresql://process:5432/proddb"

    def test_load_dotenv_does_not_overwrite_existing(self, tmp_path, monkeypatch):
        """load_dotenv with override=False should not overwrite existing DATABASE_URL."""
        from api.main import _get_stores

        _clear_stores()

        env_file = tmp_path / ".env"
        _set_env_file(env_file, "DATABASE_URL=postgresql://file:5432/filedb\n")

        # Pre-set DATABASE_URL in process env
        monkeypatch.setenv("DATABASE_URL", "postgresql://proc:5432/proddb")

        import api.main as main_mod

        main_mod._ENV_PATH = env_file
        main_mod._stores = None

        stores = _get_stores()
        # Should use pre-set process env value, not the .env value
        assert stores._config.database_url == "postgresql://proc:5432/proddb"

    def test_stores_is_cached_after_first_call(self, tmp_path, monkeypatch):
        """_get_stores returns the same instance on subsequent calls (singleton behavior)."""
        from api.main import _get_stores

        _clear_stores()

        env_file = tmp_path / ".env"
        _set_env_file(env_file, "DATABASE_URL=postgresql://cached:5432/cached\n")
        _unset_env_var("DATABASE_URL")

        import api.main as main_mod

        main_mod._ENV_PATH = env_file
        main_mod._stores = None

        first = _get_stores()
        second = _get_stores()

        assert first is second
