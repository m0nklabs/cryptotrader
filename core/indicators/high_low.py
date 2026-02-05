"""High/Low channel (Donchian-style) indicator module.

Computes the highest high and lowest low over a lookback window and can generate
simple breakout/breakdown signals.

Design notes:
- Uses candle highs/lows (not closes) for the channel bounds.
- For signals, compares the *current close* against the previous window bounds
  (excluding the current candle) to avoid lookahead bias.

Usage:
    from core.indicators.high_low import compute_high_low_channel, generate_high_low_signal
    from core.types import Candle

    upper, lower = compute_high_low_channel(candles, period=20)
    signal = generate_high_low_signal(candles, period=20)
"""

from __future__ import annotations

from typing import Sequence

from core.types import Candle, IndicatorSignal


def compute_high_low_channel(candles: Sequence[Candle], period: int = 20) -> tuple[float, float]:
    """Compute highest-high / lowest-low channel for the last `period` candles.

    Args:
        candles: Sequence of OHLCV candles.
        period: Lookback window size.

    Returns:
        Tuple of (upper, lower) channel bounds.

    Raises:
        ValueError: If period is invalid or insufficient candles.
    """
    if period < 1:
        raise ValueError(f"period must be >= 1, got {period}")

    if len(candles) < period:
        raise ValueError(f"need at least {period} candles for HIGH_LOW({period}), got {len(candles)}")

    window = candles[-period:]
    upper = max(float(c.high) for c in window)
    lower = min(float(c.low) for c in window)
    return upper, lower


def generate_high_low_signal(
    candles: Sequence[Candle],
    *,
    period: int = 20,
    breakout_buffer_bps: float = 0.0,
) -> IndicatorSignal:
    """Generate a breakout/breakdown signal from a High/Low channel.

    Signal interpretation:
        - close >= previous upper bound: BUY (breakout)
        - close <= previous lower bound: SELL (breakdown)
        - otherwise: HOLD

    Args:
        candles: Sequence of OHLCV candles.
        period: Lookback window for channel bounds.
        breakout_buffer_bps: Optional buffer in basis points (bps) to reduce noise.
            Example: 10 bps means breakout requires +0.10% beyond the bound.

    Returns:
        IndicatorSignal with side, strength, value, and reason.
    """
    if breakout_buffer_bps < 0:
        raise ValueError(f"breakout_buffer_bps must be >= 0, got {breakout_buffer_bps}")

    if len(candles) < period + 1:
        raise ValueError(f"need at least {period + 1} candles for HIGH_LOW({period}) signal, got {len(candles)}")

    # Use prior window (exclude current candle) to avoid lookahead.
    prior = candles[-(period + 1) : -1]
    prev_upper = max(float(c.high) for c in prior)
    prev_lower = min(float(c.low) for c in prior)

    current_price = float(candles[-1].close)

    width = prev_upper - prev_lower
    if width == 0:
        return IndicatorSignal(
            code="HIGH_LOW",
            side="HOLD",
            strength=0,
            value=f"${current_price:.2f}",
            reason=f"HIGH_LOW({period}) flat channel at ${prev_upper:.2f}",
        )

    up_thresh = prev_upper * (1.0 + breakout_buffer_bps / 10_000.0)
    down_thresh = prev_lower * (1.0 - breakout_buffer_bps / 10_000.0)

    if current_price >= up_thresh:
        distance = current_price - prev_upper
        strength = min(100, int((distance / width) * 200) + 50)
        return IndicatorSignal(
            code="HIGH_LOW",
            side="BUY",
            strength=strength,
            value=f"${current_price:.2f} >= ${prev_upper:.2f}",
            reason=f"HIGH_LOW({period}) breakout above prior high (${prev_upper:.2f})",
        )

    if current_price <= down_thresh:
        distance = prev_lower - current_price
        strength = min(100, int((distance / width) * 200) + 50)
        return IndicatorSignal(
            code="HIGH_LOW",
            side="SELL",
            strength=strength,
            value=f"${current_price:.2f} <= ${prev_lower:.2f}",
            reason=f"HIGH_LOW({period}) breakdown below prior low (${prev_lower:.2f})",
        )

    # Inside channel.
    # Strength is informational: closer to bounds => higher "attention".
    dist_to_upper = prev_upper - current_price
    dist_to_lower = current_price - prev_lower
    nearest = min(dist_to_upper, dist_to_lower)
    # 0 at mid, up to ~50 near edges.
    strength = min(50, int((1.0 - (nearest / (width / 2))) * 50))
    return IndicatorSignal(
        code="HIGH_LOW",
        side="HOLD",
        strength=strength,
        value=f"${current_price:.2f} in [${prev_lower:.2f}, ${prev_upper:.2f}]",
        reason=f"HIGH_LOW({period}) inside channel",
    )
