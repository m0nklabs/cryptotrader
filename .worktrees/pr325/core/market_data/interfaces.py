from __future__ import annotations

from typing import Protocol, Sequence

from core.types import Candle, Timeframe


class CandleProvider(Protocol):
    """Fetches OHLCV candles for a symbol/timeframe."""

    def fetch_candles(self, *, symbol: str, timeframe: Timeframe, limit: int) -> Sequence[Candle]:
        raise NotImplementedError
