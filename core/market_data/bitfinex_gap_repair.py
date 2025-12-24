from __future__ import annotations

import argparse
import os
import random
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Sequence

import requests

from core.storage import PostgresConfig, PostgresStores
from core.types import Candle, CandleGap, MarketDataJob, Timeframe


@dataclass(frozen=True)
class _TimeframeSpec:
    api: str
    delta: timedelta
    step_seconds: int


_TIMEFRAMES: dict[str, _TimeframeSpec] = {
    "1m": _TimeframeSpec(api="1m", delta=timedelta(minutes=1), step_seconds=60),
    "5m": _TimeframeSpec(api="5m", delta=timedelta(minutes=5), step_seconds=300),
    "15m": _TimeframeSpec(api="15m", delta=timedelta(minutes=15), step_seconds=900),
    "1h": _TimeframeSpec(api="1h", delta=timedelta(hours=1), step_seconds=3600),
    "4h": _TimeframeSpec(api="4h", delta=timedelta(hours=4), step_seconds=14400),
    "1d": _TimeframeSpec(api="1D", delta=timedelta(days=1), step_seconds=86400),
}


def _parse_dt(value: str) -> datetime:
    if len(value) == 10 and value[4] == "-" and value[7] == "-":
        dt = datetime.fromisoformat(value)
        return dt.replace(tzinfo=timezone.utc)

    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _align_to_step(dt: datetime, step_seconds: int) -> datetime:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    epoch = int(dt.timestamp())
    aligned = (epoch // step_seconds) * step_seconds
    return datetime.fromtimestamp(aligned, tz=timezone.utc)


def _to_ms(dt: datetime) -> int:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def _normalize_bitfinex_symbol(symbol: str) -> str:
    s = symbol.strip()
    if not s:
        raise ValueError("symbol is required")
    if not s.startswith("t"):
        s = "t" + s
    return s


def _fetch_bitfinex_candles_page(
    *,
    symbol: str,
    timeframe_api: str,
    start_ms: int,
    end_ms: int,
    limit: int = 10_000,
    sort: int = 1,
    timeout_s: int = 20,
    max_retries: int = 6,
    initial_backoff_seconds: float = 0.5,
    max_backoff_seconds: float = 8.0,
    jitter_seconds: float = 0.0,
) -> list[list[object]]:
    url = f"https://api-pub.bitfinex.com/v2/candles/trade:{timeframe_api}:{symbol}/hist"
    params = {
        "start": str(start_ms),
        "end": str(end_ms),
        "limit": str(limit),
        "sort": str(sort),
    }

    backoff = initial_backoff_seconds
    last_err: Exception | None = None

    for _ in range(max_retries):
        try:
            resp = requests.get(url, params=params, timeout=timeout_s)
            if resp.status_code == 429:
                last_err = RuntimeError("Bitfinex candle fetch failed: HTTP 429 rate limiting")
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
        raise RuntimeError("Bitfinex candle fetch failed: exhausted retries")
    raise RuntimeError("Bitfinex candle fetch failed") from last_err


def _fetch_single_candle(
    *,
    exchange: str,
    symbol: str,
    timeframe: Timeframe,
    open_time: datetime,
    max_retries: int = 6,
    initial_backoff_seconds: float = 0.5,
    max_backoff_seconds: float = 8.0,
    jitter_seconds: float = 0.0,
) -> Candle | None:
    tf_key = str(timeframe)
    if tf_key not in _TIMEFRAMES:
        raise ValueError(f"Unsupported timeframe: {timeframe}")

    spec = _TIMEFRAMES[tf_key]
    if open_time.tzinfo is None:
        open_time = open_time.replace(tzinfo=timezone.utc)
    start_ms = _to_ms(open_time)
    end_ms = _to_ms(open_time + spec.delta)

    try:
        page = _fetch_bitfinex_candles_page(
            symbol=_normalize_bitfinex_symbol(symbol),
            timeframe_api=spec.api,
            start_ms=start_ms,
            end_ms=end_ms,
            limit=1,
            sort=1,
            max_retries=max_retries,
            initial_backoff_seconds=initial_backoff_seconds,
            max_backoff_seconds=max_backoff_seconds,
            jitter_seconds=jitter_seconds,
        )
    except Exception:
        # Treat transient upstream failures as a skip; the timer will retry later.
        return None
    if not page:
        return None

    row = page[0]
    mts = int(row[0])
    actual_open_time = datetime.fromtimestamp(mts / 1000, tz=timezone.utc)
    close_time = actual_open_time + spec.delta

    return Candle(
        exchange=exchange,
        symbol=symbol,
        timeframe=timeframe,
        open_time=actual_open_time,
        close_time=close_time,
        open=Decimal(str(row[1])),
        close=Decimal(str(row[2])),
        high=Decimal(str(row[3])),
        low=Decimal(str(row[4])),
        volume=Decimal(str(row[5])),
    )


def _find_missing_open_times(
    *,
    stores: PostgresStores,
    exchange: str,
    symbol: str,
    timeframe: Timeframe,
    start: datetime,
    end: datetime,
) -> list[datetime]:
    """Detect missing candles using Postgres generate_series for the timeframe step."""

    tf_key = str(timeframe)
    if tf_key not in _TIMEFRAMES:
        raise ValueError(f"Unsupported timeframe: {timeframe}")

    spec = _TIMEFRAMES[tf_key]

    engine = stores._get_engine()  # internal but OK within package
    _, text = stores._require_sqlalchemy()  # internal

    stmt = text(
        """
        WITH expected AS (
            SELECT generate_series(
                :start_time,
                :end_time,
                ((:step_seconds)::text || ' seconds')::interval
            ) AS open_time
        ), actual AS (
            SELECT open_time
            FROM candles
            WHERE exchange = :exchange
              AND symbol = :symbol
              AND timeframe = :timeframe
              AND open_time >= :start_time
              AND open_time <= :end_time
        )
        SELECT expected.open_time
        FROM expected
        LEFT JOIN actual USING(open_time)
        WHERE actual.open_time IS NULL
        ORDER BY expected.open_time ASC
        """
    )

    with engine.begin() as conn:
        rows = conn.execute(
            stmt,
            {
                "exchange": exchange,
                "symbol": symbol,
                "timeframe": str(timeframe),
                "start_time": start,
                "end_time": end,
                "step_seconds": spec.step_seconds,
            },
        ).fetchall()

    return [row[0] for row in rows]


def run_gap_repair(
    *,
    database_url: str,
    symbol: str,
    timeframe: Timeframe,
    start: datetime,
    end: datetime,
    exchange: str = "bitfinex",
    repair: bool = True,
    max_repairs: int = 10_000,
    max_retries: int = 6,
    initial_backoff_seconds: float = 0.5,
    max_backoff_seconds: float = 8.0,
    jitter_seconds: float = 0.0,
) -> dict[str, int]:
    tf_key = str(timeframe)
    if tf_key not in _TIMEFRAMES:
        raise ValueError(f"Unsupported timeframe for gap repair: {timeframe}")

    spec = _TIMEFRAMES[tf_key]
    start_aligned = _align_to_step(start, spec.step_seconds)
    end_aligned = _align_to_step(end, spec.step_seconds)

    stores = PostgresStores(config=PostgresConfig(database_url=database_url))

    job_id = stores.create_job(
        job=MarketDataJob(
            job_type="repair",
            exchange=exchange,
            symbol=symbol,
            timeframe=timeframe,
            start_time=start_aligned,
            end_time=end_aligned,
            status="running",
        )
    )
    run_id = stores.start_run(job_id=job_id)

    detected_gaps = 0
    repaired_gaps = 0
    candles_fetched = 0
    candles_upserted = 0

    try:
        missing = _find_missing_open_times(
            stores=stores,
            exchange=exchange,
            symbol=symbol,
            timeframe=timeframe,
            start=start_aligned,
            end=end_aligned,
        )

        for open_time in missing[:max_repairs]:
            gap_id = stores.log_gap(
                gap=CandleGap(
                    exchange=exchange,
                    symbol=symbol,
                    timeframe=timeframe,
                    expected_open_time=open_time,
                    expected_close_time=open_time + spec.delta,
                    detected_at=datetime.now(tz=timezone.utc),
                    notes="auto-detected",
                )
            )
            detected_gaps += 1

            if not repair:
                continue

            candle = _fetch_single_candle(
                exchange=exchange,
                symbol=symbol,
                timeframe=timeframe,
                open_time=open_time,
                max_retries=max_retries,
                initial_backoff_seconds=initial_backoff_seconds,
                max_backoff_seconds=max_backoff_seconds,
                jitter_seconds=jitter_seconds,
            )
            if candle is None:
                continue

            candles_fetched += 1
            candles_upserted += stores.upsert_candles(candles=[candle])
            stores.mark_repaired(gap_id=gap_id, repaired_at=datetime.now(tz=timezone.utc), notes="auto-repaired")
            repaired_gaps += 1

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
        "gaps_detected": int(detected_gaps),
        "gaps_repaired": int(repaired_gaps),
        "candles_fetched": int(candles_fetched),
        "candles_upserted": int(candles_upserted),
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Detect and repair missing candles in Postgres using Bitfinex.")
    parser.add_argument("--symbol", required=True, help="Symbol without prefix, e.g. BTCUSD or BTC:USD")
    parser.add_argument("--timeframe", required=True, choices=sorted(_TIMEFRAMES.keys()), help="Candle timeframe")
    parser.add_argument("--start", help="ISO datetime/date (UTC assumed if no tz)")
    parser.add_argument("--end", help="ISO datetime/date (UTC assumed if no tz). Default: now (UTC)")
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Use a DB-driven default range (end=now, start=end-lookback-days) instead of specifying --start/--end.",
    )
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=30,
        help="Only used with --resume. Default: 30",
    )
    parser.add_argument("--exchange", default="bitfinex", help="Exchange code stored in DB")
    parser.add_argument("--detect-only", action="store_true", help="Only detect and log gaps; do not fetch missing candles")
    parser.add_argument("--max", type=int, default=10_000, help="Max number of gaps to process")
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
        if args.lookback_days <= 0:
            raise SystemExit("--lookback-days must be > 0")
        start = end - timedelta(days=int(args.lookback_days))
    else:
        if not args.start:
            raise SystemExit("--start is required unless --resume is set")
        start = _parse_dt(args.start)

    if end <= start:
        raise SystemExit("end must be after start")

    result = run_gap_repair(
        database_url=database_url,
        symbol=args.symbol,
        timeframe=args.timeframe,
        start=start,
        end=end,
        exchange=args.exchange,
        repair=not args.detect_only,
        max_repairs=args.max,
        max_retries=args.max_retries,
        initial_backoff_seconds=args.initial_backoff_seconds,
        max_backoff_seconds=args.max_backoff_seconds,
        jitter_seconds=args.jitter_seconds,
    )

    print(
        f"gap-repair-ok job_id={result['job_id']} run_id={result['run_id']} "
        f"gaps_detected={result['gaps_detected']} gaps_repaired={result['gaps_repaired']} "
        f"candles_fetched={result['candles_fetched']} candles_upserted={result['candles_upserted']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
