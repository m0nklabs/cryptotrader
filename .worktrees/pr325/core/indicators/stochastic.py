"""
Stochastic Oscillator indicator module.

This follows the same pattern as RSI for clean indicator-to-signal pipeline.

Usage:
    from core.indicators.stochastic import compute_stochastic, generate_stochastic_signal
    from core.types import Candle

    # Compute Stochastic values
    k_value, d_value = compute_stochastic(candles, k_period=14, d_period=3)

    # Generate trading signal
    signal = generate_stochastic_signal(candles, k_period=14, d_period=3, oversold=20, overbought=80)
"""

from __future__ import annotations

from typing import Sequence

from core.types import Candle, IndicatorSignal


def compute_stochastic(
    candles: Sequence[Candle],
    k_period: int = 14,
    d_period: int = 3,
) -> tuple[float, float]:
    """
    Calculate Stochastic Oscillator from candle data.

    The Stochastic Oscillator is a momentum indicator that compares the closing price
    to the price range over a given period. It ranges from 0 to 100.

    Formula:
        %K = 100 * (Close - Lowest Low) / (Highest High - Lowest Low)
        %D = SMA(%K, d_period)

    Args:
        candles: Sequence of OHLCV candles (must have at least k_period+d_period-1 candles)
        k_period: Lookback period for %K calculation (default: 14)
        d_period: Smoothing period for %D calculation (default: 3)

    Returns:
        Tuple of (%K, %D) values (0-100)

    Raises:
        ValueError: If insufficient candles or invalid periods
    """
    if k_period < 1 or d_period < 1:
        raise ValueError(f"periods must be >= 1, got k_period={k_period}, d_period={d_period}")

    min_candles = k_period + d_period - 1
    if len(candles) < min_candles:
        raise ValueError(
            f"need at least {min_candles} candles for Stochastic({k_period},{d_period}), got {len(candles)}"
        )

    # Calculate %K values for the last d_period candles
    k_values = []

    for i in range(len(candles) - d_period + 1, len(candles) + 1):
        # Get the window of candles for this %K calculation
        window = candles[max(0, i - k_period) : i]

        if len(window) < k_period:
            # Not enough data yet, skip
            continue

        # Find highest high and lowest low in the window
        highest_high = max(float(c.high) for c in window)
        lowest_low = min(float(c.low) for c in window)

        # Current close
        current_close = float(window[-1].close)

        # Calculate %K
        if highest_high == lowest_low:
            # Avoid division by zero
            k_value = 50.0
        else:
            k_value = 100.0 * (current_close - lowest_low) / (highest_high - lowest_low)

        k_values.append(k_value)

    if len(k_values) < d_period:
        raise ValueError(f"insufficient data to calculate %D, need {d_period} %K values, got {len(k_values)}")

    # Current %K is the last value
    k = k_values[-1]

    # %D is the SMA of the last d_period %K values
    d = sum(k_values[-d_period:]) / d_period

    return k, d


def generate_stochastic_signal(
    candles: Sequence[Candle],
    k_period: int = 14,
    d_period: int = 3,
    oversold: float = 20.0,
    overbought: float = 80.0,
) -> IndicatorSignal:
    """
    Generate trading signal from Stochastic Oscillator.

    Signal interpretation:
        - %K < oversold (default 20): BUY signal (oversold condition)
        - %K > overbought (default 80): SELL signal (overbought condition)
        - oversold <= %K <= overbought: HOLD signal (neutral)

    Strength calculation:
        - For BUY: Higher strength when %K is lower (more oversold)
        - For SELL: Higher strength when %K is higher (more overbought)
        - For HOLD: Zero strength (neutral zone)

    Args:
        candles: Sequence of OHLCV candles
        k_period: %K period (default: 14)
        d_period: %D smoothing period (default: 3)
        oversold: Oversold threshold (default: 20)
        overbought: Overbought threshold (default: 80)

    Returns:
        IndicatorSignal with side, strength, value, and reason

    Raises:
        ValueError: If insufficient candles or invalid parameters
    """
    if oversold >= overbought:
        raise ValueError(f"oversold ({oversold}) must be < overbought ({overbought})")
    if oversold < 0:
        raise ValueError(f"oversold must be >= 0, got {oversold}")
    if overbought > 100:
        raise ValueError(f"overbought must be <= 100, got {overbought}")

    k, d = compute_stochastic(candles, k_period=k_period, d_period=d_period)

    # Determine signal side and strength based on %K
    if k < oversold:
        # Oversold: BUY signal
        # Strength increases as %K gets lower (more oversold)
        # strength = 0 at oversold threshold, 100 at %K=0
        strength = min(100, int((oversold - k) * (100.0 / oversold)))
        side = "BUY"
        reason = f"Stochastic({k_period},{d_period}) oversold: %K={k:.2f}, %D={d:.2f} (below {oversold:.0f})"
    elif k > overbought:
        # Overbought: SELL signal
        # Strength increases as %K gets higher (more overbought)
        # strength = 0 at overbought threshold, 100 at %K=100
        strength = min(100, int((k - overbought) * (100.0 / (100.0 - overbought))))
        side = "SELL"
        reason = f"Stochastic({k_period},{d_period}) overbought: %K={k:.2f}, %D={d:.2f} (above {overbought:.0f})"
    else:
        # Neutral zone: HOLD
        strength = 0
        side = "HOLD"
        reason = (
            f"Stochastic({k_period},{d_period}) neutral: %K={k:.2f}, %D={d:.2f} (range {oversold:.0f}-{overbought:.0f})"
        )

    return IndicatorSignal(
        code="STOCHASTIC",
        side=side,
        strength=strength,
        value=f"%K={k:.2f}, %D={d:.2f}",
        reason=reason,
    )
