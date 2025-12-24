#!/usr/bin/env python3
"""Example: Ingest multiple timeframes for common trading pairs.

This script demonstrates how to use the multi-timeframe ingestion script
to populate the database with candles for standard timeframes.

Prerequisites:
- DATABASE_URL environment variable set
- PostgreSQL database with schema initialized (db/schema.sql)

Example usage:
    # Historical backfill (last 30 days)
    python scripts/example_multi_timeframe_ingestion.py --mode backfill

    # Resume/update (fetch latest candles)
    python scripts/example_multi_timeframe_ingestion.py --mode resume

Note:
    This is an EXAMPLE script. For production, use systemd timers or cron jobs
    to run the multi-timeframe ingestion on a schedule.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta, timezone

from scripts.ingest_multi_timeframe import main as ingest_main


# Common trading pairs to track
DEFAULT_SYMBOLS = [
    "BTCUSD",
    "ETHUSD",
    "SOLUSD",
    "XRPUSD",
]

# Standard timeframes (matches DEFAULT_TIMEFRAMES in ingest_multi_timeframe.py)
DEFAULT_TIMEFRAMES = ["1m", "5m", "15m", "1h", "4h", "1d"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Example multi-timeframe ingestion for common trading pairs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--mode",
        choices=["backfill", "resume"],
        default="resume",
        help="Ingestion mode: backfill (historical) or resume (latest)",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=30,
        help="Number of days to backfill (only used in backfill mode, default: 30)",
    )
    parser.add_argument(
        "--symbols",
        nargs="+",
        default=DEFAULT_SYMBOLS,
        help=f"Symbols to ingest (default: {' '.join(DEFAULT_SYMBOLS)})",
    )
    parser.add_argument(
        "--timeframes",
        nargs="+",
        default=DEFAULT_TIMEFRAMES,
        help=f"Timeframes to ingest (default: {' '.join(DEFAULT_TIMEFRAMES)})",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    # Verify DATABASE_URL is set
    if not os.getenv("DATABASE_URL"):
        print("ERROR: DATABASE_URL environment variable not set", file=sys.stderr)
        print("\nExample:", file=sys.stderr)
        print('  export DATABASE_URL="postgresql://user:pass@localhost:5432/cryptotrader"', file=sys.stderr)
        return 1

    # Build arguments for ingest_multi_timeframe
    ingest_args = []

    # Add symbols
    for symbol in args.symbols:
        ingest_args.extend(["--symbol", symbol])

    # Add timeframes (if not using defaults, they would be added implicitly)
    if args.timeframes != DEFAULT_TIMEFRAMES:
        for timeframe in args.timeframes:
            ingest_args.extend(["--timeframe", timeframe])

    # Add mode-specific arguments
    if args.mode == "resume":
        ingest_args.append("--resume")
        print(f"Resuming ingestion for {len(args.symbols)} symbols × {len(args.timeframes)} timeframes")
        print("This will fetch the latest candles from the last recorded timestamp to now.\n")
    else:  # backfill
        start_date = datetime.now(tz=timezone.utc) - timedelta(days=args.days)
        start_str = start_date.strftime("%Y-%m-%d")
        ingest_args.extend(["--start", start_str])
        print(f"Backfilling {args.days} days for {len(args.symbols)} symbols × {len(args.timeframes)} timeframes")
        print(f"Start date: {start_str}")
        print("This may take several minutes depending on the date range and number of pairs.\n")

    # Show what we're about to do
    print("Symbols:", ", ".join(args.symbols))
    print("Timeframes:", ", ".join(args.timeframes))
    print()

    # Confirm before proceeding with large backfills
    if args.mode == "backfill" and args.days > 7:
        response = input("Proceed with backfill? [y/N]: ")
        if response.lower() not in ("y", "yes"):
            print("Cancelled.")
            return 0

    # Run the ingestion
    return ingest_main(ingest_args)


if __name__ == "__main__":
    raise SystemExit(main())
