"""Shared fixtures for disposable PostgreSQL integration tests.

Provides:
- A disposable PostgreSQL container (via Docker Compose or Docker CLI)
- Schema/migration application
- Cleanup between tests
"""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path
from typing import Generator
from urllib.parse import urlparse

import pytest

ROOT = Path(__file__).resolve().parents[2]

# Disposable DB configuration
DISPOSABLE_DB_NAME = os.environ.get("INTEGRATION_DB", "cryptotrader_test")
DISPOSABLE_DB_USER = os.environ.get("INTEGRATION_USER", "cryptotrader")
DISPOSABLE_DB_PASSWORD = os.environ.get("INTEGRATION_PASS", "testpassword123")
DISPOSABLE_DB_PORT = int(os.environ.get("INTEGRATION_PORT", "5433"))
DISPOSABLE_DB_CONTAINER = os.environ.get("INTEGRATION_CONTAINER_NAME", "cryptotrader-test-db")
KEEP_DISPOSABLE_DB_ENV = "CRYPTOTRADER_KEEP_DISPOSABLE_DB"
CLEAN_DISPOSABLE_DB_ENV = "CRYPTOTRADER_CLEAN_DISPOSABLE_DB"
DISPOSABLE_DB_URL = (
    f"postgresql://{DISPOSABLE_DB_USER}:{DISPOSABLE_DB_PASSWORD}"
    f"@127.0.0.1:{DISPOSABLE_DB_PORT}/{DISPOSABLE_DB_NAME}"
)


def _psql_env() -> dict[str, str]:
    """Return an environment that lets psql authenticate non-interactively."""
    return {**os.environ, "PGPASSWORD": DISPOSABLE_DB_PASSWORD}


def _keep_disposable_db() -> bool:
    """Return whether the disposable DB container should be kept after tests."""
    return os.environ.get(KEEP_DISPOSABLE_DB_ENV) == "1"


def _clean_disposable_db() -> bool:
    """Return whether an existing disposable DB container should be discarded first."""
    return os.environ.get(CLEAN_DISPOSABLE_DB_ENV) == "1"


def _psql_args(db_url: str) -> list[str]:
    """Build psql connection arguments from a PostgreSQL URL."""
    parsed = urlparse(db_url)
    return [
        "-h",
        parsed.hostname or "127.0.0.1",
        "-p",
        str(parsed.port or DISPOSABLE_DB_PORT),
        "-U",
        parsed.username or DISPOSABLE_DB_USER,
        "-d",
        (parsed.path or f"/{DISPOSABLE_DB_NAME}").lstrip("/"),
    ]


def _docker_available() -> bool:
    """Check if Docker is available and running."""
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _psql_available(port: int = DISPOSABLE_DB_PORT, retries: int = 10, delay: int = 2) -> bool:
    """Wait for PostgreSQL to be ready on the given port."""
    for _ in range(retries):
        try:
            result = subprocess.run(
                [
                    "psql",
                    "-h",
                    "127.0.0.1",
                    "-p",
                    str(port),
                    "-U",
                    DISPOSABLE_DB_USER,
                    "-d",
                    DISPOSABLE_DB_NAME,
                    "-c",
                    "SELECT 1",
                ],
                capture_output=True,
                timeout=5,
                env=_psql_env(),
            )
            if result.returncode == 0:
                return True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            # Tooling may not be ready yet while the container is still starting.
            continue
        time.sleep(delay)
    return False


def start_disposable_db(port: int = DISPOSABLE_DB_PORT) -> str:
    """Start a disposable PostgreSQL container and return its URL.

    Reuses an existing named container unless clean-start was requested.
    Returns the DATABASE_URL string.
    """
    if not _docker_available():
        pytest.skip("Docker is not available for disposable PostgreSQL integration tests")

    # Ensure non-interactive psql calls can authenticate.
    os.environ["PGPASSWORD"] = DISPOSABLE_DB_PASSWORD

    if _clean_disposable_db():
        subprocess.run(
            ["docker", "rm", "-f", DISPOSABLE_DB_CONTAINER],
            capture_output=True,
        )

    running = subprocess.run(
        ["docker", "ps", "--format", "{{.Names}}"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    existing = subprocess.run(
        ["docker", "ps", "-a", "--format", "{{.Names}}"],
        capture_output=True,
        text=True,
        timeout=10,
    )

    running_names = running.stdout.splitlines()
    existing_names = existing.stdout.splitlines()

    if DISPOSABLE_DB_CONTAINER in running_names:
        pass
    elif DISPOSABLE_DB_CONTAINER in existing_names:
        subprocess.run(
            ["docker", "start", DISPOSABLE_DB_CONTAINER],
            capture_output=True,
            timeout=30,
        )
    else:
        subprocess.run(
            [
                "docker",
                "run",
                "-d",
                "--name",
                DISPOSABLE_DB_CONTAINER,
                "-p",
                f"{port}:5432",
                "-e",
                f"POSTGRES_USER={DISPOSABLE_DB_USER}",
                "-e",
                f"POSTGRES_PASSWORD={DISPOSABLE_DB_PASSWORD}",
                "-e",
                f"POSTGRES_DB={DISPOSABLE_DB_NAME}",
                "-e",
                "POSTGRES_INITDB_ARGS=--encoding=UTF-8",
                f"postgres:{os.environ.get('PG_VERSION', '16-alpine')}",
            ],
            capture_output=True,
            timeout=30,
        )

    # Wait for it to be ready
    if not _psql_available(port):
        # Collect logs for debugging
        logs = subprocess.run(
            ["docker", "logs", DISPOSABLE_DB_CONTAINER],
            capture_output=True,
            text=True,
            timeout=10,
        )
        raise RuntimeError(f"PostgreSQL did not become ready on port {port}.\n{logs.stdout[-500:]}")
    return f"postgresql://{DISPOSABLE_DB_USER}:{DISPOSABLE_DB_PASSWORD}" f"@127.0.0.1:{port}/{DISPOSABLE_DB_NAME}"


def stop_disposable_db() -> None:
    """Stop and remove the disposable PostgreSQL container."""
    if _keep_disposable_db():
        return

    subprocess.run(
        ["docker", "rm", "-f", DISPOSABLE_DB_CONTAINER],
        capture_output=True,
    )


def apply_schema(db_url: str, schema_path: Path | None = None) -> None:
    """Apply the main schema.sql to the disposable database."""
    if schema_path is None:
        schema_path = ROOT / "db" / "schema.sql"

    result = subprocess.run(
        [
            "psql",
            *_psql_args(db_url),
            "-f",
            str(schema_path),
        ],
        capture_output=True,
        text=True,
        timeout=30,
        env=_psql_env(),
    )
    if result.returncode != 0:
        raise RuntimeError(f"Schema application failed:\n{result.stderr}")


def apply_migrations(db_url: str, migrations_dir: Path | None = None) -> int:
    """Apply all migration SQL files in order. Returns count of applied migrations."""
    if migrations_dir is None:
        migrations_dir = ROOT / "db" / "migrations"

    # Find and sort migration files
    migration_files = sorted(migrations_dir.glob("*.sql"))

    applied = 0
    for mf in migration_files:
        result = subprocess.run(
            [
                "psql",
                *_psql_args(db_url),
                "-f",
                str(mf),
            ],
            capture_output=True,
            text=True,
            timeout=30,
            env=_psql_env(),
        )
        if result.returncode != 0:
            raise RuntimeError(f"Migration {mf.name} failed:\n{result.stderr}")
        applied += 1

    return applied


@pytest.fixture(scope="session")
def disposable_db() -> Generator[str, None, None]:
    """Session-scoped disposable PostgreSQL container.

    Starts once per test session, stops at the end.
    Yields the DATABASE_URL string.
    """
    url = start_disposable_db()
    yield url
    stop_disposable_db()


@pytest.fixture(scope="session")
def schema_applied(disposable_db: str) -> str:
    """Apply schema.sql to the disposable DB. Yields DB_URL."""
    apply_schema(disposable_db)
    return disposable_db


@pytest.fixture(scope="session")
def migrations_applied(schema_applied: str) -> str:
    """Apply all migrations to the disposable DB. Yields DB_URL."""
    apply_migrations(schema_applied)
    return schema_applied


@pytest.fixture
def test_db_url() -> str:
    """Return the disposable database URL for each test."""
    return DISPOSABLE_DB_URL


@pytest.fixture
def env_override(test_db_url: str):
    """Temporarily override DATABASE_URL for tests that read from env."""
    old = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = test_db_url
    yield test_db_url
    if old is not None:
        os.environ["DATABASE_URL"] = old
    elif "DATABASE_URL" in os.environ:
        del os.environ["DATABASE_URL"]
