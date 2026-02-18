"""Simple Moving Average (SMA) crossover strategy.

This strategy generates buy signals when the fast SMA crosses above the slow SMA,
and sell signals when the fast SMA crosses below the slow SMA.
"""

from __future__ import annotations

from typing import Optional

from core.backtest.strategy import Signal
from core.types import Candle


class SMACrossoverStrategy:
    """SMA crossover strategy.

    Generates BUY signals when fast SMA crosses above slow SMA.
    Generates SELL signals when fast SMA crosses below slow SMA.
    """

    def __init__(self, fast_period: int = 10, slow_period: int = 30):
        """Initialize the SMA crossover strategy.

        Args:
            fast_period: Period for fast SMA (default: 10)
            slow_period: Period for slow SMA (default: 30)
        """
        if fast_period >= slow_period:
            raise ValueError("fast_period must be less than slow_period")

        self.fast_period = fast_period
        self.slow_period = slow_period
        self._prev_fast_sma: Optional[float] = None
        self._prev_slow_sma: Optional[float] = None

    def on_candle(self, candle: Candle, indicators: dict) -> Signal | None:
        """Generate trading signal based on SMA crossover.

        Args:
            candle: Current OHLCV candle
            indicators: Computed indicators dict (must contain 'sma_fast' and 'sma_slow')

        Returns:
            Signal with side (BUY/SELL/HOLD) or None if SMAs not available
        """
        fast_sma = indicators.get(f"sma_{self.fast_period}")
        slow_sma = indicators.get(f"sma_{self.slow_period}")

        if fast_sma is None or slow_sma is None:
            return None

        # Detect crossover by comparing current and previous values
        if self._prev_fast_sma is not None and self._prev_slow_sma is not None:
            # Golden cross: fast SMA crosses above slow SMA
            if self._prev_fast_sma <= self._prev_slow_sma and fast_sma > slow_sma:
                signal = Signal(side="BUY", strength=80)
                self._prev_fast_sma = fast_sma
                self._prev_slow_sma = slow_sma
                return signal

            # Death cross: fast SMA crosses below slow SMA
            if self._prev_fast_sma >= self._prev_slow_sma and fast_sma < slow_sma:
                signal = Signal(side="SELL", strength=80)
                self._prev_fast_sma = fast_sma
                self._prev_slow_sma = slow_sma
                return signal

        # Update previous values for next iteration
        self._prev_fast_sma = fast_sma
        self._prev_slow_sma = slow_sma

        # No crossover detected
        return Signal(side="HOLD", strength=0)
