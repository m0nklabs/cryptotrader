"""Binance exchange adapter for OHLCV candle backfill.

This module implements the ExchangeAdapter protocol for Binance,
fetching historical candle data via the Binance public REST API.
"""

from __future__ import annotations

import argparse
import os
import random
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Iterable, Sequence

import requests

from core.market_data.base import TimeframeSpec
from core.storage import PostgresConfig, PostgresStores
from core.types import Candle, MarketDataJob, Timeframe


# Binance-specific timeframe mappings
_BINANCE_TIMEFRAMES: dict[str, TimeframeSpec] = {
    "1m": TimeframeSpec(api="1m", delta=timedelta(minutes=1), step_ms=60_000),
    "5m": TimeframeSpec(api="5m", delta=timedelta(minutes=5), step_ms=300_000),
    "15m": TimeframeSpec(api="15m", delta=timedelta(minutes=15), step_ms=900_000),
    "1h": TimeframeSpec(api="1h", delta=timedelta(hours=1), step_ms=3_600_000),
    "4h": TimeframeSpec(api="4h", delta=timedelta(hours=4), step_ms=14_400_000),
    "1d": TimeframeSpec(api="1d", delta=timedelta(days=1), step_ms=86_400_000),
}


def _parse_dt(value: str) -> datetime:
    """Parse ISO date/datetime and return timezone-aware UTC datetime."""
    # Accept YYYY-MM-DD
    if len(value) == 10 and value[4] == "-" and value[7] == "-":
        dt = datetime.fromisoformat(value)
        return dt.replace(tzinfo=timezone.utc)

    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _to_ms(dt: datetime) -> int:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def _normalize_binance_symbol(symbol: str) -> str:
    """Normalize symbol for Binance API.

    Binance uses uppercase symbols without separators (e.g., BTCUSDT).
    """
    s = symbol.strip().upper().replace("/", "").replace(":", "")
    if not s:
        raise ValueError("symbol is required")
    # Convert common variants to Binance format
    if s.endswith("USD") and not s.endswith("USDT"):
        s = s[:-3] + "USDT"  # Convert BTCUSD to BTCUSDT
    return s


def _fetch_binance_candles_page(
    *,
    symbol: str,
    timeframe_api: str,
    start_ms: int,
    end_ms: int,
    limit: int = 1000,
    timeout_s: int = 20,
    max_retries: int = 6,
    initial_backoff_seconds: float = 0.5,
    max_backoff_seconds: float = 8.0,
    jitter_seconds: float = 0.0,
) -> list[list]:
    """Fetch one page from Binance klines endpoint.

    Response format: [[openTime, open, high, low, close, volume, closeTime, ...], ...]
    """
    url = "https://api.binance.com/api/v3/klines"
    params = {
        "symbol": symbol,
        "interval": timeframe_api,
        "startTime": str(start_ms),
        "endTime": str(end_ms),
        "limit": str(limit),
    }

    backoff = initial_backoff_seconds
    last_err: Exception | None = None

    for _ in range(max_retries):
        try:
            resp = requests.get(url, params=params, timeout=timeout_s)
            if resp.status_code == 429:
                last_err = RuntimeError("Binance candle fetch failed: HTTP 429 rate limiting")
                jitter = random.uniform(0, jitter_seconds) if jitter_seconds > 0 else 0
                time.sleep(backoff + jitter)
                backoff = min(max_backoff_seconds, backoff * 2)
                continue
            resp.raise_for_status()
            data = resp.json()
            if not isinstance(data, list):
                raise RuntimeError(f"Unexpected response type: {type(data)}")
            return data
        except Exception as exc:
            last_err = exc
            jitter = random.uniform(0, jitter_seconds) if jitter_seconds > 0 else 0
            time.sleep(backoff + jitter)
            backoff = min(max_backoff_seconds, backoff * 2)

    if last_err is None:
        raise RuntimeError("Binance candle fetch failed: exhausted retries")
    raise RuntimeError("Binance candle fetch failed") from last_err


def _iter_binance_candles(
    *,
    exchange: str,
    symbol: str,
    timeframe: Timeframe,
    start: datetime,
    end: datetime,
    max_retries: int = 6,
    initial_backoff_seconds: float = 0.5,
    max_backoff_seconds: float = 8.0,
    jitter_seconds: float = 0.0,
) -> Iterable[Candle]:
    """Iterate over Binance candles for the given time range."""
    tf_key = str(timeframe)
    if tf_key not in _BINANCE_TIMEFRAMES:
        raise ValueError(f"Unsupported timeframe for Binance backfill: {timeframe}")

    spec = _BINANCE_TIMEFRAMES[tf_key]
    start_ms = _to_ms(start)
    end_ms = _to_ms(end)

    cursor_ms = start_ms
    while cursor_ms <= end_ms:
        page = _fetch_binance_candles_page(
            symbol=_normalize_binance_symbol(symbol),
            timeframe_api=spec.api,
            start_ms=cursor_ms,
            end_ms=end_ms,
            limit=1000,  # Binance max is 1000
            max_retries=max_retries,
            initial_backoff_seconds=initial_backoff_seconds,
            max_backoff_seconds=max_backoff_seconds,
            jitter_seconds=jitter_seconds,
        )

        if not page:
            break

        for row in page:
            # Binance klines format:
            # [openTime, open, high, low, close, volume, closeTime, quoteVolume, trades, ...]
            open_time_ms = int(row[0])
            close_time_ms = int(row[6])
            open_time = datetime.fromtimestamp(open_time_ms / 1000, tz=timezone.utc)
            close_time = datetime.fromtimestamp(close_time_ms / 1000, tz=timezone.utc)

            yield Candle(
                exchange=exchange,
                symbol=symbol,
                timeframe=timeframe,
                open_time=open_time,
                close_time=close_time,
                open=Decimal(str(row[1])),
                high=Decimal(str(row[2])),
                low=Decimal(str(row[3])),
                close=Decimal(str(row[4])),
                volume=Decimal(str(row[5])),
            )

        # Move to next page
        last_close_time = int(page[-1][6])
        next_cursor = last_close_time + 1  # Start from next millisecond
        if next_cursor <= cursor_ms:
            # Safety against infinite loops
            next_cursor = cursor_ms + spec.step_ms
        cursor_ms = next_cursor


def _batched(items: Iterable[Candle], batch_size: int) -> Iterable[list[Candle]]:
    batch: list[Candle] = []
    for item in items:
        batch.append(item)
        if len(batch) >= batch_size:
            yield batch
            batch = []
    if batch:
        yield batch


def run_backfill(
    *,
    database_url: str,
    symbol: str,
    timeframe: Timeframe,
    start: datetime,
    end: datetime,
    exchange: str = "binance",
    batch_size: int = 1000,
    max_retries: int = 6,
    initial_backoff_seconds: float = 0.5,
    max_backoff_seconds: float = 8.0,
    jitter_seconds: float = 0.0,
) -> dict[str, int]:
    """Run Binance candle backfill and store in database.

    Args:
        database_url: PostgreSQL connection string
        symbol: Trading pair symbol (e.g., BTCUSDT or BTCUSD)
        timeframe: Candle timeframe
        start: Start datetime (UTC)
        end: End datetime (UTC)
        exchange: Exchange identifier (default: "binance")
        batch_size: Number of candles to batch for DB upserts
        max_retries: Maximum retry attempts
        initial_backoff_seconds: Initial backoff delay
        max_backoff_seconds: Maximum backoff delay
        jitter_seconds: Random jitter for backoff

    Returns:
        Dictionary with job_id, run_id, candles_fetched, candles_upserted
    """
    stores = PostgresStores(config=PostgresConfig(database_url=database_url))

    job_id = stores.create_job(
        job=MarketDataJob(
            job_type="backfill",
            exchange=exchange,
            symbol=symbol,
            timeframe=timeframe,
            start_time=start,
            end_time=end,
            status="running",
        )
    )
    run_id = stores.start_run(job_id=job_id)

    candles_fetched = 0
    candles_upserted = 0

    try:
        candle_iter = _iter_binance_candles(
            exchange=exchange,
            symbol=symbol,
            timeframe=timeframe,
            start=start,
            end=end,
            max_retries=max_retries,
            initial_backoff_seconds=initial_backoff_seconds,
            max_backoff_seconds=max_backoff_seconds,
            jitter_seconds=jitter_seconds,
        )
        for batch in _batched(candle_iter, batch_size=batch_size):
            candles_fetched += len(batch)
            candles_upserted += stores.upsert_candles(candles=batch)

        stores.finish_run(
            run_id=run_id,
            status="success",
            candles_fetched=candles_fetched,
            candles_upserted=candles_upserted,
        )
        stores.update_job_status(job_id=job_id, status="success")

    except Exception as exc:
        stores.finish_run(
            run_id=run_id,
            status="failed",
            candles_fetched=candles_fetched,
            candles_upserted=candles_upserted,
            last_error=str(exc),
        )
        stores.update_job_status(job_id=job_id, status="failed", last_error=str(exc))
        raise

    return {
        "job_id": int(job_id),
        "run_id": int(run_id),
        "candles_fetched": int(candles_fetched),
        "candles_upserted": int(candles_upserted),
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Backfill OHLCV candles from Binance into Postgres.")
    parser.add_argument("--symbol", required=True, help="Symbol (e.g., BTCUSDT, BTCUSD)")
    parser.add_argument("--timeframe", required=True, choices=sorted(_BINANCE_TIMEFRAMES.keys()), help="Candle timeframe")
    parser.add_argument("--start", help="ISO datetime/date (UTC assumed if no tz)")
    parser.add_argument("--end", help="ISO datetime/date (UTC assumed if no tz). Default: now (UTC)")
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from the latest candle in DB (start = latest_open_time + timeframe).",
    )
    parser.add_argument("--exchange", default="binance", help="Exchange code stored in DB")
    parser.add_argument("--batch-size", type=int, default=1000, help="DB upsert batch size")
    parser.add_argument(
        "--max-retries",
        type=int,
        default=6,
        help="Maximum number of retry attempts for API requests (default: 6)",
    )
    parser.add_argument(
        "--initial-backoff-seconds",
        type=float,
        default=0.5,
        help="Initial backoff delay in seconds before retrying (default: 0.5)",
    )
    parser.add_argument(
        "--max-backoff-seconds",
        type=float,
        default=8.0,
        help="Maximum backoff delay in seconds (backoff doubles each retry up to this cap) (default: 8.0)",
    )
    parser.add_argument(
        "--jitter-seconds",
        type=float,
        default=0.0,
        help="Maximum random jitter in seconds added to backoff delay (default: 0.0)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    if args.max_retries <= 0:
        parser.error("--max-retries must be > 0")
    if args.initial_backoff_seconds < 0:
        parser.error("--initial-backoff-seconds must be >= 0")
    if args.max_backoff_seconds < 0:
        parser.error("--max-backoff-seconds must be >= 0")
    if args.initial_backoff_seconds > args.max_backoff_seconds:
        parser.error("--initial-backoff-seconds must be <= --max-backoff-seconds")
    if args.jitter_seconds < 0:
        parser.error("--jitter-seconds must be >= 0")

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL is not set")

    end = _parse_dt(args.end) if args.end else datetime.now(tz=timezone.utc)

    if args.resume:
        stores = PostgresStores(config=PostgresConfig(database_url=database_url))
        latest = stores._get_latest_candle_open_time(
            exchange=args.exchange,
            symbol=args.symbol,
            timeframe=str(args.timeframe),
        )
        if latest is None:
            raise SystemExit("No existing candles found to resume from; provide --start for the initial backfill")
        if latest.tzinfo is None:
            latest = latest.replace(tzinfo=timezone.utc)
        start = latest + _BINANCE_TIMEFRAMES[str(args.timeframe)].delta
    else:
        if not args.start:
            raise SystemExit("--start is required unless --resume is set")
        start = _parse_dt(args.start)

    if end <= start:
        if args.resume:
            print("backfill-skip start_after_end")
            return 0
        raise SystemExit("end must be after start")

    result = run_backfill(
        database_url=database_url,
        symbol=args.symbol,
        timeframe=args.timeframe,
        start=start,
        end=end,
        exchange=args.exchange,
        batch_size=args.batch_size,
        max_retries=args.max_retries,
        initial_backoff_seconds=args.initial_backoff_seconds,
        max_backoff_seconds=args.max_backoff_seconds,
        jitter_seconds=args.jitter_seconds,
    )

    print(
        f"backfill-ok job_id={result['job_id']} run_id={result['run_id']} "
        f"fetched={result['candles_fetched']} upserted={result['candles_upserted']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
