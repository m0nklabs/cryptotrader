"""
ATR (Average True Range) indicator module.

This follows the same pattern as RSI for clean indicator-to-signal pipeline.

Usage:
    from core.indicators.atr import compute_atr, generate_atr_signal
    from core.types import Candle

    # Compute ATR value
    atr_value = compute_atr(candles, period=14)

    # Generate trading signal (volatility-based)
    signal = generate_atr_signal(candles, period=14)
"""

from __future__ import annotations

from typing import Sequence

from core.types import Candle, IndicatorSignal


def compute_atr(candles: Sequence[Candle], period: int = 14) -> float:
    """
    Calculate ATR (Average True Range) from candle data.

    ATR is a volatility indicator that measures the average range of price movements.
    It uses the True Range, which is the maximum of:
        - Current High - Current Low
        - |Current High - Previous Close|
        - |Current Low - Previous Close|

    Formula:
        True Range = max(High - Low, |High - Previous Close|, |Low - Previous Close|)
        ATR = Moving Average of True Range over period

    Args:
        candles: Sequence of OHLCV candles (must have at least period+1 candles)
        period: Lookback period for ATR calculation (default: 14)

    Returns:
        ATR value

    Raises:
        ValueError: If insufficient candles or invalid period
    """
    if period < 1:
        raise ValueError(f"period must be >= 1, got {period}")

    if len(candles) < period + 1:
        raise ValueError(f"need at least {period + 1} candles for ATR({period}), got {len(candles)}")

    # Calculate True Range for each candle
    true_ranges = []

    for i in range(1, len(candles)):
        current = candles[i]
        previous = candles[i - 1]

        high = float(current.high)
        low = float(current.low)
        prev_close = float(previous.close)

        # True Range = max(H-L, |H-PC|, |L-PC|)
        tr = max(
            high - low,
            abs(high - prev_close),
            abs(low - prev_close),
        )

        true_ranges.append(tr)

    # Calculate initial ATR (simple moving average for first period)
    atr = sum(true_ranges[:period]) / period

    # Smooth subsequent values using Wilder's smoothing (similar to EMA)
    for i in range(period, len(true_ranges)):
        atr = (atr * (period - 1) + true_ranges[i]) / period

    return atr


def generate_atr_signal(
    candles: Sequence[Candle],
    period: int = 14,
    high_volatility_threshold: float = 1.5,
    low_volatility_threshold: float = 0.5,
) -> IndicatorSignal:
    """
    Generate trading signal from ATR indicator.

    ATR doesn't directly indicate buy/sell, but rather volatility levels.
    High volatility can signal potential breakouts or increased risk.
    Low volatility can signal consolidation or reduced risk.

    Signal interpretation:
        - ATR > (average ATR * high_threshold): High volatility (caution or breakout potential)
        - ATR < (average ATR * low_threshold): Low volatility (consolidation)
        - Otherwise: Normal volatility (neutral)

    Args:
        candles: Sequence of OHLCV candles
        period: ATR period (default: 14)
        high_volatility_threshold: Threshold multiplier for high volatility (default: 1.5)
        low_volatility_threshold: Threshold multiplier for low volatility (default: 0.5)

    Returns:
        IndicatorSignal with side, strength, value, and reason

    Raises:
        ValueError: If insufficient candles or invalid parameters
    """
    if high_volatility_threshold <= 1.0:
        raise ValueError(f"high_volatility_threshold must be > 1.0, got {high_volatility_threshold}")
    if low_volatility_threshold >= 1.0:
        raise ValueError(f"low_volatility_threshold must be < 1.0, got {low_volatility_threshold}")

    # Need extra candles to calculate average ATR for comparison
    lookback_for_avg = period * 3  # Use 3x period for average calculation
    if len(candles) < lookback_for_avg:
        # Fall back to minimum required
        if len(candles) < period + 1:
            raise ValueError(f"need at least {period + 1} candles for ATR({period}), got {len(candles)}")

    current_atr = compute_atr(candles, period=period)

    # Calculate average ATR over a longer period for comparison
    # We'll calculate ATR at multiple points and average them
    if len(candles) >= lookback_for_avg:
        atr_values = []
        for i in range(lookback_for_avg - period, len(candles)):
            window = candles[: i + 1]
            if len(window) >= period + 1:
                atr_val = compute_atr(window, period=period)
                atr_values.append(atr_val)

        avg_atr = sum(atr_values) / len(atr_values) if atr_values else current_atr
    else:
        # Not enough data for historical average, use current ATR as baseline
        avg_atr = current_atr

    # Avoid division by zero
    if avg_atr == 0:
        avg_atr = current_atr if current_atr > 0 else 1.0

    # Calculate volatility ratio
    volatility_ratio = current_atr / avg_atr

    # Determine signal based on volatility level
    if volatility_ratio >= high_volatility_threshold:
        # High volatility
        strength = min(100, int((volatility_ratio - high_volatility_threshold) * 100))
        side = "HOLD"  # ATR doesn't indicate direction, just volatility
        reason = (
            f"ATR({period}) high volatility: {current_atr:.4f} "
            f"({volatility_ratio:.2f}x average, threshold {high_volatility_threshold}x)"
        )
    elif volatility_ratio <= low_volatility_threshold:
        # Low volatility
        strength = min(100, int((low_volatility_threshold - volatility_ratio) * 100))
        side = "HOLD"
        reason = (
            f"ATR({period}) low volatility: {current_atr:.4f} "
            f"({volatility_ratio:.2f}x average, threshold {low_volatility_threshold}x)"
        )
    else:
        # Normal volatility
        strength = 0
        side = "HOLD"
        reason = f"ATR({period}) normal volatility: {current_atr:.4f} ({volatility_ratio:.2f}x average)"

    return IndicatorSignal(
        code="ATR",
        side=side,
        strength=strength,
        value=f"{current_atr:.4f}",
        reason=reason,
    )
