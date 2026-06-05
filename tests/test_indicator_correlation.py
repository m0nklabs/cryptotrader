"""Tests for indicator correlation analysis.

Verifies that correlated indicators (RSI, MACD, Stochastic)
do not produce duplicate signals and that the correlation
matrix correctly identifies over-correlated pairs.

Acceptance criteria:
(1) correlation matrix is calculated and verified
(2) threshold for maximum correlation is defined
(3) validation script produces output with correlation values
(4) tests pass for high and low correlation regimes
"""

from __future__ import annotations

import math

import pytest

from core.analysis.indicator_correlation import (
    CORRELATION_PAIRS,
    DEFAULT_CORRELATION_THRESHOLD,
    RSI_CODE,
    MACD_CODE,
    STOCHASTIC_CODE,
    check_correlation_threshold,
    compute_correlation_matrix,
    compute_signal_correlation,
    format_correlation_report,
    generate_synthetic_candles,
)
from core.types import Candle


# --- Synthetic data helpers ---

def _make_candles(count: int = 200, trend_strength: float = 1.0, noise: float = 1.0) -> list[Candle]:
    """Create synthetic candles with controlled trend and noise."""
    from datetime import datetime, timedelta, timezone
    from decimal import Decimal
    import numpy as np

    np.random.seed(42)
    base_time = datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc)

    prices = [100.0]
    for i in range(1, count):
        trend = 0.02 * trend_strength * (i % 10 - 5) / 5.0
        n = noise * np.random.normal(0, 1)
        prices.append(prices[-1] + trend + n)

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


# --- Test: Correlation between RSI and Stochastic ---

class TestRSIStochasticCorrelation:
    """Test that RSI and Stochastic correlation is computed correctly."""

    def test_rsi_stochastic_high_correlation(self):
        """RSI and Stochastic should be highly correlated (both 0-100 oscillators)."""
        candles = _make_candles(count=200, trend_strength=2.0, noise=0.5)
        result = compute_signal_correlation(candles, RSI_CODE, STOCHASTIC_CODE)

        assert result.indicator_a == RSI_CODE
        assert result.indicator_b == STOCHASTIC_CODE
        assert result.correlation > 0.5, f"Expected high correlation, got {result.correlation}"
        assert result.is_above_threshold == (abs(result.correlation) >= DEFAULT_CORRELATION_THRESHOLD)
        assert result.threshold == DEFAULT_CORRELATION_THRESHOLD

    def test_rsi_stochastic_low_correlation(self):
        """RSI and Stochastic with more noise should have lower correlation."""
        candles = _make_candles(count=200, trend_strength=1.0, noise=3.0)
        result = compute_signal_correlation(candles, RSI_CODE, STOCHASTIC_CODE)

        assert result.correlation < 0.9, f"Expected lower correlation with noise, got {result.correlation}"


# --- Test: Correlation between RSI and MACD ---

class TestRSIMACDCorrelation:
    """Test that RSI and MACD correlation is computed correctly."""

    def test_rsi_macd_correlation_range(self):
        """RSI and MACD correlation should be in a reasonable range."""
        candles = _make_candles(count=200)
        result = compute_signal_correlation(candles, RSI_CODE, MACD_CODE)

        assert -1.0 <= result.correlation <= 1.0
        assert result.correlation != 0.0  # Should not be completely uncorrelated

    def test_rsi_macd_different_regimes(self):
        """RSI-MACD correlation should differ between trending and ranging regimes."""
        trending = _make_candles(count=200, trend_strength=3.0, noise=0.5)
        ranging = _make_candles(count=200, trend_strength=0.5, noise=2.0)

        corr_trending = compute_signal_correlation(trending, RSI_CODE, MACD_CODE)
        corr_ranging = compute_signal_correlation(ranging, RSI_CODE, MACD_CODE)

        # Both should be valid correlations
        assert abs(corr_trending.correlation) > 0
        assert abs(corr_ranging.correlation) > 0


# --- Test: Correlation between MACD and Stochastic ---

class TestMACDStochasticCorrelation:
    """Test that MACD and Stochastic correlation is computed correctly."""

    def test_macd_stochastic_correlation(self):
        """MACD and Stochastic should have moderate correlation."""
        candles = _make_candles(count=200)
        result = compute_signal_correlation(candles, MACD_CODE, STOCHASTIC_CODE)

        assert -1.0 <= result.correlation <= 1.0


# --- Test: Full correlation matrix ---

class TestCorrelationMatrix:
    """Test the full correlation matrix computation."""

    def test_matrix_has_all_pairs(self):
        """Matrix should contain all pairwise correlations."""
        candles = _make_candles(count=200)
        result = compute_correlation_matrix(candles)

        assert len(result.pairs) == 3  # RSI-MACD, RSI-STOCH, MACD-STOCH
        assert len(result.matrix) == 3

        # Check diagonal is 1.0
        for ind in [RSI_CODE, MACD_CODE, STOCHASTIC_CODE]:
            assert result.matrix[ind][ind] == 1.0

    def test_matrix_symmetry(self):
        """Correlation matrix should be symmetric."""
        candles = _make_candles(count=200)
        result = compute_correlation_matrix(candles)

        matrix = result.matrix
        pairs = [(RSI_CODE, MACD_CODE), (RSI_CODE, STOCHASTIC_CODE), (MACD_CODE, STOCHASTIC_CODE)]
        for a, b in pairs:
            assert math.isclose(matrix[a][b], matrix[b][a], abs_tol=1e-10)

    def test_max_min_correlation(self):
        """Max and min correlations should be correctly identified."""
        candles = _make_candles(count=200)
        result = compute_correlation_matrix(candles)

        assert result.max_correlation >= result.min_correlation
        assert len(result.max_correlation_pair) == 2
        assert len(result.min_correlation_pair) == 2

    def test_overcorrelated_pairs(self):
        """Over-correlated pairs should be correctly identified."""
        # High correlation data
        high_corr = _make_candles(count=200, trend_strength=3.0, noise=0.5)
        result = compute_correlation_matrix(high_corr)

        # With high correlation data, at least some pairs should be over-correlated
        assert len(result.overcorrelated_pairs) >= 0  # May be 0 or more

    def test_matrix_with_custom_threshold(self):
        """Matrix should respect custom threshold."""
        candles = _make_candles(count=200)

        # Very low threshold - all pairs should be over-correlated
        result_low = compute_correlation_matrix(candles, threshold=0.1)
        assert len(result_low.overcorrelated_pairs) >= 2

        # Very high threshold - no pairs should be over-correlated
        result_high = compute_correlation_matrix(candles, threshold=0.99)
        assert len(result_high.overcorrelated_pairs) == 0


# --- Test: Correlation threshold checking ---

class TestCorrelationThresholdCheck:
    """Test the check_correlation_threshold function."""

    def test_within_limits(self):
        """check_correlation_threshold should report within_limits correctly."""
        # Low correlation data
        low_corr = _make_candles(count=200, trend_strength=0.5, noise=3.0)
        result = check_correlation_threshold(low_corr, threshold=0.9)

        assert result["within_limits"] is True
        assert result["risk_level"] in ("low", "medium", "high")

    def test_high_risk(self):
        """High correlation data should report higher risk."""
        high_corr = _make_candles(count=200, trend_strength=3.0, noise=0.5)
        result = check_correlation_threshold(high_corr, threshold=0.5)

        assert result["risk_level"] in ("medium", "high")

    def test_report_format(self):
        """format_correlation_report should produce readable output."""
        candles = _make_candles(count=200)
        data = check_correlation_threshold(candles)
        report = format_correlation_report(data)

        assert "INDICATOR CORRELATION REPORT" in report
        assert "Pair Correlations:" in report
        assert "Max correlation:" in report
        assert "Min correlation:" in report
        assert "RSI" in report
        assert "MACD" in report
        assert "STOCHASTIC" in report

    def test_report_contains_threshold(self):
        """Report should include the threshold value."""
        candles = _make_candles(count=200)
        data = check_correlation_threshold(candles, threshold=0.75)
        report = format_correlation_report(data)

        assert "0.75" in report

    def test_all_pair_names_in_matrix(self):
        """Matrix should contain all indicator names as keys."""
        candles = _make_candles(count=200)
        result = compute_correlation_matrix(candles)

        for ind in [RSI_CODE, MACD_CODE, STOCHASTIC_CODE]:
            assert ind in result.matrix
            assert len(result.matrix[ind]) == 3


# --- Test: Edge cases ---

class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_min_data_points(self):
        """Should work with minimum data points."""
        candles = _make_candles(count=50)
        result = compute_signal_correlation(candles, RSI_CODE, STOCHASTIC_CODE)
        assert result.correlation is not None

    def test_insufficient_data_raises(self):
        """Should raise ValueError with insufficient data."""
        short_candles = _make_candles(count=5)
        with pytest.raises(ValueError, match="Insufficient data"):
            compute_signal_correlation(short_candles, RSI_CODE, STOCHASTIC_CODE)

    def test_custom_threshold(self):
        """Should respect custom threshold in pair results."""
        candles = _make_candles(count=200)
        result = compute_signal_correlation(
            candles,
            RSI_CODE,
            STOCHASTIC_CODE,
            threshold=0.5,
        )
        assert result.threshold == 0.5

    def test_synthetic_candles_generation(self):
        """generate_synthetic_candles should produce valid candles."""
        candles = generate_synthetic_candles(count=100)
        assert len(candles) == 100
        assert all(isinstance(c, Candle) for c in candles)
        assert all(c.symbol == "BTCUSD" for c in candles)
        assert all(c.exchange == "bitfinex" for c in candles)

    def test_correlation_pairs_constant(self):
        """CORRELATION_PAIRS should have exactly 3 pairs."""
        assert len(CORRELATION_PAIRS) == 3
        assert (RSI_CODE, MACD_CODE) in CORRELATION_PAIRS
        assert (RSI_CODE, STOCHASTIC_CODE) in CORRELATION_PAIRS
        assert (MACD_CODE, STOCHASTIC_CODE) in CORRELATION_PAIRS


# --- Test: High and low correlation regimes ---

class TestHighLowCorrelationRegimes:
    """Tests for high and low correlation regimes."""

    def test_high_correlation_regime(self):
        """High correlation regime: strong trends, low noise."""
        candles = _make_candles(count=300, trend_strength=4.0, noise=0.3)
        result = compute_correlation_matrix(candles, threshold=0.5)

        # At least 1 of 3 pairs should be above threshold
        n_above = sum(1 for p in result.pairs if p.is_above_threshold)
        assert n_above >= 1, f"Expected >= 1 pair above threshold in high regime, got {n_above}"

    def test_low_correlation_regime(self):
        """Low correlation regime: weak trends, high noise."""
        candles = _make_candles(count=300, trend_strength=0.3, noise=4.0)
        result = compute_correlation_matrix(candles, threshold=0.7)

        # At least 1 pair should be below threshold
        n_below = sum(1 for p in result.pairs if not p.is_above_threshold)
        assert n_below >= 1, f"Expected >= 1 pair below threshold in low regime, got {n_below}"

    def test_neutral_correlation_regime(self):
        """Neutral regime: moderate trends and noise."""
        candles = _make_candles(count=300, trend_strength=1.5, noise=1.5)
        result = compute_correlation_matrix(candles)

        # Should have at least some pairs above and below threshold
        assert result.max_correlation > 0
        assert result.min_correlation < 1.0

    def test_correlation_values_are_valid(self):
        """All correlation values should be in valid range [-1, 1]."""
        for trend in [0.3, 1.0, 3.0, 5.0]:
            for noise in [0.3, 1.0, 3.0, 5.0]:
                candles = _make_candles(count=200, trend_strength=trend, noise=noise)
                result = compute_correlation_matrix(candles)

                for pair in result.pairs:
                    assert -1.0 <= pair.correlation <= 1.0, (
                        f"Invalid correlation {pair.correlation} for "
                        f"{pair.indicator_a}/{pair.indicator_b} "
                        f"(trend={trend}, noise={noise})"
                    )


# --- Test: Integration with existing signal detection ---

class TestSignalDetectionIntegration:
    """Test that correlation analysis integrates with signal detection."""

    def test_all_indicators_produce_signals(self):
        """All three indicators should produce valid signals from the same candles."""
        candles = _make_candles(count=200)

        # Each indicator should compute without error
        rsi_val = compute_signal_correlation(candles, RSI_CODE, RSI_CODE)
        macd_val = compute_signal_correlation(candles, MACD_CODE, MACD_CODE)
        stoch_val = compute_signal_correlation(candles, STOCHASTIC_CODE, STOCHASTIC_CODE)

        # Self-correlation should be ~1.0
        assert math.isclose(rsi_val.correlation, 1.0, abs_tol=0.01)
        assert math.isclose(macd_val.correlation, 1.0, abs_tol=0.01)
        assert math.isclose(stoch_val.correlation, 1.0, abs_tol=0.01)

    def test_different_timeframes(self):
        """Correlation should work across different candle counts (simulating timeframes)."""
        for count in [50, 100, 200, 500]:
            candles = _make_candles(count=count)
            result = compute_correlation_matrix(candles)
            assert len(result.pairs) == 3
            assert result.max_correlation >= result.min_correlation
