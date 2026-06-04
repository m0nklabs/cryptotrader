# DATABASE_URL Fallback

## Overview

The CryptoTrader API resolves `DATABASE_URL` from multiple sources with a clear priority order:

1. **Explicit process environment variable** (highest priority)
2. **Repo-local `.env` file** (safe fallback)

This ensures that manually started API processes can find their database URL even when `DATABASE_URL` is not set as an explicit process environment variable.

## How It Works

### Priority Order

```
os.environ["DATABASE_URL"]  (explicit process env)
       ↓ (if missing)
load_dotenv(".env", override=False)  (repo-local .env file)
       ↓ (if still missing)
raise RuntimeError("DATABASE_URL environment variable is required")
```

The `override=False` parameter in `load_dotenv()` ensures that explicit process environment values are never overwritten by values from the `.env` file.

### Implementation

The `_get_stores()` function in `api/main.py` handles the resolution inline:

```python
def _get_stores() -> PostgresStores:
    """Get or initialize the database stores.

    DATABASE_URL resolution (authoritative order):
    1. Process environment variable (systemd/container overrides win)
    2. Repo-local .env file (safe fallback)
    """
    global _stores
    if _stores is None:
        database_url = os.environ.get("DATABASE_URL")
        if not database_url and load_dotenv is not None:
            load_dotenv(_ENV_PATH, override=False)
            database_url = os.environ.get("DATABASE_URL")
        if not database_url:
            raise RuntimeError("DATABASE_URL environment variable is required")
        _stores = PostgresStores(config=PostgresConfig(database_url=database_url))
    return _stores
```

### Custom Environment File Path

The `.env` file path is resolved relative to the project root (parent of `api/`):

```python
_PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent  # repo root
_ENV_PATH = _PROJECT_ROOT / ".env"
```

### Usage

The `_get_stores()` function uses `_get_database_url()` to resolve the database URL:

```python
def _get_stores() -> PostgresStores:
    """Get or initialize the database stores."""
    global _stores
    if _stores is None:
        _stores = PostgresStores(config=PostgresConfig(database_url=_get_database_url()))
    return _stores
```

## Testing

Five regression tests verify the behavior in `tests/test_api_endpoints.py`:

1. **`test_missing_env_file_raises_runtime_error`**: Verifies that `_get_stores()` raises `RuntimeError` when no `DATABASE_URL` is set and no `.env` file exists.

2. **`test_present_env_file_provides_fallback`**: Verifies that `DATABASE_URL` falls back to the `.env` file when not set as an explicit process environment variable.

3. **`test_process_env_overrides_env_file`**: Verifies that an explicit `DATABASE_URL` in the process env takes precedence over the `.env` file value.

4. **`test_load_dotenv_does_not_overwrite_existing`**: Verifies that `load_dotenv(override=False)` does not overwrite an existing `DATABASE_URL` in the process env.

5. **`test_stores_is_cached_after_first_call`**: Verifies that `_get_stores()` returns the same `PostgresStores` instance on subsequent calls (singleton behavior).

Run all DATABASE_URL regression tests:

```bash
python -m pytest tests/test_api_endpoints.py::TestDatabaseUrlFallback -v
```

## Related

- `api/main.py`: Implementation of `_get_database_url()` and `_load_runtime_env()`
- `tests/test_api_endpoints.py`: Regression tests
- `CHANGELOG.md`: Changelog entry for the DATABASE_URL fix
- `core/storage/postgres/config.py`: `PostgresConfig` dataclass
- `core/storage/postgres/stores.py`: `PostgresStores` class
