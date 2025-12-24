"""
MACD (Moving Average Convergence Divergence) indicator module.

This follows the RSI pattern for clean indicator-to-signal pipeline.

Usage:
    from core.indicators.macd import compute_macd, generate_macd_signal
    from core.types import Candle

    # Compute MACD values
    macd_line, signal_line, histogram = compute_macd(candles)

    # Generate trading signal
    signal = generate_macd_signal(candles)
"""

from __future__ import annotations

from typing import Sequence

from core.types import Candle, IndicatorSignal


def compute_macd(
    candles: Sequence[Candle],
    fast_period: int = 12,
    slow_period: int = 26,
    signal_period: int = 9,
) -> tuple[float, float, float]:
    """
    Calculate MACD (Moving Average Convergence Divergence) from candle data.

    MACD shows the relationship between two moving averages of prices.

    Formula:
        MACD Line = EMA(fast_period) - EMA(slow_period)
        Signal Line = EMA(MACD Line, signal_period)
        Histogram = MACD Line - Signal Line

    Args:
        candles: Sequence of OHLCV candles (must have at least slow_period candles)
        fast_period: Fast EMA period (default: 12)
        slow_period: Slow EMA period (default: 26)
        signal_period: Signal line EMA period (default: 9)

    Returns:
        Tuple of (macd_line, signal_line, histogram)

    Raises:
        ValueError: If insufficient candles or invalid periods
    """
    if fast_period < 1 or slow_period < 1 or signal_period < 1:
        raise ValueError("All periods must be >= 1")

    if fast_period >= slow_period:
        raise ValueError(f"fast_period ({fast_period}) must be < slow_period ({slow_period})")

    min_candles = slow_period + signal_period
    if len(candles) < min_candles:
        raise ValueError(f"need at least {min_candles} candles for MACD, got {len(candles)}")

    closes = [float(c.close) for c in candles]

    # Calculate EMAs
    def calc_ema(values: list[float], period: int) -> float:
        """Calculate Exponential Moving Average."""
        multiplier = 2.0 / (period + 1)
        # Start with SMA for initial value
        ema = sum(values[:period]) / period

        # Apply EMA formula for remaining values
        for i in range(period, len(values)):
            ema = (values[i] - ema) * multiplier + ema

        return ema

    # Calculate fast and slow EMAs
    fast_ema = calc_ema(closes, fast_period)
    slow_ema = calc_ema(closes, slow_period)

    # MACD line
    macd_line = fast_ema - slow_ema

    # For signal line, we need MACD values for the last signal_period bars
    # Compute MACD line for each point to build signal line
    macd_values = []
    for i in range(slow_period, len(closes) + 1):
        subset = closes[:i]
        f_ema = calc_ema(subset, fast_period)
        s_ema = calc_ema(subset, slow_period)
        macd_values.append(f_ema - s_ema)

    # Signal line is EMA of MACD values
    if len(macd_values) >= signal_period:
        signal_line = calc_ema(macd_values, signal_period)
    else:
        signal_line = macd_line

    # Histogram
    histogram = macd_line - signal_line

    return macd_line, signal_line, histogram


def generate_macd_signal(
    candles: Sequence[Candle],
    fast_period: int = 12,
    slow_period: int = 26,
    signal_period: int = 9,
) -> IndicatorSignal:
    """
    Generate trading signal from MACD indicator.

    Signal interpretation:
        - MACD line crosses above signal line: BUY signal (bullish)
        - MACD line crosses below signal line: SELL signal (bearish)
        - No crossover: HOLD signal

    Strength calculation:
        - Based on histogram magnitude (distance between MACD and signal line)

    Args:
        candles: Sequence of OHLCV candles
        fast_period: Fast EMA period (default: 12)
        slow_period: Slow EMA period (default: 26)
        signal_period: Signal line EMA period (default: 9)

    Returns:
        IndicatorSignal with side, strength, value, and reason

    Raises:
        ValueError: If insufficient candles or invalid parameters
    """
    # Need at least 2 sets of values to detect crossover
    min_candles = slow_period + signal_period + 1
    if len(candles) < min_candles:
        raise ValueError(f"need at least {min_candles} candles for MACD signal, got {len(candles)}")

    # Calculate current MACD
    macd_line, signal_line, histogram = compute_macd(
        candles, fast_period=fast_period, slow_period=slow_period, signal_period=signal_period
    )

    # Calculate previous MACD (using all but last candle)
    prev_macd_line, prev_signal_line, prev_histogram = compute_macd(
        candles[:-1], fast_period=fast_period, slow_period=slow_period, signal_period=signal_period
    )

    # Detect crossover
    bullish_crossover = prev_macd_line <= prev_signal_line and macd_line > signal_line
    bearish_crossover = prev_macd_line >= prev_signal_line and macd_line < signal_line

    # Calculate strength based on histogram magnitude
    # Normalize histogram relative to typical price range
    closes = [float(c.close) for c in candles[-slow_period:]]
    price_range = max(closes) - min(closes)
    if price_range > 0:
        normalized_histogram = abs(histogram) / price_range
        strength = min(100, int(normalized_histogram * 500))  # Scale factor
    else:
        strength = 50

    if bullish_crossover:
        side = "BUY"
        strength = max(strength, 60)  # Crossovers get minimum 60 strength
        reason = f"MACD bullish crossover: MACD({macd_line:.2f}) > Signal({signal_line:.2f})"
    elif bearish_crossover:
        side = "SELL"
        strength = max(strength, 60)
        reason = f"MACD bearish crossover: MACD({macd_line:.2f}) < Signal({signal_line:.2f})"
    else:
        # Check histogram for trend confirmation
        if histogram > 0:
            side = "BUY"
            reason = f"MACD bullish: MACD({macd_line:.2f}) > Signal({signal_line:.2f}), Hist={histogram:.2f}"
        elif histogram < 0:
            side = "SELL"
            reason = f"MACD bearish: MACD({macd_line:.2f}) < Signal({signal_line:.2f}), Hist={histogram:.2f}"
        else:
            side = "HOLD"
            strength = 0
            reason = f"MACD neutral: MACD({macd_line:.2f}) ≈ Signal({signal_line:.2f})"

    return IndicatorSignal(
        code="MACD",
        side=side,
        strength=strength,
        value=f"{macd_line:.2f}",
        reason=reason,
    )
