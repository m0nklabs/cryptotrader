#!/usr/bin/env python
from __future__ import annotations

import argparse
import time
from datetime import datetime, timezone

import requests


_TIMEFRAMES_API: dict[str, str] = {
    "1m": "1m",
    "5m": "5m",
    "15m": "15m",
    "1h": "1h",
    "4h": "4h",
    "1d": "1D",
}


def _normalize_bitfinex_symbol(symbol: str) -> str:
    s = symbol.strip()
    if not s:
        raise SystemExit("symbol is required")
    if not s.startswith("t"):
        s = "t" + s
    return s


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Smoke-test Bitfinex public candle endpoint (no DB).")
    p.add_argument("--symbol", required=True, help="Symbol like BTCUSD (or tBTCUSD)")
    p.add_argument("--timeframe", default="1m", choices=sorted(_TIMEFRAMES_API.keys()))
    p.add_argument("--minutes", type=int, default=10, help="Lookback window in minutes")
    p.add_argument("--limit", type=int, default=10, help="Max rows to request")
    return p.parse_args()


def main() -> int:
    args = _parse_args()

    symbol = _normalize_bitfinex_symbol(args.symbol)
    tf_api = _TIMEFRAMES_API[args.timeframe]

    now_ms = int(time.time() * 1000)
    start_ms = now_ms - int(args.minutes * 60_000)

    url = f"https://api-pub.bitfinex.com/v2/candles/trade:{tf_api}:{symbol}/hist"
    params = {
        "start": str(start_ms),
        "end": str(now_ms),
        "limit": str(args.limit),
        "sort": "1",
    }

    r = requests.get(url, params=params, timeout=20)
    print(f"status={r.status_code}")
    r.raise_for_status()

    data = r.json()
    if not isinstance(data, list):
        raise RuntimeError(f"Unexpected response type: {type(data)}")

    print(f"rows={len(data)}")
    if data:
        first_mts = int(data[0][0])
        last_mts = int(data[-1][0])
        first_dt = datetime.fromtimestamp(first_mts / 1000, tz=timezone.utc)
        last_dt = datetime.fromtimestamp(last_mts / 1000, tz=timezone.utc)
        print(f"first_open_time_utc={first_dt.isoformat()}")
        print(f"last_open_time_utc={last_dt.isoformat()}")
        print(f"first_row={data[0]}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
