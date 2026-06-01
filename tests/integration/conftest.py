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

import pytest

ROOT = Path(__file__).resolve().parents[2]

# Disposable DB configuration
DISPOSABLE_DB_NAME = "cryptotrader_test"
DISPOSABLE_DB_USER = "cryptotrader"
DISPOSABLE_DB_PASSWORD = "testpassword123"
DISPOSABLE_DB_URL = (
    f"postgresql://{DISPOSABLE_DB_USER}:{DISPOSABLE_DB_PASSWORD}"
    "@127.0.0.1:5433/"
    f"{DISPOSABLE_DB_NAME}"
)


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


def _psql_available(port: int = 5433, retries: int = 10, delay: int = 2) -> bool:
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
            )
            if result.returncode == 0:
                return True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        time.sleep(delay)
    return False


def start_disposable_db(port: int = 5433) -> str:
    """Start a disposable PostgreSQL container and return its URL.

    Uses docker run with a dedicated test database.
    Returns the DATABASE_URL string.
    """
    if not _docker_available():
        raise RuntimeError("Docker is not available for disposable PostgreSQL")

    # Ensure non-interactive psql calls can authenticate.
    os.environ.setdefault("PGPASSWORD", DISPOSABLE_DB_PASSWORD)
    # Stop any existing test container
    subprocess.run(
        ["docker", "rm", "-f", "cryptotrader-test-db"],
        capture_output=True,
    )

    # Start fresh container
    subprocess.run(
        [
            "docker",
            "run",
            "-d",
            "--name",
            "cryptotrader-test-db",
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
            "postgres:16-alpine",
        ],
        capture_output=True,
        timeout=30,
    )

    # Wait for it to be ready
    if not _psql_available(port):
        # Collect logs for debugging
        logs = subprocess.run(
            ["docker", "logs", "cryptotrader-test-db"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        raise RuntimeError(
            f"PostgreSQL did not become ready on port {port}.\n{logs.stdout[-500:]}"
    return (
        f"postgresql://{DISPOSABLE_DB_USER}:{DISPOSABLE_DB_PASSWORD}"
        f"@127.0.0.1:{port}/{DISPOSABLE_DB_NAME}"
    )


def stop_disposable_db() -> None:
    """Stop and remove the disposable PostgreSQL container."""
    subprocess.run(
        ["docker", "rm", "-f", "cryptotrader-test-db"],
        capture_output=True,
    )


def apply_schema(db_url: str, schema_path: Path | None = None) -> None:
    """Apply the main schema.sql to the disposable database."""
    if schema_path is None:
        schema_path = ROOT / "db" / "schema.sql"

    result = subprocess.run(
        [
            "psql",
            "-h",
            "127.0.0.1",
            "-p",
            "5433",
            "-U",
            DISPOSABLE_DB_USER,
            "-d",
            DISPOSABLE_DB_NAME,
            "-f",
            str(schema_path),
        ],
        capture_output=True,
        text=True,
        timeout=30,
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
                "-h",
                "127.0.0.1",
                "-p",
                "5433",
                "-U",
                DISPOSABLE_DB_USER,
                "-d",
                DISPOSABLE_DB_NAME,
                "-f",
                str(mf),
            ],
            capture_output=True,
            text=True,
            timeout=30,
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
