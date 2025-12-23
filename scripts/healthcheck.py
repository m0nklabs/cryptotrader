#!/usr/bin/env python3
"""DB + ingestion healthcheck (no secrets).

This script is intentionally conservative:
- Reads DATABASE_URL from the environment (does not print it).
- Uses SQLAlchemy if installed.
- Exits non-zero on missing deps / connectivity / schema problems.

Usage:
  python scripts/healthcheck.py

Exit codes:
  0 = OK
  2 = missing dependency or configuration
  3 = database connectivity error
  4 = schema/problem detected
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class CheckResult:
    ok: bool
    message: str


REQUIRED_TABLES = (
    "candles",
    "candle_gaps",
    "market_data_jobs",
    "market_data_job_runs",
)


def _require_database_url() -> str:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL is not set")
    return database_url


def _require_sqlalchemy() -> tuple[object, object]:
    try:
        from sqlalchemy import create_engine, text  # type: ignore[import-not-found]
    except Exception as exc:
        raise SystemExit(
            "SQLAlchemy is required for healthcheck. Install optional deps: pip install SQLAlchemy psycopg2-binary"
        ) from exc

    return create_engine, text


def _check_connectivity(*, engine: object, text: object) -> CheckResult:
    try:
        with engine.begin() as conn:  # type: ignore[attr-defined]
            conn.execute(text("SELECT 1"))  # type: ignore[call-arg]
        return CheckResult(True, "db connectivity: ok")
    except Exception as exc:
        return CheckResult(False, f"db connectivity: failed ({type(exc).__name__})")


def _fetch_existing_tables(*, engine: object, text: object) -> set[str]:
    stmt = text(
        """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
        """
    )

    with engine.begin() as conn:  # type: ignore[attr-defined]
        rows = conn.execute(stmt).fetchall()  # type: ignore[call-arg]

    return {str(r[0]) for r in rows}


def _check_schema(*, engine: object, text: object) -> CheckResult:
    try:
        existing = _fetch_existing_tables(engine=engine, text=text)
    except Exception as exc:
        return CheckResult(False, f"schema check: failed ({type(exc).__name__})")

    missing = [t for t in REQUIRED_TABLES if t not in existing]
    if missing:
        return CheckResult(False, f"schema check: missing tables: {', '.join(missing)}")

    return CheckResult(True, "schema check: ok")


def _check_candle_stats(*, engine: object, text: object) -> CheckResult:
    # Candles may be empty on a fresh install; that's still OK.
    stmt = text(
        """
        SELECT COUNT(*) AS n, MAX(open_time) AS latest_open_time
        FROM candles
        """
    )

    try:
        with engine.begin() as conn:  # type: ignore[attr-defined]
            row = conn.execute(stmt).fetchone()  # type: ignore[call-arg]
    except Exception as exc:
        return CheckResult(False, f"candles stats: failed ({type(exc).__name__})")

    if not row:
        return CheckResult(True, "candles stats: ok (no rows)")

    n = int(row[0] or 0)
    latest = row[1]
    if latest is None:
        return CheckResult(True, f"candles stats: ok (rows={n}, latest_open_time=none)")

    # Do not attempt timezone normalization here; we only display the type.
    return CheckResult(True, f"candles stats: ok (rows={n}, latest_open_time_type={type(latest).__name__})")


def _check_gaps(*, engine: object, text: object) -> CheckResult:
    stmt = text(
        """
        SELECT
          SUM(CASE WHEN repaired_at IS NULL THEN 1 ELSE 0 END) AS open_gaps
        FROM candle_gaps
        """
    )

    try:
        with engine.begin() as conn:  # type: ignore[attr-defined]
            row = conn.execute(stmt).fetchone()  # type: ignore[call-arg]
    except Exception as exc:
        return CheckResult(False, f"gap check: failed ({type(exc).__name__})")

    open_gaps = int((row[0] if row and row[0] is not None else 0))
    # Open gaps are not fatal for “health”, but do indicate remediation needed.
    return CheckResult(True, f"gap check: ok (open_gaps={open_gaps})")


def main() -> int:
    try:
        database_url = _require_database_url()
        create_engine, text = _require_sqlalchemy()
    except SystemExit as exc:
        msg = str(exc)
        if msg:
            print(msg)
        return 2

    # Do not log database_url.
    engine = create_engine(database_url, echo=False, pool_pre_ping=True)

    checks: list[CheckResult] = []

    checks.append(_check_connectivity(engine=engine, text=text))
    if not checks[-1].ok:
        for c in checks:
            print(c.message)
        return 3

    checks.append(_check_schema(engine=engine, text=text))
    if not checks[-1].ok:
        for c in checks:
            print(c.message)
        return 4

    checks.append(_check_candle_stats(engine=engine, text=text))
    checks.append(_check_gaps(engine=engine, text=text))

    for c in checks:
        print(c.message)

    # If we got here, we consider the system healthy.
    return 0


if __name__ == "__main__":
    sys.exit(main())
