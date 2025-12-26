"""Abstract exchange interface for market data ingestion.

This module defines the base protocol for exchange adapters that fetch
OHLCV candle data. Each exchange implementation should conform to this
interface to enable consistent multi-exchange support.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable, Protocol

from core.types import Candle, Timeframe


@dataclass(frozen=True)
class TimeframeSpec:
    """Specification for a timeframe including API representation and duration."""

    api: str  # Exchange-specific API identifier (e.g., "1m", "1h", "1D")
    delta: timedelta  # Duration of one candle
    step_ms: int  # Duration in milliseconds


class ExchangeAdapter(Protocol):
    """Protocol for exchange market data adapters.

    Each exchange implementation must provide methods to:
    - Fetch candles for a given symbol and timeframe
    - Normalize symbol names to exchange-specific format
    - Define supported timeframes
    """

    def fetch_candles(
        self,
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
        """Fetch candles for the given parameters.

        Args:
            exchange: Exchange identifier (e.g., "binance", "bitfinex")
            symbol: Trading pair symbol (e.g., "BTCUSD", "BTC/USDT")
            timeframe: Candle timeframe
            start: Start datetime (UTC)
            end: End datetime (UTC)
            max_retries: Maximum number of retry attempts
            initial_backoff_seconds: Initial backoff delay
            max_backoff_seconds: Maximum backoff delay
            jitter_seconds: Random jitter added to backoff

        Returns:
            Iterator of Candle objects

        Raises:
            RuntimeError: If fetching fails after retries
            ValueError: If parameters are invalid
        """
        raise NotImplementedError

    def normalize_symbol(self, symbol: str) -> str:
        """Normalize symbol to exchange-specific format.

        Args:
            symbol: Raw symbol string

        Returns:
            Normalized symbol for this exchange's API

        Raises:
            ValueError: If symbol is empty or invalid
        """
        raise NotImplementedError

    def get_timeframe_spec(self, timeframe: Timeframe) -> TimeframeSpec:
        """Get timeframe specification for this exchange.

        Args:
            timeframe: Standard timeframe identifier

        Returns:
            TimeframeSpec with exchange-specific details

        Raises:
            ValueError: If timeframe is not supported
        """
        raise NotImplementedError


# Common timeframe specifications (can be overridden by exchange adapters)
COMMON_TIMEFRAMES: dict[str, TimeframeSpec] = {
    "1m": TimeframeSpec(api="1m", delta=timedelta(minutes=1), step_ms=60_000),
    "5m": TimeframeSpec(api="5m", delta=timedelta(minutes=5), step_ms=300_000),
    "15m": TimeframeSpec(api="15m", delta=timedelta(minutes=15), step_ms=900_000),
    "1h": TimeframeSpec(api="1h", delta=timedelta(hours=1), step_ms=3_600_000),
    "4h": TimeframeSpec(api="4h", delta=timedelta(hours=4), step_ms=14_400_000),
    "1d": TimeframeSpec(api="1D", delta=timedelta(days=1), step_ms=86_400_000),
}
