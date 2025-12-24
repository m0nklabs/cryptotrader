"""
Bollinger Bands indicator module.

This follows the same pattern as RSI for clean indicator-to-signal pipeline.

Usage:
    from core.indicators.bollinger import compute_bollinger_bands, generate_bollinger_signal
    from core.types import Candle

    # Compute Bollinger Bands
    upper, middle, lower = compute_bollinger_bands(candles, period=20, std_dev=2)

    # Generate trading signal
    signal = generate_bollinger_signal(candles, period=20, std_dev=2)
"""

from __future__ import annotations

from typing import Sequence

from core.types import Candle, IndicatorSignal


def compute_bollinger_bands(
    candles: Sequence[Candle],
    period: int = 20,
    std_dev: float = 2.0,
) -> tuple[float, float, float]:
    """
    Calculate Bollinger Bands from candle data.

    Bollinger Bands consist of a middle band (SMA) and two outer bands
    (standard deviations above and below the SMA).

    Formula:
        Middle Band = SMA(close, period)
        Upper Band = Middle Band + (std_dev * standard deviation)
        Lower Band = Middle Band - (std_dev * standard deviation)

    Args:
        candles: Sequence of OHLCV candles (must have at least period candles)
        period: SMA period (default: 20)
        std_dev: Number of standard deviations (default: 2.0)

    Returns:
        Tuple of (upper_band, middle_band, lower_band)

    Raises:
        ValueError: If insufficient candles or invalid parameters
    """
    if period < 1:
        raise ValueError(f"period must be >= 1, got {period}")

    if std_dev <= 0:
        raise ValueError(f"std_dev must be > 0, got {std_dev}")

    if len(candles) < period:
        raise ValueError(f"need at least {period} candles for Bollinger({period},{std_dev}), got {len(candles)}")

    # Get closing prices
    closes = [float(c.close) for c in candles[-period:]]

    # Calculate middle band (SMA)
    middle_band = sum(closes) / period

    # Calculate standard deviation
    variance = sum((price - middle_band) ** 2 for price in closes) / period
    standard_deviation = variance**0.5

    # Calculate upper and lower bands
    upper_band = middle_band + (std_dev * standard_deviation)
    lower_band = middle_band - (std_dev * standard_deviation)

    return upper_band, middle_band, lower_band


def generate_bollinger_signal(
    candles: Sequence[Candle],
    period: int = 20,
    std_dev: float = 2.0,
) -> IndicatorSignal:
    """
    Generate trading signal from Bollinger Bands.

    Signal interpretation:
        - Price touches/breaks below lower band: BUY signal (oversold)
        - Price touches/breaks above upper band: SELL signal (overbought)
        - Price within bands: HOLD signal (neutral)

    Strength calculation:
        - For BUY: Stronger when price is further below lower band
        - For SELL: Stronger when price is further above upper band
        - For HOLD: Strength based on distance from middle band

    Args:
        candles: Sequence of OHLCV candles
        period: SMA period (default: 20)
        std_dev: Number of standard deviations (default: 2.0)

    Returns:
        IndicatorSignal with side, strength, value, and reason

    Raises:
        ValueError: If insufficient candles or invalid parameters
    """
    upper_band, middle_band, lower_band = compute_bollinger_bands(candles, period=period, std_dev=std_dev)

    current_price = float(candles[-1].close)

    # Calculate bandwidth for strength normalization
    bandwidth = upper_band - lower_band

    # Determine signal side and strength
    if current_price <= lower_band:
        # Price at or below lower band: BUY signal
        # Strength increases as price moves further below lower band
        if bandwidth > 0:
            distance_below = lower_band - current_price
            strength = min(100, int((distance_below / bandwidth) * 200))
        else:
            strength = 50
        side = "BUY"
        reason = f"Bollinger({period},{std_dev}) price at/below lower band (${current_price:.2f} <= ${lower_band:.2f})"
    elif current_price >= upper_band:
        # Price at or above upper band: SELL signal
        # Strength increases as price moves further above upper band
        if bandwidth > 0:
            distance_above = current_price - upper_band
            strength = min(100, int((distance_above / bandwidth) * 200))
        else:
            strength = 50
        side = "SELL"
        reason = f"Bollinger({period},{std_dev}) price at/above upper band (${current_price:.2f} >= ${upper_band:.2f})"
    else:
        # Price within bands: HOLD
        # Give some strength if price is closer to bands than middle
        if bandwidth > 0:
            distance_from_middle = abs(current_price - middle_band)
            relative_distance = distance_from_middle / (bandwidth / 2)
            strength = min(50, int(relative_distance * 50))
        else:
            strength = 0
        side = "HOLD"

        # More descriptive reason based on position
        if current_price > middle_band:
            reason = f"Bollinger({period},{std_dev}) price above middle band (${current_price:.2f} > ${middle_band:.2f})"
        elif current_price < middle_band:
            reason = f"Bollinger({period},{std_dev}) price below middle band (${current_price:.2f} < ${middle_band:.2f})"
        else:
            reason = f"Bollinger({period},{std_dev}) price at middle band (${current_price:.2f})"

    return IndicatorSignal(
        code="BOLLINGER",
        side=side,
        strength=strength,
        value=f"${current_price:.2f}",
        reason=reason,
    )
