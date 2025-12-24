"""
Stochastic Oscillator indicator module.

This follows the RSI pattern for clean indicator-to-signal pipeline.

Usage:
    from core.indicators.stochastic import compute_stochastic, generate_stochastic_signal
    from core.types import Candle

    # Compute Stochastic values
    k_value, d_value = compute_stochastic(candles)

    # Generate trading signal
    signal = generate_stochastic_signal(candles)
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

    Stochastic compares a closing price to its price range over a given period.
    It ranges from 0 to 100.

    Formula:
        %K = 100 * (Close - Lowest Low) / (Highest High - Lowest Low)
        %D = SMA of %K over d_period

    Args:
        candles: Sequence of OHLCV candles (must have at least k_period candles)
        k_period: Lookback period for %K (default: 14)
        d_period: SMA period for %D (default: 3)

    Returns:
        Tuple of (k_value, d_value)

    Raises:
        ValueError: If insufficient candles or invalid periods
    """
    if k_period < 1 or d_period < 1:
        raise ValueError("All periods must be >= 1")

    min_candles = k_period + d_period - 1
    if len(candles) < min_candles:
        raise ValueError(f"need at least {min_candles} candles for Stochastic, got {len(candles)}")

    # Calculate %K for the latest period
    recent_candles = candles[-k_period:]
    lows = [float(c.low) for c in recent_candles]
    highs = [float(c.high) for c in recent_candles]
    close = float(candles[-1].close)

    lowest_low = min(lows)
    highest_high = max(highs)

    # Calculate %K
    if highest_high == lowest_low:
        k_value = 50.0  # Neutral when no range
    else:
        k_value = 100.0 * (close - lowest_low) / (highest_high - lowest_low)

    # Calculate %K values for the last d_period points to get %D
    k_values = []
    for i in range(max(0, len(candles) - k_period - d_period + 1), len(candles)):
        if i + k_period <= len(candles):
            subset = candles[i:i + k_period]
            subset_lows = [float(c.low) for c in subset]
            subset_highs = [float(c.high) for c in subset]
            subset_close = float(subset[-1].close)

            subset_lowest = min(subset_lows)
            subset_highest = max(subset_highs)

            if subset_highest == subset_lowest:
                k_values.append(50.0)
            else:
                k_values.append(100.0 * (subset_close - subset_lowest) / (subset_highest - subset_lowest))

    # Calculate %D as SMA of %K
    if len(k_values) >= d_period:
        d_value = sum(k_values[-d_period:]) / d_period
    else:
        d_value = k_value

    return k_value, d_value


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
        - %K crosses above %D in oversold: Strong BUY
        - %K crosses below %D in overbought: Strong SELL
        - Otherwise: HOLD signal

    Strength calculation:
        - For BUY: Higher strength when %K is lower (more oversold)
        - For SELL: Higher strength when %K is higher (more overbought)
        - Crossovers get bonus strength

    Args:
        candles: Sequence of OHLCV candles
        k_period: %K period (default: 14)
        d_period: %D period (default: 3)
        oversold: Oversold threshold (default: 20)
        overbought: Overbought threshold (default: 80)

    Returns:
        IndicatorSignal with side, strength, value, and reason

    Raises:
        ValueError: If insufficient candles or invalid parameters
    """
    if oversold >= overbought:
        raise ValueError(f"oversold ({oversold}) must be < overbought ({overbought})")
    if oversold <= 0:
        raise ValueError(f"oversold must be > 0, got {oversold}")
    if overbought >= 100:
        raise ValueError(f"overbought must be < 100, got {overbought}")

    # Need at least 2 sets to detect crossover
    min_candles = k_period + d_period
    if len(candles) < min_candles:
        raise ValueError(f"need at least {min_candles} candles for Stochastic signal, got {len(candles)}")

    k_value, d_value = compute_stochastic(candles, k_period=k_period, d_period=d_period)

    # Get previous values for crossover detection
    if len(candles) > min_candles:
        prev_k, prev_d = compute_stochastic(candles[:-1], k_period=k_period, d_period=d_period)
    else:
        prev_k, prev_d = k_value, d_value

    # Detect crossovers
    bullish_crossover = prev_k <= prev_d and k_value > d_value
    bearish_crossover = prev_k >= prev_d and k_value < d_value

    # Determine signal
    if k_value < oversold:
        side = "BUY"
        # Strength increases as %K gets lower
        strength = min(100, int((oversold - k_value) * (100.0 / oversold)))
        if bullish_crossover:
            strength = min(100, strength + 30)  # Bonus for crossover
            reason = f"Stochastic oversold + bullish crossover: %K({k_value:.1f}) crossed above %D({d_value:.1f})"
        else:
            reason = f"Stochastic oversold: %K({k_value:.1f}) < {oversold:.0f}"
    elif k_value > overbought:
        side = "SELL"
        # Strength increases as %K gets higher
        strength = min(100, int((k_value - overbought) * (100.0 / (100.0 - overbought))))
        if bearish_crossover:
            strength = min(100, strength + 30)  # Bonus for crossover
            reason = f"Stochastic overbought + bearish crossover: %K({k_value:.1f}) crossed below %D({d_value:.1f})"
        else:
            reason = f"Stochastic overbought: %K({k_value:.1f}) > {overbought:.0f}"
    elif bullish_crossover:
        side = "BUY"
        strength = 60
        reason = f"Stochastic bullish crossover: %K({k_value:.1f}) crossed above %D({d_value:.1f})"
    elif bearish_crossover:
        side = "SELL"
        strength = 60
        reason = f"Stochastic bearish crossover: %K({k_value:.1f}) crossed below %D({d_value:.1f})"
    else:
        side = "HOLD"
        strength = 0
        reason = f"Stochastic neutral: %K({k_value:.1f}), %D({d_value:.1f})"

    return IndicatorSignal(
        code="STOCH",
        side=side,
        strength=strength,
        value=f"%K={k_value:.1f}, %D={d_value:.1f}",
        reason=reason,
    )
