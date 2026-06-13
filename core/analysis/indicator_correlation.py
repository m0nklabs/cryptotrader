"""Indicator correlation analysis for correlated indicator groups.

Calculates correlation between RSI, MACD, and Stochastic indicators
to detect when correlated indicators produce the same signals and
cause double exposure.

Usage:
    from core.analysis.indicator_correlation import (
        compute_signal_correlation,
        compute_correlation_matrix,
        check_correlation_threshold,
    )
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Sequence

import numpy as np

from core.indicators.macd import compute_macd
from core.indicators.rsi import compute_rsi
from core.indicators.stochastic import compute_stochastic
from core.types import Candle

logger = logging.getLogger(__name__)

# Default maximum correlation threshold.
# Indicators with correlation above this are considered "too correlated".
DEFAULT_CORRELATION_THRESHOLD = 0.7

# Indicator names for labeling
RSI_CODE = "RSI"
MACD_CODE = "MACD"
STOCHASTIC_CODE = "STOCHASTIC"

# Pairs to track
CORRELATION_PAIRS = [
    (RSI_CODE, MACD_CODE),
    (RSI_CODE, STOCHASTIC_CODE),
    (MACD_CODE, STOCHASTIC_CODE),
]


@dataclass(frozen=True)
class CorrelationResult:
    """Result of a correlation check between two indicators."""

    indicator_a: str
    indicator_b: str
    correlation: float
    is_above_threshold: bool
    threshold: float


@dataclass(frozen=True)
class CorrelationMatrixResult:
    """Full correlation matrix result for all indicator pairs."""

    pairs: list[CorrelationResult]
    matrix: dict[str, dict[str, float]]
    threshold: float
    max_correlation: float
    max_correlation_pair: tuple[str, str]
    min_correlation: float
    min_correlation_pair: tuple[str, str]
    overcorrelated_pairs: list[str] = field(default_factory=list)


def _extract_signal_series(
    candles: Sequence[Candle],
    indicator: str = "RSI",
    **kwargs,
) -> list[float]:
    """Extract a time series of indicator values from candle data.

    Uses a rolling window approach: for each candle position (after warmup),
    computes the indicator using all candles up to that point.

    Args:
        candles: Sequence of OHLCV candles.
        indicator: Which indicator to compute ("RSI", "MACD", "STOCHASTIC").
        **kwargs: Additional parameters passed to the indicator function.

    Returns:
        List of indicator values, one per candle position (after warmup).
    """
    values: list[float] = []
    warmup = kwargs.get("warmup", 40)

    for i in range(warmup, len(candles)):
        window = candles[: i + 1]

        if indicator == RSI_CODE:
            period = kwargs.get("period", 14)
            val = compute_rsi(window, period=period)
            values.append(val)

        elif indicator == MACD_CODE:
            fast = kwargs.get("fast", 12)
            slow = kwargs.get("slow", 26)
            signal_period = kwargs.get("signal_period", 9)
            macd_line, signal_line, histogram = compute_macd(
                window, fast=fast, slow=slow, signal_period=signal_period
            )
            # Use histogram as the signal value (most discriminative)
            values.append(histogram)

        elif indicator == STOCHASTIC_CODE:
            k_period = kwargs.get("k_period", 14)
            d_period = kwargs.get("d_period", 3)
            k_val, d_val = compute_stochastic(window, k_period=k_period, d_period=d_period)
            values.append(k_val)

        else:
            raise ValueError(f"Unknown indicator: {indicator}")

    return values


def compute_signal_correlation(
    candles: Sequence[Candle],
    indicator_a: str = RSI_CODE,
    indicator_b: str = STOCHASTIC_CODE,
    threshold: float = DEFAULT_CORRELATION_THRESHOLD,
    **kwargs,
) -> CorrelationResult:
    """Compute correlation between two indicators.

    Args:
        candles: Sequence of OHLCV candles.
        indicator_a: First indicator code.
        indicator_b: Second indicator code.
        threshold: Correlation threshold above which indicators
            are considered too correlated.
        **kwargs: Parameters passed to indicator functions.

    Returns:
        CorrelationResult with correlation value and threshold check.
    """
    series_a = _extract_signal_series(candles, indicator_a, **kwargs)
    series_b = _extract_signal_series(candles, indicator_b, **kwargs)

    # Align series lengths
    min_len = min(len(series_a), len(series_b))
    series_a = series_a[:min_len]
    series_b = series_b[:min_len]

    if min_len < 10:
        raise ValueError(
            f"Insufficient data for correlation: {min_len} points "
            f"(need >= 10) for {indicator_a} vs {indicator_b}"
        )

    correlation = float(np.corrcoef(series_a, series_b)[0, 1])

    # Handle NaN from constant series
    if np.isnan(correlation):
        correlation = 0.0

    is_above = abs(correlation) >= threshold

    return CorrelationResult(
        indicator_a=indicator_a,
        indicator_b=indicator_b,
        correlation=round(correlation, 4),
        is_above_threshold=is_above,
        threshold=threshold,
    )


def compute_correlation_matrix(
    candles: Sequence[Candle],
    indicators: list[str] | None = None,
    threshold: float = DEFAULT_CORRELATION_THRESHOLD,
    **kwargs,
) -> CorrelationMatrixResult:
    """Compute full correlation matrix for all indicator pairs.

    Args:
        candles: Sequence of OHLCV candles.
        indicators: List of indicator codes to include.
            Defaults to [RSI, MACD, STOCHASTIC].
        threshold: Maximum correlation threshold.
        **kwargs: Parameters passed to indicator functions.

    Returns:
        CorrelationMatrixResult with all pairwise correlations.
    """
    if indicators is None:
        indicators = [RSI_CODE, MACD_CODE, STOCHASTIC_CODE]

    if len(indicators) < 2:
        raise ValueError("Need at least 2 indicators for correlation matrix")

    # Build pairwise correlation results
    pairs: list[CorrelationResult] = []
    matrix: dict[str, dict[str, float]] = {ind: {} for ind in indicators}

    for i, ind_a in enumerate(indicators):
        matrix[ind_a][ind_a] = 1.0
        for j, ind_b in enumerate(indicators):
            if i < j:
                result = compute_signal_correlation(
                    candles, indicator_a=ind_a, indicator_b=ind_b, threshold=threshold, **kwargs
                )
                pairs.append(result)
                matrix[ind_a][ind_b] = result.correlation
                matrix[ind_b][ind_a] = result.correlation

    # Find max and min correlations
    pair_correlations = [(p.indicator_a, p.indicator_b, p.correlation) for p in pairs]
    max_pair = max(pair_correlations, key=lambda x: abs(x[2]))
    min_pair = min(pair_correlations, key=lambda x: abs(x[2]))

    # Find over-correlated pairs
    overcorrelated = [
        f"{p.indicator_a}/{p.indicator_b}"
        for p in pairs
        if p.is_above_threshold
    ]

    return CorrelationMatrixResult(
        pairs=pairs,
        matrix=matrix,
        threshold=threshold,
        max_correlation=max_pair[2],
        max_correlation_pair=(max_pair[0], max_pair[1]),
        min_correlation=min_pair[2],
        min_correlation_pair=(min_pair[0], min_pair[1]),
        overcorrelated_pairs=overcorrelated,
    )


def check_correlation_threshold(
    candles: Sequence[Candle],
    threshold: float = DEFAULT_CORRELATION_THRESHOLD,
    indicators: list[str] | None = None,
    **kwargs,
) -> dict:
    """Check if indicator correlations are within acceptable limits.

    This is the main entry point for Phase 6 correlation verification.

    Args:
        candles: Sequence of OHLCV candles.
        threshold: Maximum allowed correlation (0.0 to 1.0).
        indicators: List of indicators to check.
        **kwargs: Parameters for indicator functions.

    Returns:
        Dictionary with:
        - matrix: full correlation matrix
        - pairs: list of pair results
        - threshold: the threshold used
        - max_correlation: highest correlation found
        - max_correlation_pair: pair with highest correlation
        - min_correlation: lowest correlation found
        - min_correlation_pair: pair with lowest correlation
        - overcorrelated: list of over-correlated pair names
        - within_limits: True if no pair exceeds threshold
        - risk_level: "low", "medium", or "high" based on count of
            over-correlated pairs
    """
    result = compute_correlation_matrix(candles, indicators=indicators, threshold=threshold, **kwargs)

    # Determine risk level
    n_over = len(result.overcorrelated_pairs)
    n_total = len(result.pairs)

    if n_over == 0:
        risk_level = "low"
    elif n_over <= n_total / 2:
        risk_level = "medium"
    else:
        risk_level = "high"

    return {
        "matrix": result.matrix,
        "pairs": [
            {
                "indicator_a": p.indicator_a,
                "indicator_b": p.indicator_b,
                "correlation": p.correlation,
                "is_above_threshold": p.is_above_threshold,
            }
            for p in result.pairs
        ],
        "threshold": result.threshold,
        "max_correlation": result.max_correlation,
        "max_correlation_pair": list(result.max_correlation_pair),
        "min_correlation": result.min_correlation,
        "min_correlation_pair": list(result.min_correlation_pair),
        "overcorrelated": result.overcorrelated_pairs,
        "within_limits": len(result.overcorrelated_pairs) == 0,
        "risk_level": risk_level,
    }


def generate_synthetic_candles(
    count: int = 200,
    correlation_mode: str = "neutral",
    noise_level: float = 1.0,
    **kwargs,
) -> list[Candle]:
    """Generate synthetic candle data for testing.

    Args:
        count: Number of candles to generate.
        correlation_mode: "high" for correlated indicators,
            "low" for uncorrelated, "neutral" for typical.
        noise_level: Noise level for signal variation.
        **kwargs: Additional parameters for indicator functions.

    Returns:
        List of synthetic Candle objects.
    """
    from datetime import datetime, timedelta, timezone
    from decimal import Decimal

    base_time = datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc)

    # Generate base price series
    prices: list[float] = [100.0]
    for i in range(1, count):
        # Trend + noise
        trend = 0.02 * (i % 10 - 5) / 5.0
        noise = np.random.normal(0, noise_level)

        if correlation_mode == "high":
            # Stronger trend for correlated behavior
            trend *= 2.0
        elif correlation_mode == "low":
            # More noise for uncorrelated behavior
            noise *= 2.0

        prices.append(prices[-1] + trend + noise)

    candles = []
    for i in range(count):
        price = prices[i]
        high = price + abs(np.random.normal(0, 1.5))
        low = price - abs(np.random.normal(0, 1.5))
        volume = Decimal(str(1000 + np.random.randint(0, 500)))

        candles.append(Candle(
            symbol="BTCUSD",
            exchange="bitfinex",
            timeframe="1h",
            open_time=base_time + timedelta(hours=i),
            close_time=base_time + timedelta(hours=i, minutes=59),
            open=Decimal(str(price)),
            high=Decimal(str(high)),
            low=Decimal(str(low)),
            close=Decimal(str(price)),
            volume=volume,
        ))

    return candles


def format_correlation_report(data: dict[str, object]) -> str:
    """Format correlation analysis results as a human-readable report.

    Args:
        data: Output from check_correlation_threshold.

    Returns:
        Formatted report string.
    """
    lines = []
    lines.append("=" * 60)
    lines.append("INDICATOR CORRELATION REPORT")
    lines.append("=" * 60)
    lines.append("")

    # Threshold
    lines.append(f"Correlation threshold: {data['threshold']}")
    lines.append(f"Risk level: {data['risk_level']}")
    lines.append(f"Within limits: {data['within_limits']}")
    lines.append("")

    # Pair correlations
    lines.append("Pair Correlations:")
    lines.append("-" * 60)
    for pair in data["pairs"]:
        marker = " [HIGH]" if pair["is_above_threshold"] else ""
        lines.append(
            f"  {pair['indicator_a']:>12} <-> {pair['indicator_b']:>12}: "
            f"{pair['correlation']:.4f}{marker}"
        )
    lines.append("")

    # Extremes
    lines.append(f"Max correlation: {data['max_correlation']:.4f} "
                 f"({data['max_correlation_pair'][0]} / {data['max_correlation_pair'][1]})")
    lines.append(f"Min correlation: {data['min_correlation']:.4f} "
                 f"({data['min_correlation_pair'][0]} / {data['min_correlation_pair'][1]})")
    lines.append("")

    # Over-correlated
    if data["overcorrelated"]:
        lines.append("Over-correlated pairs (above threshold):")
        for pair_name in data["overcorrelated"]:
            lines.append(f"  - {pair_name}")
    else:
        lines.append("No over-correlated pairs detected.")

    lines.append("")
    lines.append("=" * 60)

    return "\n".join(lines)
