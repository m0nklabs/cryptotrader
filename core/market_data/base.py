from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable, Protocol

from core.types import Candle, Timeframe


@dataclass(frozen=True)
class TimeframeSpec:
    """Timeframe configuration for exchange adapters."""

    api: str
    delta: timedelta
    step_ms: int


class ExchangeAdapter(Protocol):
    """Protocol for market data exchange adapters."""

    def fetch_ohlcv(
        self,
        *,
        symbol: str,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
    ) -> Iterable[Candle]:
        """Fetch OHLCV candles for the requested window."""

    def normalize_symbol(self, symbol: str) -> str:
        """Normalize the symbol to the exchange-specific format."""
