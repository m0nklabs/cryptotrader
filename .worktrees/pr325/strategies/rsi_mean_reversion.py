"""RSI mean reversion trading strategy.

This strategy buys when RSI falls below the oversold threshold and sells when RSI
rises above the overbought threshold.
"""

from __future__ import annotations

from core.backtest.strategy import Signal
from core.types import Candle


class RSIMeanReversionStrategy:
    """RSI-based mean reversion strategy.

    Generates BUY signals when RSI < oversold threshold.
    Generates SELL signals when RSI > overbought threshold.
    """

    def __init__(self, oversold: float = 30.0, overbought: float = 70.0):
        """Initialize the RSI mean reversion strategy.

        Args:
            oversold: RSI level below which to generate BUY signals (default: 30)
            overbought: RSI level above which to generate SELL signals (default: 70)
        """
        self.oversold = oversold
        self.overbought = overbought

    def on_candle(self, candle: Candle, indicators: dict) -> Signal | None:
        """Generate trading signal based on RSI indicator.

        Args:
            candle: Current OHLCV candle
            indicators: Computed indicators dict (must contain 'rsi')

        Returns:
            Signal with side (BUY/SELL/HOLD) or None if RSI not available
        """
        if "rsi" not in indicators:
            return None

        rsi = indicators["rsi"]

        if rsi < self.oversold:
            # Oversold - generate BUY signal
            # Strength increases as RSI gets more oversold
            strength = int((self.oversold - rsi) * 3)
            return Signal(side="BUY", strength=min(strength, 100))
        elif rsi > self.overbought:
            # Overbought - generate SELL signal
            # Strength increases as RSI gets more overbought
            strength = int((rsi - self.overbought) * 3)
            return Signal(side="SELL", strength=min(strength, 100))
        else:
            # Neutral zone - HOLD
            return Signal(side="HOLD", strength=0)
