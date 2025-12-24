"""
MACD (Moving Average Convergence Divergence) indicator module.

This follows the same pattern as RSI for clean indicator-to-signal pipeline.

Usage:
    from core.indicators.macd import compute_macd, generate_macd_signal
    from core.types import Candle

    # Compute MACD values
    macd_line, signal_line, histogram = compute_macd(candles, fast=12, slow=26, signal_period=9)

    # Generate trading signal
    signal = generate_macd_signal(candles, fast=12, slow=26, signal_period=9)
"""

from __future__ import annotations

from typing import Sequence

from core.types import Candle, IndicatorSignal


def compute_macd(
    candles: Sequence[Candle],
    fast: int = 12,
    slow: int = 26,
    signal_period: int = 9,
) -> tuple[float, float, float]:
    """
    Calculate MACD (Moving Average Convergence Divergence) from candle data.

    MACD is a trend-following momentum indicator that shows the relationship
    between two exponential moving averages (EMAs).

    Formula:
        MACD Line = EMA(fast) - EMA(slow)
        Signal Line = EMA(MACD Line, signal_period)
        Histogram = MACD Line - Signal Line

    Args:
        candles: Sequence of OHLCV candles (must have at least slow+signal_period candles)
        fast: Fast EMA period (default: 12)
        slow: Slow EMA period (default: 26)
        signal_period: Signal line EMA period (default: 9)

    Returns:
        Tuple of (macd_line, signal_line, histogram)

    Raises:
        ValueError: If insufficient candles or invalid periods
    """
    if fast < 1 or slow < 1 or signal_period < 1:
        raise ValueError(f"periods must be >= 1, got fast={fast}, slow={slow}, signal={signal_period}")

    if fast >= slow:
        raise ValueError(f"fast period ({fast}) must be < slow period ({slow})")

    min_candles = slow + signal_period
    if len(candles) < min_candles:
        raise ValueError(f"need at least {min_candles} candles for MACD({fast},{slow},{signal_period}), got {len(candles)}")

    closes = [float(c.close) for c in candles]

    # Calculate EMAs
    fast_ema = _calculate_ema(closes, fast)
    slow_ema = _calculate_ema(closes, slow)

    # MACD line = fast EMA - slow EMA
    macd_values = [fast_ema[i] - slow_ema[i] for i in range(len(fast_ema))]

    # Signal line = EMA of MACD line
    signal_line_values = _calculate_ema(macd_values, signal_period)

    # Get the latest values
    macd_line = macd_values[-1]
    signal_line = signal_line_values[-1]
    histogram = macd_line - signal_line

    return macd_line, signal_line, histogram


def _calculate_ema(values: list[float], period: int) -> list[float]:
    """Calculate Exponential Moving Average (EMA).

    Args:
        values: List of price values
        period: EMA period

    Returns:
        List of EMA values starting from index period-1 (aligned with input)
    """
    if len(values) < period:
        raise ValueError(f"need at least {period} values for EMA({period}), got {len(values)}")

    multiplier = 2.0 / (period + 1)
    ema_values = [0.0] * len(values)  # Preallocate full length

    # Start with SMA for the first valid EMA at index period-1
    sma = sum(values[:period]) / period
    ema_values[period - 1] = sma

    # Calculate EMA for remaining values
    for i in range(period, len(values)):
        ema_values[i] = (values[i] - ema_values[i - 1]) * multiplier + ema_values[i - 1]

    return ema_values


def generate_macd_signal(
    candles: Sequence[Candle],
    fast: int = 12,
    slow: int = 26,
    signal_period: int = 9,
) -> IndicatorSignal:
    """
    Generate trading signal from MACD indicator.

    Signal interpretation:
        - MACD line crosses above signal line: BUY signal (bullish crossover)
        - MACD line crosses below signal line: SELL signal (bearish crossover)
        - No crossover: HOLD signal (neutral)

    Strength calculation:
        - Based on histogram magnitude (distance between MACD and signal line)
        - Larger histogram = stronger signal

    Args:
        candles: Sequence of OHLCV candles
        fast: Fast EMA period (default: 12)
        slow: Slow EMA period (default: 26)
        signal_period: Signal line EMA period (default: 9)

    Returns:
        IndicatorSignal with side, strength, value, and reason

    Raises:
        ValueError: If insufficient candles or invalid parameters
    """
    # Need extra candles to detect crossover
    if len(candles) < slow + signal_period + 1:
        raise ValueError(f"need at least {slow + signal_period + 1} candles to detect crossover")

    # Get current MACD values
    macd_line, signal_line, histogram = compute_macd(candles, fast=fast, slow=slow, signal_period=signal_period)

    # Get previous MACD values to detect crossover
    prev_candles = candles[:-1]
    prev_macd_line, prev_signal_line, prev_histogram = compute_macd(
        prev_candles, fast=fast, slow=slow, signal_period=signal_period
    )

    # Detect crossover
    if prev_macd_line <= prev_signal_line and macd_line > signal_line:
        # Bullish crossover: MACD crossed above signal
        # Strength based on histogram magnitude
        strength = min(100, int(abs(histogram) * 100))
        side = "BUY"
        reason = f"MACD({fast},{slow},{signal_period}) bullish crossover (histogram: {histogram:.4f})"
    elif prev_macd_line >= prev_signal_line and macd_line < signal_line:
        # Bearish crossover: MACD crossed below signal
        strength = min(100, int(abs(histogram) * 100))
        side = "SELL"
        reason = f"MACD({fast},{slow},{signal_period}) bearish crossover (histogram: {histogram:.4f})"
    else:
        # No crossover: HOLD
        # If histogram is significantly positive or negative, give it some strength
        if histogram > 0:
            strength = min(50, int(abs(histogram) * 50))
            reason = f"MACD({fast},{slow},{signal_period}) above signal (histogram: {histogram:.4f})"
        elif histogram < 0:
            strength = min(50, int(abs(histogram) * 50))
            reason = f"MACD({fast},{slow},{signal_period}) below signal (histogram: {histogram:.4f})"
        else:
            strength = 0
            reason = f"MACD({fast},{slow},{signal_period}) neutral (histogram: {histogram:.4f})"
        side = "HOLD"

    return IndicatorSignal(
        code="MACD",
        side=side,
        strength=strength,
        value=f"{histogram:.4f}",
        reason=reason,
    )
