from __future__ import annotations

import argparse
import os
import random
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Sequence

from core.market_data.bitfinex_backfill import _TIMEFRAMES, run_backfill
from core.storage import PostgresConfig, PostgresStores
from core.types import Timeframe


# Jitter configuration for rate-limit friendly sleep
JITTER_MIN = 0.8  # Minimum jitter multiplier (80% of sleep time)
JITTER_RANGE = 0.4  # Range of jitter (±20%)


@dataclass(frozen=True)
class SeedConfig:
    """Configuration for seed backfill batching."""

    symbol: str
    timeframe: Timeframe
    days: int
    chunk_minutes: int
    sleep_seconds: float
    exchange: str = "bitfinex"


def _calculate_chunks(
    *,
    end: datetime,
    total_days: int,
    chunk_minutes: int,
    timeframe: Timeframe,
) -> list[tuple[datetime, datetime]]:
    """Calculate time chunks for batched backfill.

    Returns list of (start, end) tuples in chronological order (oldest first).
    """
    tf_key = str(timeframe)
    if tf_key not in _TIMEFRAMES:
        raise ValueError(f"Unsupported timeframe: {timeframe}")

    chunk_delta = timedelta(minutes=chunk_minutes)
    total_delta = timedelta(days=total_days)

    # Calculate the overall start point
    overall_start = end - total_delta

    chunks = []
    cursor = overall_start

    while cursor < end:
        chunk_end = min(cursor + chunk_delta, end)
        chunks.append((cursor, chunk_end))
        cursor = chunk_end

    return chunks


def run_seed_backfill(
    *,
    database_url: str,
    config: SeedConfig,
    resume: bool = False,
) -> dict[str, object]:
    """Run batched backfill with sleep/jitter between chunks.

    Args:
        database_url: PostgreSQL connection string
        config: Seed backfill configuration
        resume: If True, continue from latest candle in DB

    Returns:
        Summary dict with total_chunks, completed_chunks, total_fetched, total_upserted
    """
    stores = PostgresStores(config=PostgresConfig(database_url=database_url))

    # Determine the end point (now by default)
    end = datetime.now(tz=timezone.utc)

    # If resuming, check what we already have and adjust the backfill range
    if resume:
        latest = stores._get_latest_candle_open_time(
            exchange=config.exchange,
            symbol=config.symbol,
            timeframe=str(config.timeframe),
        )
        if latest is not None:
            # Normalize to UTC-aware
            if latest.tzinfo is None:
                latest = latest.replace(tzinfo=timezone.utc)

            # Calculate how far back we still need to go
            target_start = end - timedelta(days=config.days)

            if latest >= target_start:
                # We already have enough data
                print(f"seed-skip already_complete latest={latest.isoformat()}")
                return {
                    "total_chunks": 0,
                    "completed_chunks": 0,
                    "total_fetched": 0,
                    "total_upserted": 0,
                }

            # Resume from where we left off, but still respect the target lookback
            # We'll backfill from target_start to latest (filling the gap)
            end = latest
        # If latest is None, we'll backfill the full range from scratch

    # Calculate chunks
    chunks = _calculate_chunks(
        end=end,
        total_days=config.days,
        chunk_minutes=config.chunk_minutes,
        timeframe=config.timeframe,
    )

    total_chunks = len(chunks)
    completed_chunks = 0
    total_fetched = 0
    total_upserted = 0

    print(
        f"seed-start symbol={config.symbol} tf={config.timeframe} "
        f"chunks={total_chunks} chunk_min={config.chunk_minutes} sleep_s={config.sleep_seconds}"
    )

    for idx, (chunk_start, chunk_end) in enumerate(chunks, start=1):
        # Add jitter to sleep (±20%)
        if idx > 1 and config.sleep_seconds > 0:
            jitter_factor = JITTER_MIN + (random.random() * JITTER_RANGE)
            sleep_time = config.sleep_seconds * jitter_factor
            time.sleep(sleep_time)

        try:
            result = run_backfill(
                database_url=database_url,
                symbol=config.symbol,
                timeframe=config.timeframe,
                start=chunk_start,
                end=chunk_end,
                exchange=config.exchange,
                batch_size=1000,
            )
            completed_chunks += 1
            total_fetched += result["candles_fetched"]
            total_upserted += result["candles_upserted"]

            print(
                f"seed-chunk {idx}/{total_chunks} "
                f"start={chunk_start.isoformat()} end={chunk_end.isoformat()} "
                f"fetched={result['candles_fetched']} upserted={result['candles_upserted']}"
            )

        except Exception as exc:
            print(
                f"seed-chunk-fail {idx}/{total_chunks} "
                f"start={chunk_start.isoformat()} end={chunk_end.isoformat()} "
                f"error={str(exc)}"
            )
            raise

    print(
        f"seed-complete chunks={completed_chunks}/{total_chunks} " f"fetched={total_fetched} upserted={total_upserted}"
    )

    return {
        "total_chunks": total_chunks,
        "completed_chunks": completed_chunks,
        "total_fetched": total_fetched,
        "total_upserted": total_upserted,
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Seed historical candles in small batches with rate-limit friendly jitter."
    )
    parser.add_argument(
        "--symbol",
        required=True,
        help="Symbol without prefix, e.g. BTCUSD or BTC:USD",
    )
    parser.add_argument(
        "--timeframe",
        required=True,
        choices=sorted(_TIMEFRAMES.keys()),
        help="Candle timeframe",
    )
    parser.add_argument(
        "--days",
        type=int,
        required=True,
        help="Total lookback period in days (e.g. 7, 30)",
    )
    parser.add_argument(
        "--chunk-minutes",
        type=int,
        default=180,
        help="Size of each batch window in minutes (default: 180 = 3 hours)",
    )
    parser.add_argument(
        "--sleep-seconds",
        type=float,
        default=2.0,
        help="Sleep duration between chunks with ±20%% jitter (default: 2.0)",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from latest candle in DB (backfill only the missing gap to target lookback)",
    )
    parser.add_argument(
        "--exchange",
        default="bitfinex",
        help="Exchange code stored in DB (default: bitfinex)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL is not set")

    config = SeedConfig(
        symbol=args.symbol,
        timeframe=args.timeframe,
        days=args.days,
        chunk_minutes=args.chunk_minutes,
        sleep_seconds=args.sleep_seconds,
        exchange=args.exchange,
    )

    try:
        run_seed_backfill(
            database_url=database_url,
            config=config,
            resume=args.resume,
        )
        return 0
    except Exception as exc:
        print(f"seed-fail error={str(exc)}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
