from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Iterable

import requests

from core.market_data.base import ExchangeProvider, TimeframeSpec
from core.types import Candle, Timeframe


class BitfinexProvider(ExchangeProvider):
    """Bitfinex exchange data provider."""

    _TIMEFRAMES: dict[str, TimeframeSpec] = {
        "1m": TimeframeSpec(api="1m", delta=timedelta(minutes=1), step_ms=60_000),
        "5m": TimeframeSpec(api="5m", delta=timedelta(minutes=5), step_ms=300_000),
        "15m": TimeframeSpec(api="15m", delta=timedelta(minutes=15), step_ms=900_000),
        "1h": TimeframeSpec(api="1h", delta=timedelta(hours=1), step_ms=3_600_000),
        "4h": TimeframeSpec(api="4h", delta=timedelta(hours=4), step_ms=14_400_000),
        "1d": TimeframeSpec(api="1D", delta=timedelta(days=1), step_ms=86_400_000),
    }

    @property
    def exchange_name(self) -> str:
        return "bitfinex"

    def get_timeframe_spec(self, timeframe: Timeframe) -> TimeframeSpec:
        tf_key = str(timeframe)
        if tf_key not in self._TIMEFRAMES:
            raise ValueError(f"Unsupported timeframe for Bitfinex: {timeframe}")
        return self._TIMEFRAMES[tf_key]

    def _normalize_symbol(self, symbol: str) -> str:
        """Add 't' prefix if missing."""
        s = symbol.strip()
        if not s:
            raise ValueError("symbol is required")
        if not s.startswith("t"):
            s = "t" + s
        return s

    def _to_ms(self, dt: datetime) -> int:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp() * 1000)

    def _fetch_page(
        self,
        *,
        symbol: str,
        timeframe_api: str,
        start_ms: int,
        end_ms: int,
        limit: int = 10_000,
        sort: int = 1,
        timeout_s: int = 20,
        max_retries: int = 6,
    ) -> list[list[object]]:
        """Fetch one page from Bitfinex candles endpoint."""
        url = f"https://api-pub.bitfinex.com/v2/candles/trade:{timeframe_api}:{symbol}/hist"
        params = {
            "start": str(start_ms),
            "end": str(end_ms),
            "limit": str(limit),
            "sort": str(sort),
        }

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
                if not isinstance(data, list):
                    raise RuntimeError(f"Unexpected response type: {type(data)}")
                return data
            except Exception as exc:
                last_err = exc
                time.sleep(backoff)
                backoff = min(8.0, backoff * 2)

        raise RuntimeError("Bitfinex candle fetch failed") from last_err

    def iter_candles(
        self,
        *,
        symbol: str,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
    ) -> Iterable[Candle]:
        spec = self.get_timeframe_spec(timeframe)
        start_ms = self._to_ms(start)
        end_ms = self._to_ms(end)

        cursor_ms = start_ms
        while cursor_ms <= end_ms:
            page = self._fetch_page(
                symbol=self._normalize_symbol(symbol),
                timeframe_api=spec.api,
                start_ms=cursor_ms,
                end_ms=end_ms,
                limit=10_000,
                sort=1,
            )

            if not page:
                break

            # Oldest-first when sort=1
            # Response format: [MTS, OPEN, CLOSE, HIGH, LOW, VOLUME]
            for row in page:
                mts = int(row[0])
                open_time = datetime.fromtimestamp(mts / 1000, tz=timezone.utc)
                close_time = open_time + spec.delta
                yield Candle(
                    exchange=self.exchange_name,
                    symbol=symbol,
                    timeframe=timeframe,
                    open_time=open_time,
                    close_time=close_time,
                    open=Decimal(str(row[1])),
                    close=Decimal(str(row[2])),
                    high=Decimal(str(row[3])),
                    low=Decimal(str(row[4])),
                    volume=Decimal(str(row[5])),
                )

            last_ts_ms = int(page[-1][0])
            next_cursor = last_ts_ms + spec.step_ms
            if next_cursor <= cursor_ms:
                next_cursor = cursor_ms + spec.step_ms
            cursor_ms = next_cursor
