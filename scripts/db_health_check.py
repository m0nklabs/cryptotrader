#!/usr/bin/env python3
"""Database + ingestion healthcheck CLI.

Validates DB connectivity and reports ingestion status without exposing secrets.

Usage:
  python scripts/db_health_check.py --exchange bitfinex --symbol BTCUSD --timeframe 1h

Exit codes:
  0 = success
  1 = failure (DB connectivity, schema, or other error)

Requirements:
  - DATABASE_URL must be set
  - SQLAlchemy + psycopg2-binary (see requirements.txt)
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="DB + ingestion healthcheck (no secrets output)."
    )
    p.add_argument(
        "--exchange",
        default="bitfinex",
        help="Exchange code (default: bitfinex)",
    )
    p.add_argument(
        "--symbol",
        default="BTCUSD",
        help="Symbol (default: BTCUSD)",
    )
    p.add_argument(
        "--timeframe",
        default="1h",
        help="Timeframe (default: 1h)",
    )
    return p.parse_args()


def main() -> int:
    args = _parse_args()

    # 1. Check DATABASE_URL is set
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("❌ db-fail: DATABASE_URL is not set", file=sys.stderr)
        return 1

    # 2. Try to import SQLAlchemy
    try:
        from sqlalchemy import create_engine, text  # type: ignore
    except ImportError as exc:
        print(
            f"❌ db-fail: SQLAlchemy is required. Install: pip install SQLAlchemy psycopg2-binary",
            file=sys.stderr,
        )
        print(f"   Error: {exc}", file=sys.stderr)
        return 1

    # 3. Try to connect to the database
    try:
        # Do not echo the database_url or log it (contains credentials)
        engine = create_engine(database_url, echo=False, pool_pre_ping=True)
        conn = engine.connect()
    except Exception as exc:
        print(f"❌ db-fail: Unable to connect to database", file=sys.stderr)
        print(f"   Error: {exc}", file=sys.stderr)
        return 1

    print("✅ db-ok")

    # 4. Check schema (candles table exists)
    schema_ok = False
    try:
        stmt = text(
            """
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'candles'
            )
            """
        )
        row = conn.execute(stmt).fetchone()
        schema_ok = bool(row and row[0])
    except Exception as exc:
        print(f"❌ schema-fail: Unable to verify schema", file=sys.stderr)
        print(f"   Error: {exc}", file=sys.stderr)
        conn.close()
        return 1

    if not schema_ok:
        print("❌ schema-fail: candles table does not exist", file=sys.stderr)
        conn.close()
        return 1

    print("✅ schema-ok (candles table exists)")

    # 5. Count total candles
    try:
        stmt = text("SELECT COUNT(*) FROM candles")
        row = conn.execute(stmt).fetchone()
        candles_count = int(row[0]) if row else 0
        print(f"📊 candles_count: {candles_count}")
    except Exception as exc:
        print(f"⚠️  candles_count: Unable to count candles", file=sys.stderr)
        print(f"   Error: {exc}", file=sys.stderr)

    # 6. Get latest candle open_time for the provided exchange/symbol/timeframe
    try:
        stmt = text(
            """
            SELECT open_time
            FROM candles
            WHERE exchange = :exchange
              AND symbol = :symbol
              AND timeframe = :timeframe
            ORDER BY open_time DESC
            LIMIT 1
            """
        )
        row = conn.execute(
            stmt,
            {
                "exchange": args.exchange,
                "symbol": args.symbol,
                "timeframe": args.timeframe,
            },
        ).fetchone()

        if row:
            latest_open_time: datetime = row[0]
            print(
                f"🕒 latest_candle_open_time ({args.exchange}/{args.symbol}/{args.timeframe}): "
                f"{latest_open_time.isoformat()}"
            )
        else:
            print(
                f"⚠️  latest_candle_open_time ({args.exchange}/{args.symbol}/{args.timeframe}): "
                f"No candles found"
            )
    except Exception as exc:
        print(
            f"⚠️  latest_candle_open_time: Unable to query latest candle",
            file=sys.stderr,
        )
        print(f"   Error: {exc}", file=sys.stderr)

    conn.close()
    print("\n✅ Health check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
