from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable

from core.types import Candle, Timeframe


@dataclass(frozen=True)
class TimeframeSpec:
    """Common timeframe specification across exchanges."""

    api: str  # API-specific timeframe string
    delta: timedelta  # Time delta for one candle
    step_ms: int  # Step in milliseconds


class ExchangeProvider(ABC):
    """Abstract base class for exchange market data providers."""

    @property
    @abstractmethod
    def exchange_name(self) -> str:
        """Return the exchange identifier (e.g., 'bitfinex', 'binance')."""
        raise NotImplementedError

    @abstractmethod
    def get_timeframe_spec(self, timeframe: Timeframe) -> TimeframeSpec:
        """Get the timeframe specification for this exchange."""
        raise NotImplementedError

    @abstractmethod
    def iter_candles(
        self,
        *,
        symbol: str,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
    ) -> Iterable[Candle]:
        """Iterate over candles for the given symbol and timeframe."""
        raise NotImplementedError
