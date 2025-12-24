from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Iterable

import requests

from core.market_data.base import ExchangeProvider, TimeframeSpec
from core.types import Candle, Timeframe


class KrakenProvider(ExchangeProvider):
    """Kraken exchange data provider."""

    _TIMEFRAMES: dict[str, TimeframeSpec] = {
        "1m": TimeframeSpec(api="1", delta=timedelta(minutes=1), step_ms=60_000),
        "5m": TimeframeSpec(api="5", delta=timedelta(minutes=5), step_ms=300_000),
        "15m": TimeframeSpec(api="15", delta=timedelta(minutes=15), step_ms=900_000),
        "1h": TimeframeSpec(api="60", delta=timedelta(hours=1), step_ms=3_600_000),
        "4h": TimeframeSpec(api="240", delta=timedelta(hours=4), step_ms=14_400_000),
        "1d": TimeframeSpec(api="1440", delta=timedelta(days=1), step_ms=86_400_000),
    }

    @property
    def exchange_name(self) -> str:
        return "kraken"

    def get_timeframe_spec(self, timeframe: Timeframe) -> TimeframeSpec:
        tf_key = str(timeframe)
        if tf_key not in self._TIMEFRAMES:
            raise ValueError(f"Unsupported timeframe for Kraken: {timeframe}")
        return self._TIMEFRAMES[tf_key]

    def _normalize_symbol(self, symbol: str) -> str:
        """Normalize symbol for Kraken API (e.g., BTCUSD -> XXBTZUSD)."""
        s = symbol.strip().upper()
        if not s:
            raise ValueError("symbol is required")
        
        # Kraken uses X prefix for crypto and Z prefix for fiat
        # Common mappings for major pairs
        symbol_map = {
            "BTCUSD": "XXBTZUSD",
            "BTCEUR": "XXBTZEUR",
            "ETHUSD": "XETHZUSD",
            "ETHEUR": "XETHZEUR",
            "XRPUSD": "XXRPZUSD",
            "XRPEUR": "XXRPZEUR",
        }
        
        return symbol_map.get(s, s)

    def _to_ms(self, dt: datetime) -> int:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp() * 1000)

    def _fetch_page(
        self,
        *,
        symbol: str,
        interval: str,
        since: int | None = None,
        timeout_s: int = 20,
        max_retries: int = 6,
    ) -> dict[str, object]:
        """Fetch candles from Kraken API.
        
        Response format: {
            "error": [],
            "result": {
                "PAIR": [[time, open, high, low, close, vwap, volume, count], ...],
                "last": timestamp
            }
        }
        """
        url = "https://api.kraken.com/0/public/OHLC"
        params = {
            "pair": symbol,
            "interval": interval,
        }
        if since is not None:
            params["since"] = str(since)

        backoff = 0.5
        last_err: Exception | None = None

        for _ in range(max_retries):
            try:
                resp = requests.get(url, params=params, timeout=timeout_s)
                if resp.status_code == 429:
                    time.sleep(backoff)
                    backoff = min(8.0, backoff * 2)
                    continue
                resp.raise_for_status()
                data = resp.json()
                if not isinstance(data, dict):
                    raise RuntimeError(f"Unexpected response type: {type(data)}")
                
                # Check for API errors
                if data.get("error") and len(data["error"]) > 0:
                    raise RuntimeError(f"Kraken API error: {data['error']}")
                
                return data
            except Exception as exc:
                last_err = exc
                time.sleep(backoff)
                backoff = min(8.0, backoff * 2)

        raise RuntimeError("Kraken candle fetch failed") from last_err

    def iter_candles(
        self,
        *,
        symbol: str,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
    ) -> Iterable[Candle]:
        spec = self.get_timeframe_spec(timeframe)
        start_ts = int(start.timestamp())
        end_ts = int(end.timestamp())

        normalized_symbol = self._normalize_symbol(symbol)
        cursor_ts = start_ts
        
        while cursor_ts <= end_ts:
            data = self._fetch_page(
                symbol=normalized_symbol,
                interval=spec.api,
                since=cursor_ts,
            )

            result = data.get("result", {})
            if not result:
                break

            # The result contains the pair data under a key (which may vary)
            # Extract the first non-"last" key
            candles_key = None
            for key in result.keys():
                if key != "last":
                    candles_key = key
                    break

            if not candles_key:
                break

            candles_data = result[candles_key]
            if not isinstance(candles_data, list) or not candles_data:
                break

            # Response: [time, open, high, low, close, vwap, volume, count]
            for row in candles_data:
                open_time_ts = int(row[0])
                
                # Skip candles beyond our end time
                if open_time_ts > end_ts:
                    return
                
                open_time = datetime.fromtimestamp(open_time_ts, tz=timezone.utc)
                close_time = open_time + spec.delta
                
                yield Candle(
                    exchange=self.exchange_name,
                    symbol=symbol,
                    timeframe=timeframe,
                    open_time=open_time,
                    close_time=close_time,
                    open=Decimal(str(row[1])),
                    high=Decimal(str(row[2])),
                    low=Decimal(str(row[3])),
                    close=Decimal(str(row[4])),
                    volume=Decimal(str(row[6])),
                )

            # Move cursor using the "last" timestamp
            last_ts = result.get("last")
            if last_ts and isinstance(last_ts, (int, float)):
                next_cursor = int(last_ts)
                if next_cursor <= cursor_ts:
                    # Prevent infinite loop
                    next_cursor = cursor_ts + (spec.step_ms // 1000)
                cursor_ts = next_cursor
            else:
                # No more data
                break
