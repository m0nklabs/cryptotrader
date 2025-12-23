#!/usr/bin/env python3
"""Detect trading signals/opportunities and store them in the database.

This script:
1. Fetches available symbols/timeframes from the database
2. For each pair, fetches recent candles
3. Runs signal detection (RSI, MA crossover, volume spike)
4. Stores detected opportunities in the database

Usage:
    python -m scripts.detect_signals [--exchange bitfinex] [--symbol BTCUSD] [--timeframe 1h]

Environment:
    DATABASE_URL - PostgreSQL connection string
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Ensure imports work when invoked as a script (e.g., from systemd).
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from core.signals.detector import detect_signals  # noqa: E402
from core.storage.postgres.config import PostgresConfig  # noqa: E402
from core.storage.postgres.stores import PostgresStores  # noqa: E402
from core.types import Candle  # noqa: E402


def fetch_available_pairs(stores: PostgresStores, exchange: str) -> list[tuple[str, str]]:
    """Fetch available (symbol, timeframe) pairs from candles table."""
    engine = stores._get_engine()  # noqa: SLF001
    _, text = stores._require_sqlalchemy()  # noqa: SLF001

    stmt = text(
        """
        SELECT DISTINCT symbol, timeframe
        FROM candles
        WHERE exchange = :exchange
        ORDER BY symbol ASC, timeframe ASC
        """
    )

    with engine.begin() as conn:
        rows = conn.execute(stmt, {"exchange": exchange}).fetchall()

    return [(str(row[0]), str(row[1])) for row in rows]


def fetch_candles_for_detection(
    stores: PostgresStores,
    *,
    exchange: str,
    symbol: str,
    timeframe: str,
    limit: int = 250,
) -> list[Candle]:
    """Fetch recent candles for signal detection."""
    engine = stores._get_engine()  # noqa: SLF001
    _, text = stores._require_sqlalchemy()  # noqa: SLF001

    stmt = text(
        """
        SELECT exchange, symbol, timeframe, open_time, close_time, open, high, low, close, volume
        FROM candles
        WHERE exchange = :exchange
          AND symbol = :symbol
          AND timeframe = :timeframe
        ORDER BY open_time DESC
        LIMIT :limit
        """
    )

    with engine.begin() as conn:
        rows = conn.execute(
            stmt,
            {"exchange": exchange, "symbol": symbol, "timeframe": timeframe, "limit": limit},
        ).fetchall()

    # Reverse to get ascending time order
    rows = list(reversed(rows))

    return [
        Candle(
            exchange=row[0],
            symbol=row[1],
            timeframe=row[2],
            open_time=row[3],
            close_time=row[4],
            open=row[5],
            high=row[6],
            low=row[7],
            close=row[8],
            volume=row[9],
        )
        for row in rows
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description="Detect trading signals and store opportunities")
    parser.add_argument("--exchange", default="bitfinex", help="Exchange name (default: bitfinex)")
    parser.add_argument("--symbol", help="Optional: specific symbol to analyze")
    parser.add_argument("--timeframe", help="Optional: specific timeframe to analyze")
    parser.add_argument("--limit", type=int, default=250, help="Number of candles to fetch (default: 250)")
    args = parser.parse_args()

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("❌ DATABASE_URL is required", file=sys.stderr)
        return 1

    stores = PostgresStores(config=PostgresConfig(database_url=database_url))

    # Fetch available pairs
    if args.symbol and args.timeframe:
        pairs = [(args.symbol, args.timeframe)]
    elif args.symbol:
        all_pairs = fetch_available_pairs(stores, args.exchange)
        pairs = [(sym, tf) for sym, tf in all_pairs if sym == args.symbol]
    elif args.timeframe:
        all_pairs = fetch_available_pairs(stores, args.exchange)
        pairs = [(sym, tf) for sym, tf in all_pairs if tf == args.timeframe]
    else:
        pairs = fetch_available_pairs(stores, args.exchange)

    if not pairs:
        print(f"⚠️  No pairs found for exchange={args.exchange}", file=sys.stderr)
        return 0

    print(f"🔍 Analyzing {len(pairs)} pairs on {args.exchange}...")

    detected_count = 0
    for symbol, timeframe in pairs:
        try:
            # Fetch candles
            candles = fetch_candles_for_detection(
                stores,
                exchange=args.exchange,
                symbol=symbol,
                timeframe=timeframe,
                limit=args.limit,
            )

            if len(candles) < 15:
                continue

            # Detect signals
            opportunity = detect_signals(
                candles=candles,
                symbol=symbol,
                timeframe=timeframe,
                exchange=args.exchange,
            )

            if opportunity and opportunity.score > 0:
                # Store opportunity
                stores.log_opportunity(opportunity=opportunity, exchange=args.exchange)
                detected_count += 1
                print(
                    f"  ✓ {symbol} {timeframe}: {opportunity.side} (score: {opportunity.score}, "
                    f"signals: {len(opportunity.signals)})"
                )

        except Exception as exc:
            print(f"  ⚠️  Error analyzing {symbol} {timeframe}: {exc}", file=sys.stderr)
            continue

    print(f"✅ Detected and stored {detected_count} opportunities")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
