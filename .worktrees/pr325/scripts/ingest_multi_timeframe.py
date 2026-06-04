#!/usr/bin/env python3
"""Multi-timeframe candle ingestion wrapper.

This script orchestrates backfill for multiple timeframes for one or more symbols.
It's a convenience wrapper around core.market_data.bitfinex_backfill that runs
ingestion for standard timeframes (1m, 5m, 15m, 1h, 4h, 1d).

Usage:
    # Backfill all timeframes for a symbol from a start date
    python -m scripts.ingest_multi_timeframe --symbol BTCUSD --start 2024-01-01

    # Resume ingestion for all timeframes for multiple symbols
    python -m scripts.ingest_multi_timeframe --symbol BTCUSD --symbol ETHUSD --resume

    # Backfill specific timeframes only
    python -m scripts.ingest_multi_timeframe --symbol BTCUSD --timeframe 1h --timeframe 4h --resume
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Sequence

from core.market_data.bitfinex_backfill import main as backfill_main


# Default timeframes to ingest if none specified
DEFAULT_TIMEFRAMES = ["1m", "5m", "15m", "1h", "4h", "1d"]


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backfill candles for multiple timeframes",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--symbol",
        action="append",
        required=True,
        help="Symbol to ingest (repeatable for multiple symbols)",
    )
    parser.add_argument(
        "--timeframe",
        action="append",
        help="Timeframe to ingest (default: all standard timeframes). Repeatable.",
    )
    parser.add_argument(
        "--start",
        help="ISO datetime/date for initial backfill (UTC assumed if no tz)",
    )
    parser.add_argument(
        "--end",
        help="ISO datetime/date (UTC assumed if no tz). Default: now (UTC)",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from latest candle in DB (ignores --start)",
    )
    parser.add_argument(
        "--exchange",
        default="bitfinex",
        help="Exchange code (default: bitfinex)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=1000,
        help="DB upsert batch size (default: 1000)",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=6,
        help="Maximum retry attempts (default: 6)",
    )
    parser.add_argument(
        "--initial-backoff-seconds",
        type=float,
        default=0.5,
        help="Initial backoff delay in seconds (default: 0.5)",
    )
    parser.add_argument(
        "--max-backoff-seconds",
        type=float,
        default=8.0,
        help="Max backoff delay in seconds (default: 8.0)",
    )
    parser.add_argument(
        "--jitter-seconds",
        type=float,
        default=0.0,
        help="Max random jitter in seconds (default: 0.0)",
    )
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Stop on first error instead of continuing with other timeframes",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)

    if not args.resume and not args.start:
        print("ERROR: --start is required unless --resume is set", file=sys.stderr)
        return 1

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL environment variable not set", file=sys.stderr)
        return 1

    symbols = args.symbol
    timeframes = args.timeframe if args.timeframe else DEFAULT_TIMEFRAMES

    print("Multi-timeframe ingestion starting")
    print(f"  Exchange: {args.exchange}")
    print(f"  Symbols: {', '.join(symbols)}")
    print(f"  Timeframes: {', '.join(timeframes)}")
    print(f"  Mode: {'resume' if args.resume else 'backfill'}")
    if not args.resume:
        print(f"  Start: {args.start}")
        if args.end:
            print(f"  End: {args.end}")
    print()

    total_jobs = len(symbols) * len(timeframes)
    completed = 0
    failed = 0
    errors: list[tuple[str, str, str]] = []

    for symbol in symbols:
        for timeframe in timeframes:
            job_desc = f"{symbol}:{timeframe}"
            print(f"[{completed + 1}/{total_jobs}] Processing {job_desc}...")

            # Build argv for backfill_main
            backfill_argv = [
                "--symbol",
                symbol,
                "--timeframe",
                timeframe,
                "--exchange",
                args.exchange,
                "--batch-size",
                str(args.batch_size),
                "--max-retries",
                str(args.max_retries),
                "--initial-backoff-seconds",
                str(args.initial_backoff_seconds),
                "--max-backoff-seconds",
                str(args.max_backoff_seconds),
                "--jitter-seconds",
                str(args.jitter_seconds),
            ]

            if args.resume:
                backfill_argv.append("--resume")
            else:
                backfill_argv.extend(["--start", args.start])

            if args.end:
                backfill_argv.extend(["--end", args.end])

            try:
                exit_code = backfill_main(backfill_argv)
                if exit_code == 0:
                    completed += 1
                    print(f"✓ {job_desc} completed successfully\n")
                else:
                    failed += 1
                    error_msg = f"Exit code: {exit_code}"
                    errors.append((symbol, timeframe, error_msg))
                    print(f"✗ {job_desc} failed: {error_msg}\n")
                    if args.fail_fast:
                        break
            except Exception as e:
                failed += 1
                error_msg = str(e)
                errors.append((symbol, timeframe, error_msg))
                print(f"✗ {job_desc} failed: {error_msg}\n")
                if args.fail_fast:
                    break

        if args.fail_fast and failed > 0:
            break

    # Summary
    print("=" * 60)
    print("Multi-timeframe ingestion summary")
    print(f"  Total jobs: {total_jobs}")
    print(f"  Completed: {completed}")
    print(f"  Failed: {failed}")

    if errors:
        print("\nErrors:")
        for symbol, timeframe, error in errors:
            print(f"  - {symbol}:{timeframe}: {error}")

    print("=" * 60)

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
