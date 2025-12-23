"""
RSI (Relative Strength Index) indicator module.

This is a reference implementation demonstrating clean indicator-to-signal pipeline.
Agents should copy this pattern for other indicators.

Usage:
    from core.indicators.rsi import compute_rsi, generate_rsi_signal
    from core.types import Candle

    # Compute RSI value
    rsi_value = compute_rsi(candles, period=14)

    # Generate trading signal
    signal = generate_rsi_signal(candles, period=14, oversold=30, overbought=70)
"""

from __future__ import annotations

from typing import Sequence

from core.types import Candle, IndicatorSignal


def compute_rsi(candles: Sequence[Candle], period: int = 14) -> float:
    """
    Calculate RSI (Relative Strength Index) from candle data.

    RSI is a momentum oscillator that measures the speed and magnitude of
    price changes. It ranges from 0 to 100.

    Formula:
        RSI = 100 - (100 / (1 + RS))
        where RS = Average Gain / Average Loss over period

    Args:
        candles: Sequence of OHLCV candles (must have at least period+1 candles)
        period: Lookback period for RSI calculation (default: 14)

    Returns:
        RSI value (0-100)

    Raises:
        ValueError: If insufficient candles or invalid period
    """
    if period < 1:
        raise ValueError(f"period must be >= 1, got {period}")

    if len(candles) < period + 1:
        raise ValueError(f"need at least {period + 1} candles for RSI({period}), got {len(candles)}")

    # Calculate price changes
    gains = []
    losses = []

    for i in range(1, len(candles)):
        change = float(candles[i].close - candles[i - 1].close)
        if change > 0:
            gains.append(change)
            losses.append(0.0)
        else:
            gains.append(0.0)
            losses.append(abs(change))

    # Calculate initial averages (simple moving average for first period)
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    # Smooth subsequent values using Wilder's smoothing (exponential moving average)
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    # Calculate RSI
    if avg_loss == 0:
        return 100.0

    rs = avg_gain / avg_loss
    rsi = 100.0 - (100.0 / (1.0 + rs))

    return rsi


def generate_rsi_signal(
    candles: Sequence[Candle],
    period: int = 14,
    oversold: float = 30.0,
    overbought: float = 70.0,
) -> IndicatorSignal:
    """
    Generate trading signal from RSI indicator.

    Signal interpretation:
        - RSI < oversold (default 30): BUY signal (oversold condition)
        - RSI > overbought (default 70): SELL signal (overbought condition)
        - oversold <= RSI <= overbought: HOLD signal (neutral)

    Strength calculation:
        - For BUY: Higher strength when RSI is lower (more oversold)
        - For SELL: Higher strength when RSI is higher (more overbought)
        - For HOLD: Zero strength (neutral zone)

    Args:
        candles: Sequence of OHLCV candles
        period: RSI period (default: 14)
        oversold: Oversold threshold (default: 30)
        overbought: Overbought threshold (default: 70)

    Returns:
        IndicatorSignal with side, strength, value, and reason

    Raises:
        ValueError: If insufficient candles or invalid parameters
    """
    if oversold >= overbought:
        raise ValueError(f"oversold ({oversold}) must be < overbought ({overbought})")

    rsi = compute_rsi(candles, period=period)

    # Determine signal side and strength
    if rsi < oversold:
        # Oversold: BUY signal
        # Strength increases as RSI gets lower (more oversold)
        # strength = 0 at oversold threshold, 100 at RSI=0
        strength = min(100, int((oversold - rsi) * (100.0 / oversold)))
        side = "BUY"
        reason = f"RSI({period}) at {rsi:.2f} is oversold (below {oversold:.0f})"
    elif rsi > overbought:
        # Overbought: SELL signal
        # Strength increases as RSI gets higher (more overbought)
        # strength = 0 at overbought threshold, 100 at RSI=100
        strength = min(100, int((rsi - overbought) * (100.0 / (100.0 - overbought))))
        side = "SELL"
        reason = f"RSI({period}) at {rsi:.2f} is overbought (above {overbought:.0f})"
    else:
        # Neutral zone: HOLD
        strength = 0
        side = "HOLD"
        reason = f"RSI({period}) at {rsi:.2f} is in neutral range ({oversold:.0f}-{overbought:.0f})"

    return IndicatorSignal(
        code="RSI",
        side=side,
        strength=strength,
        value=f"{rsi:.2f}",
        reason=reason,
    )
