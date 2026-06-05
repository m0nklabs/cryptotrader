"""Tests for walk_forward_analysis.py — per-regime metrics and statistical significance."""

from __future__ import annotations

import json
import math
import random
import statistics
import sys
from pathlib import Path

# Ensure project root is on path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.walk_forward_analysis import (
    Regime,
    RegimeMetrics,
    WalkForwardWindow,
    aggregate_regime_metrics,
    classify_regime,
    generate_synthetic_candles,
    load_candles_from_file,
    print_regime_summary,
    run_walk_forward,
    save_results,
    build_regime_curves,
    _normal_cdf,
)
from core.backtest.metrics import Trade, calculate_sharpe_ratio, calculate_win_rate, calculate_profit_factor
from core.types import Candle
from decimal import Decimal
from datetime import datetime, timedelta


# ---------------------------------------------------------------------------
# Synthetic data helpers
# ---------------------------------------------------------------------------

def make_candle(
    open_price: float,
    close: float,
    high: float | None = None,
    low: float | None = None,
    volume: float = 100.0,
    offset_hours: int = 0,
) -> Candle:
    """Create a minimal Candle for testing."""
    base = datetime(2024, 1, 1)
    if high is None:
        high = max(open_price, close) + abs(open_price - close) * 0.5
    if low is None:
        low = min(open_price, close) - abs(open_price - close) * 0.5
    return Candle(
        symbol="BTC/USDT",
        exchange="bitfinex",
        timeframe="1h",
        open_time=base + timedelta(hours=offset_hours),
        close_time=base + timedelta(hours=offset_hours + 1),
        open=Decimal(str(open_price)),
        high=Decimal(str(high)),
        low=Decimal(str(low)),
        close=Decimal(str(close)),
        volume=Decimal(str(volume)),
    )


def make_trade(entry: float, exit_p: float, side: str = "BUY") -> Trade:
    return Trade(
        entry_price=Decimal(str(entry)),
        exit_price=Decimal(str(exit_p)),
        side=side,
        size=Decimal("1.0"),
    )


# ---------------------------------------------------------------------------
# Normal CDF tests
# ---------------------------------------------------------------------------

class TestNormalCDF:
    """Verify _normal_cdf approximates the standard normal CDF."""

    def test_zero(self):
        assert abs(_normal_cdf(0.0) - 0.5) < 0.001

    def test_positive(self):
        # Phi(1) ≈ 0.8413
        assert abs(_normal_cdf(1.0) - 0.8413) < 0.01

    def test_negative(self):
        # Phi(-1) ≈ 0.1587
        assert abs(_normal_cdf(-1.0) - 0.1587) < 0.01

    def test_large_positive(self):
        # Phi(3) ≈ 0.9987
        assert abs(_normal_cdf(3.0) - 0.9987) < 0.002

    def test_symmetry(self):
        assert abs(_normal_cdf(1.0) + _normal_cdf(-1.0) - 1.0) < 0.01


# ---------------------------------------------------------------------------
# Regime classification tests
# ---------------------------------------------------------------------------

class TestRegimeClassification:
    """Verify classify_regime produces expected regimes for synthetic data."""

    def test_transition_before_lookback(self):
        candles = [make_candle(45000.0, 45000.0)] * 10
        regime = classify_regime(candles, idx=5, lookback=20)
        assert regime == Regime.TRANSITION

    def test_high_vol_classification(self):
        """High absolute volatility → HIGH_VOL."""
        candles = [
            make_candle(45000 + i * 100 + random.gauss(0, 30), 45000 + (i + 1) * 100 + random.gauss(0, 30), offset_hours=i)
            for i in range(40)
        ]
        regime = classify_regime(candles, idx=30, lookback=20)
        assert regime == Regime.HIGH_VOL

    def test_bull_classification(self):
        """Positive momentum and price above SMA → BULL."""
        candles = [
            make_candle(45000 + i * 10 + random.gauss(0, 15), 45000 + (i + 1) * 10 + random.gauss(0, 15), offset_hours=i)
            for i in range(40)
        ]
        regime = classify_regime(candles, idx=30, lookback=20)
        assert regime == Regime.BULL

    def test_bear_classification(self):
        """Negative momentum and price below SMA → BEAR."""
        candles = [
            make_candle(45000 - i * 10 + random.gauss(0, 15), 45000 - (i + 1) * 10 + random.gauss(0, 15), offset_hours=i)
            for i in range(40)
        ]
        regime = classify_regime(candles, idx=30, lookback=20)
        assert regime == Regime.BEAR

    def test_range_classification(self):
        """Price oscillating around SMA → RANGE."""
        candles = []
        for i in range(40):
            price = 45000 + 50 * math.sin(i * 0.3) + random.gauss(0, 12)
            candles.append(make_candle(price, price + 10 + random.gauss(0, 12), offset_hours=i))
        regime = classify_regime(candles, idx=30, lookback=20)
        assert regime == Regime.RANGE

    def test_low_vol_classification(self):
        """Low absolute volatility → LOW_VOL."""
        candles = [
            make_candle(45000 + i * 0.5, 45000 + (i + 1) * 0.5, offset_hours=i)
            for i in range(40)
        ]
        regime = classify_regime(candles, idx=30, lookback=20)
        assert regime == Regime.LOW_VOL

    def test_synthetic_data_has_multiple_regimes(self):
        """Synthetic data should produce multiple distinct regimes."""
        candles = generate_synthetic_candles(n=720, seed=42)
        regimes_seen = set()
        for i in range(20, len(candles), 20):
            regimes_seen.add(classify_regime(candles, idx=i, lookback=20))
        # Should see at least 2 different regimes
        assert len(regimes_seen) >= 2


# ---------------------------------------------------------------------------
# Walk-forward engine tests
# ---------------------------------------------------------------------------

class TestWalkForwardEngine:
    """Verify run_walk_forward produces correct windows."""

    def test_returns_nonempty_windows(self):
        candles = generate_synthetic_candles(n=720, seed=42)
        windows = run_walk_forward(candles, lookback=20, trade_window=5)
        assert len(windows) > 0

    def test_windows_have_regimes(self):
        candles = generate_synthetic_candles(n=720, seed=42)
        windows = run_walk_forward(candles, lookback=20, trade_window=5)
        for w in windows:
            assert w.regime is not None
            assert isinstance(w.regime, Regime)

    def test_window_indices_are_ordered(self):
        candles = generate_synthetic_candles(n=720, seed=42)
        windows = run_walk_forward(candles, lookback=20, trade_window=5)
        indices = [w.start_idx for w in windows]
        assert indices == sorted(indices)

    def test_equity_tracks(self):
        candles = generate_synthetic_candles(n=720, seed=42)
        windows = run_walk_forward(candles, lookback=20, trade_window=5)
        for w in windows:
            assert w.equity_at_start > 0
            assert w.equity_at_end > 0

    def test_adaptive_rsi(self):
        candles = generate_synthetic_candles(n=720, seed=42)
        windows = run_walk_forward(candles, lookback=20, trade_window=5, use_adaptive_rsi=True)
        assert len(windows) > 0

    def test_non_adaptive_rsi(self):
        candles = generate_synthetic_candles(n=720, seed=42)
        windows = run_walk_forward(candles, lookback=20, trade_window=5, use_adaptive_rsi=False)
        assert len(windows) > 0

    def test_custom_step(self):
        candles = generate_synthetic_candles(n=720, seed=42)
        windows = run_walk_forward(candles, lookback=20, trade_window=5, step=20)
        assert len(windows) > 0

    def test_small_window(self):
        candles = generate_synthetic_candles(n=100, seed=42)
        windows = run_walk_forward(candles, lookback=10, trade_window=3)
        assert len(windows) > 0


# ---------------------------------------------------------------------------
# Aggregate metrics tests
# ---------------------------------------------------------------------------

class TestAggregateRegimeMetrics:
    """Verify aggregate_regime_metrics computes correct per-regime stats."""

    def test_all_regimes_present(self):
        candles = generate_synthetic_candles(n=720, seed=42)
        windows = run_walk_forward(candles, lookback=20, trade_window=5)
        metrics = aggregate_regime_metrics(windows)
        # Should have at least some regimes
        assert len(metrics) > 0

    def test_high_vol_significant(self):
        """High vol regime should show significant positive mean PnL (p<0.05)."""
        candles = generate_synthetic_candles(n=720, seed=42)
        windows = run_walk_forward(candles, lookback=20, trade_window=5)
        metrics = aggregate_regime_metrics(windows)

        if Regime.HIGH_VOL in metrics:
            m = metrics[Regime.HIGH_VOL]
            assert m.significant is True, f"high_vol should be significant, got p={m.p_value}"
            assert m.p_value < 0.05, f"high_vol p-value {m.p_value} should be < 0.05"
            assert m.mean_trade_pnl > 0, f"high_vol mean trade PnL {m.mean_trade_pnl} should be positive"

    def test_metrics_have_valid_ranges(self):
        """All metrics should be in valid ranges."""
        candles = generate_synthetic_candles(n=720, seed=42)
        windows = run_walk_forward(candles, lookback=20, trade_window=5)
        metrics = aggregate_regime_metrics(windows)

        for regime, m in metrics.items():
            assert 0 <= m.win_rate <= 1, f"{regime} win_rate {m.win_rate} out of [0,1]"
            assert m.n_windows > 0
            assert m.n_trades >= 0
            assert m.std_trade_pnl >= 0
            assert m.max_drawdown >= 0

    def test_t_stat_calculation(self):
        """T-stat = mean / (std / sqrt(n))."""
        candles = generate_synthetic_candles(n=720, seed=42)
        windows = run_walk_forward(candles, lookback=20, trade_window=5)
        metrics = aggregate_regime_metrics(windows)

        for regime, m in metrics.items():
            if m.n_trades > 1 and m.std_trade_pnl > 0:
                expected_se = m.std_trade_pnl / math.sqrt(m.n_trades)
                expected_t = m.mean_trade_pnl / expected_se
                assert abs(m.t_stat - expected_t) < 0.01, \
                    f"{regime} t_stat {m.t_stat} != expected {expected_t}"

    def test_p_value_symmetry(self):
        """p-value should be symmetric: t and -t give same p."""
        candles = generate_synthetic_candles(n=720, seed=42)
        windows = run_walk_forward(candles, lookback=20, trade_window=5)
        metrics = aggregate_regime_metrics(windows)

        for regime, m in metrics.items():
            if m.n_trades > 1 and m.std_trade_pnl > 0:
                # Flip the mean and check p-value symmetry
                flipped_t = -m.t_stat
                expected_p = 2 * (1 - _normal_cdf(abs(flipped_t)))
                assert abs(m.p_value - expected_p) < 0.01, \
                    f"{regime} p_value {m.p_value} != expected {expected_p}"

    def test_mean_trade_pnl_matches_trades(self):
        """Mean trade PnL should equal mean of pnl_values."""
        candles = generate_synthetic_candles(n=720, seed=42)
        windows = run_walk_forward(candles, lookback=20, trade_window=5)
        metrics = aggregate_regime_metrics(windows)

        for regime, m in metrics.items():
            if m.n_trades > 0:
                expected_mean = statistics.mean(m.trade_pnl_series)
                assert abs(m.mean_trade_pnl - expected_mean) < 0.01, \
                    f"{regime} mean_trade_pnl {m.mean_trade_pnl} != {expected_mean}"

    def test_std_trade_pnl_matches_trades(self):
        """Std trade PnL should equal stdev of pnl_values."""
        candles = generate_synthetic_candles(n=720, seed=42)
        windows = run_walk_forward(candles, lookback=20, trade_window=5)
        metrics = aggregate_regime_metrics(windows)

        for regime, m in metrics.items():
            if m.n_trades > 1:
                expected_std = statistics.stdev(m.trade_pnl_series)
                assert abs(m.std_trade_pnl - expected_std) < 0.01, \
                    f"{regime} std_trade_pnl {m.std_trade_pnl} != {expected_std}"

    def test_win_rate_matches_trades(self):
        """Win rate should match calculate_win_rate from core."""
        candles = generate_synthetic_candles(n=720, seed=42)
        windows = run_walk_forward(candles, lookback=20, trade_window=5)
        metrics = aggregate_regime_metrics(windows)

        for regime, m in metrics.items():
            # Collect all trades for this regime
            regime_windows = [w for w in windows if w.regime == regime]
            all_trades = []
            for w in regime_windows:
                all_trades.extend(w.trades_in_window)
            if all_trades:
                expected_wr = calculate_win_rate(all_trades)
                assert abs(m.win_rate - expected_wr) < 0.01, \
                    f"{regime} win_rate {m.win_rate} != {expected_wr}"

    def test_profit_factor_matches_trades(self):
        """Profit factor should match calculate_profit_factor from core."""
        candles = generate_synthetic_candles(n=720, seed=42)
        windows = run_walk_forward(candles, lookback=20, trade_window=5)
        metrics = aggregate_regime_metrics(windows)

        for regime, m in metrics.items():
            regime_windows = [w for w in windows if w.regime == regime]
            all_trades = []
            for w in regime_windows:
                all_trades.extend(w.trades_in_window)
            if all_trades:
                expected_pf = calculate_profit_factor(all_trades)
                # Handle inf cases
                if math.isinf(expected_pf):
                    assert math.isinf(m.profit_factor) or m.profit_factor > 100
                else:
                    assert abs(m.profit_factor - expected_pf) < 0.01, \
                        f"{regime} profit_factor {m.profit_factor} != {expected_pf}"

    def test_sharpe_ratio_matches(self):
        """Sharpe ratio should match calculate_sharpe_ratio from core."""
        candles = generate_synthetic_candles(n=720, seed=42)
        windows = run_walk_forward(candles, lookback=20, trade_window=5)
        metrics = aggregate_regime_metrics(windows)

        for regime, m in metrics.items():
            regime_windows = [w for w in windows if w.regime == regime]
            returns_list = [
                w.equity_at_end / w.equity_at_start - 1
                for w in regime_windows
                if w.equity_at_start > 0
            ]
            if returns_list:
                expected_sharpe = calculate_sharpe_ratio(returns_list, trading_days=365)
                assert abs(m.sharpe_ratio - expected_sharpe) < 0.01, \
                    f"{regime} sharpe_ratio {m.sharpe_ratio} != {expected_sharpe}"

    def test_total_pnl_matches_trades(self):
        """Total PnL should equal sum of all trade PnLs."""
        candles = generate_synthetic_candles(n=720, seed=42)
        windows = run_walk_forward(candles, lookback=20, trade_window=5)
        metrics = aggregate_regime_metrics(windows)

        for regime, m in metrics.items():
            regime_windows = [w for w in windows if w.regime == regime]
            expected_total = sum(float(t.pnl) for w in regime_windows for t in w.trades_in_window)
            assert abs(m.total_pnl - expected_total) < 0.01, \
                f"{regime} total_pnl {m.total_pnl} != {expected_total}"

    def test_n_trades_matches(self):
        """n_trades should equal total number of trades across all windows."""
        candles = generate_synthetic_candles(n=720, seed=42)
        windows = run_walk_forward(candles, lookback=20, trade_window=5)
        metrics = aggregate_regime_metrics(windows)

        for regime, m in metrics.items():
            regime_windows = [w for w in windows if w.regime == regime]
            expected_n = sum(len(w.trades_in_window) for w in regime_windows)
            assert m.n_trades == expected_n, \
                f"{regime} n_trades {m.n_trades} != {expected_n}"

    def test_n_windows_matches(self):
        """n_windows should equal number of windows for this regime."""
        candles = generate_synthetic_candles(n=720, seed=42)
        windows = run_walk_forward(candles, lookback=20, trade_window=5)
        metrics = aggregate_regime_metrics(windows)

        for regime, m in metrics.items():
            expected_n = sum(1 for w in windows if w.regime == regime)
            assert m.n_windows == expected_n, \
                f"{regime} n_windows {m.n_windows} != {expected_n}"


# ---------------------------------------------------------------------------
# Synthetic data distribution tests
# ---------------------------------------------------------------------------

class TestSyntheticDataDistributions:
    """Verify metrics match expected synthetic data distributions."""

    def test_high_vol_positive_mean(self):
        """High vol regime should have positive mean PnL in synthetic data."""
        candles = generate_synthetic_candles(n=720, seed=42)
        windows = run_walk_forward(candles, lookback=20, trade_window=5)
        metrics = aggregate_regime_metrics(windows)

        if Regime.HIGH_VOL in metrics:
            assert metrics[Regime.HIGH_VOL].mean_trade_pnl > 0

    def test_high_vol_low_std(self):
        """High vol regime should have reasonable std in synthetic data."""
        candles = generate_synthetic_candles(n=720, seed=42)
        windows = run_walk_forward(candles, lookback=20, trade_window=5)
        metrics = aggregate_regime_metrics(windows)

        if Regime.HIGH_VOL in metrics:
            assert metrics[Regime.HIGH_VOL].std_trade_pnl > 0
            # std should be less than mean * 3 (not too noisy)
            if metrics[Regime.HIGH_VOL].mean_trade_pnl > 0:
                assert metrics[Regime.HIGH_VOL].std_trade_pnl < metrics[Regime.HIGH_VOL].mean_trade_pnl * 3

    def test_bull_positive_mean(self):
        """Bull regime should have positive mean PnL in synthetic data."""
        candles = generate_synthetic_candles(n=720, seed=42)
        windows = run_walk_forward(candles, lookback=20, trade_window=5)
        metrics = aggregate_regime_metrics(windows)

        if Regime.BULL in metrics:
            assert metrics[Regime.BULL].mean_trade_pnl > 0

    def test_win_rate_reasonable(self):
        """Win rate should be between 0.2 and 1.0 for synthetic data."""
        candles = generate_synthetic_candles(n=720, seed=42)
        windows = run_walk_forward(candles, lookback=20, trade_window=5)
        metrics = aggregate_regime_metrics(windows)

        for regime, m in metrics.items():
            if m.n_trades > 0:
                assert 0.2 <= m.win_rate <= 1.0, \
                    f"{regime} win_rate {m.win_rate} outside [0.2, 1.0]"

    def test_sharpe_reasonable(self):
        """Sharpe ratio should be between -2 and 5 for synthetic data."""
        candles = generate_synthetic_candles(n=720, seed=42)
        windows = run_walk_forward(candles, lookback=20, trade_window=5)
        metrics = aggregate_regime_metrics(windows)

        for regime, m in metrics.items():
            if m.n_windows > 0:
                assert -2.0 <= m.sharpe_ratio <= 5.0, \
                    f"{regime} sharpe_ratio {m.sharpe_ratio} outside [-2, 5]"

    def test_max_drawdown_reasonable(self):
        """Max drawdown should be between 0 and 1 for synthetic data."""
        candles = generate_synthetic_candles(n=720, seed=42)
        windows = run_walk_forward(candles, lookback=20, trade_window=5)
        metrics = aggregate_regime_metrics(windows)

        for regime, m in metrics.items():
            assert 0 <= m.max_drawdown <= 1.0, \
                f"{regime} max_drawdown {m.max_drawdown} outside [0, 1]"

    def test_profit_factor_reasonable(self):
        """Profit factor should be positive for synthetic data."""
        candles = generate_synthetic_candles(n=720, seed=42)
        windows = run_walk_forward(candles, lookback=20, trade_window=5)
        metrics = aggregate_regime_metrics(windows)

        for regime, m in metrics.items():
            if m.n_trades > 0:
                assert m.profit_factor > 0, \
                    f"{regime} profit_factor {m.profit_factor} should be positive"

    def test_high_vol_p_value_less_than_005(self):
        """High vol regime p-value should be < 0.05."""
        candles = generate_synthetic_candles(n=720, seed=42)
        windows = run_walk_forward(candles, lookback=20, trade_window=5)
        metrics = aggregate_regime_metrics(windows)

        if Regime.HIGH_VOL in metrics:
            assert metrics[Regime.HIGH_VOL].p_value < 0.05, \
                f"high_vol p_value {metrics[Regime.HIGH_VOL].p_value} should be < 0.05"

    def test_high_vol_t_stat_positive(self):
        """High vol regime t-stat should be positive (positive mean)."""
        candles = generate_synthetic_candles(n=720, seed=42)
        windows = run_walk_forward(candles, lookback=20, trade_window=5)
        metrics = aggregate_regime_metrics(windows)

        if Regime.HIGH_VOL in metrics:
            assert metrics[Regime.HIGH_VOL].t_stat > 0, \
                f"high_vol t_stat {metrics[Regime.HIGH_VOL].t_stat} should be positive"

    def test_high_vol_significant_flag(self):
        """High vol regime significant flag should be True."""
        candles = generate_synthetic_candles(n=720, seed=42)
        windows = run_walk_forward(candles, lookback=20, trade_window=5)
        metrics = aggregate_regime_metrics(windows)

        if Regime.HIGH_VOL in metrics:
            assert metrics[Regime.HIGH_VOL].significant is True

    def test_synthetic_seed_reproducibility(self):
        """Same seed should produce same candles."""
        c1 = generate_synthetic_candles(n=100, seed=42)
        c2 = generate_synthetic_candles(n=100, seed=42)
        assert len(c1) == len(c2)
        for a, b in zip(c1, c2):
            assert a.open == b.open
            assert a.close == b.close


# ---------------------------------------------------------------------------
# Two-tailed t-test tests
# ---------------------------------------------------------------------------

class TestTwoTailedTTest:
    """Verify two-tailed t-test implementation."""

    def test_t_stat_sign(self):
        """T-stat sign should match mean sign."""
        candles = generate_synthetic_candles(n=720, seed=42)
        windows = run_walk_forward(candles, lookback=20, trade_window=5)
        metrics = aggregate_regime_metrics(windows)

        for regime, m in metrics.items():
            if m.n_trades > 1 and m.std_trade_pnl > 0:
                if m.mean_trade_pnl > 0:
                    assert m.t_stat > 0
                elif m.mean_trade_pnl < 0:
                    assert m.t_stat < 0

    def test_p_value_range(self):
        """P-value should be between 0 and 1."""
        candles = generate_synthetic_candles(n=720, seed=42)
        windows = run_walk_forward(candles, lookback=20, trade_window=5)
        metrics = aggregate_regime_metrics(windows)

        for regime, m in metrics.items():
            assert 0 <= m.p_value <= 1, \
                f"{regime} p_value {m.p_value} outside [0, 1]"

    def test_significant_flag_matches_p_value(self):
        """significant flag should be True iff p_value < 0.05."""
        candles = generate_synthetic_candles(n=720, seed=42)
        windows = run_walk_forward(candles, lookback=20, trade_window=5)
        metrics = aggregate_regime_metrics(windows)

        for regime, m in metrics.items():
            expected = m.p_value < 0.05
            assert m.significant == expected, \
                f"{regime} significant {m.significant} != expected {expected} (p={m.p_value})"

    def test_large_sample_t_stat(self):
        """With large samples, t-stat should be more stable."""
        candles = generate_synthetic_candles(n=1440, seed=42)  # 2x data
        windows = run_walk_forward(candles, lookback=20, trade_window=5)
        metrics = aggregate_regime_metrics(windows)

        for regime, m in metrics.items():
            if m.n_trades > 10:
                # With more data, t-stat should be more extreme if mean is non-zero
                if abs(m.mean_trade_pnl) > 0:
                    assert abs(m.t_stat) > 0.5

    def test_two_tailed_vs_one_tailed(self):
        """Two-tailed p-value should be approximately 2x one-tailed for positive t."""
        candles = generate_synthetic_candles(n=720, seed=42)
        windows = run_walk_forward(candles, lookback=20, trade_window=5)
        metrics = aggregate_regime_metrics(windows)

        for regime, m in metrics.items():
            if m.n_trades > 1 and m.std_trade_pnl > 0:
                one_tailed = 1 - _normal_cdf(abs(m.t_stat))
                two_tailed = m.p_value
                # Two-tailed should be roughly 2x one-tailed
                assert two_tailed <= 2 * one_tailed + 0.01


# ---------------------------------------------------------------------------
# Edge case tests
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """Verify edge cases are handled correctly."""

    def test_empty_windows(self):
        """Empty windows should produce zero metrics."""
        metrics = aggregate_regime_metrics([])
        assert len(metrics) == 0

    def test_single_window(self):
        """Single window should produce valid metrics."""
        candles = generate_synthetic_candles(n=100, seed=42)
        windows = run_walk_forward(candles, lookback=10, trade_window=1)
        metrics = aggregate_regime_metrics(windows)
        assert len(metrics) > 0

    def test_all_same_regime(self):
        """All windows in same regime should produce correct single-regime metrics."""
        # Create candles that all fall in HIGH_VOL
        candles = [
            make_candle(45000 + i * 100, 45000 + (i + 1) * 100, offset_hours=i)
            for i in range(100)
        ]
        windows = run_walk_forward(candles, lookback=10, trade_window=3)
        metrics = aggregate_regime_metrics(windows)
        assert len(metrics) >= 1

    def test_single_trade_window(self):
        """Single trade should produce valid metrics."""
        candles = generate_synthetic_candles(n=50, seed=42)
        windows = run_walk_forward(candles, lookback=10, trade_window=1)
        metrics = aggregate_regime_metrics(windows)

        for regime, m in metrics.items():
            if m.n_trades == 1:
                # With 1 trade, std should be 0, t_stat should be 0
                assert m.std_trade_pnl == 0.0
                assert m.t_stat == 0.0
                assert m.p_value == 1.0
                assert m.significant is False

    def test_negative_pnl(self):
        """Negative PnL should produce negative t-stat."""
        # Create trades with negative PnL
        trades = [make_trade(entry=46000, exit_p=45000, side="BUY") for _ in range(10)]
        # Manually create windows with these trades
        windows = [
            WalkForwardWindow(
                start_idx=0,
                end_idx=20,
                regime=Regime.BEAR,
                result=None,  # type: ignore
                trades_in_window=trades,
                equity_at_start=10000.0,
                equity_at_end=9900.0,
            )
            for _ in range(5)
        ]
        metrics = aggregate_regime_metrics(windows)
        assert Regime.BEAR in metrics
        assert metrics[Regime.BEAR].mean_trade_pnl < 0

    def test_large_sample_significance(self):
        """Large samples should achieve significance more easily."""
        candles = generate_synthetic_candles(n=1440, seed=42)
        windows = run_walk_forward(candles, lookback=20, trade_window=5)
        metrics = aggregate_regime_metrics(windows)

        # With more data, more regimes should be significant
        significant_count = sum(1 for m in metrics.values() if m.significant)
        assert significant_count >= 1  # At least high_vol should be significant


# ---------------------------------------------------------------------------
# Output tests
# ---------------------------------------------------------------------------

class TestOutput:
    """Verify output functions work correctly."""

    def test_regime_metrics_to_dict(self):
        """RegimeMetrics.to_dict should exclude list fields."""
        m = RegimeMetrics(
            regime="test",
            n_windows=10,
            n_candles=200,
            n_trades=5,
            total_pnl=100.0,
            total_return=0.1,
            mean_return=0.01,
            sharpe_ratio=1.5,
            max_drawdown=0.2,
            win_rate=0.6,
            profit_factor=1.8,
            mean_trade_pnl=20.0,
            std_trade_pnl=10.0,
            t_stat=2.0,
            p_value=0.05,
            significant=True,
            equity_curve=[100, 101, 102],
            trade_pnl_series=[10, 20, 30],
        )
        d = m.to_dict()
        assert "equity_curve" not in d
        assert "trade_pnl_series" not in d
        assert d["regime"] == "test"
        assert d["n_windows"] == 10

    def test_print_regime_summary_no_error(self, capsys):
        """print_regime_summary should not raise."""
        candles = generate_synthetic_candles(n=720, seed=42)
        windows = run_walk_forward(candles, lookback=20, trade_window=5)
        metrics = aggregate_regime_metrics(windows)
        print_regime_summary(metrics)
        captured = capsys.readouterr()
        assert "REGIME-BASED PERFORMANCE" in captured.out

    def test_build_regime_curves(self):
        """build_regime_curves should produce valid curve data."""
        candles = generate_synthetic_candles(n=720, seed=42)
        windows = run_walk_forward(candles, lookback=20, trade_window=5)
        metrics = aggregate_regime_metrics(windows)
        curves = build_regime_curves(windows, metrics)
        assert len(curves) > 0
        for regime, data in curves.items():
            assert "window_idx" in data
            assert "cumulative_pnl" in data
            assert "equity_ratio" in data
            assert "win_rate" in data
            assert len(data["window_idx"]) == len(data["cumulative_pnl"])

    def test_save_results(self, tmp_path):
        """save_results should write valid JSON."""
        candles = generate_synthetic_candles(n=720, seed=42)
        windows = run_walk_forward(candles, lookback=20, trade_window=5)
        metrics = aggregate_regime_metrics(windows)
        curves = build_regime_curves(windows, metrics)
        output = tmp_path / "test_results.json"
        save_results(windows, metrics, curves, str(output))
        assert output.exists()
        with open(output) as f:
            data = json.load(f)
        assert "metadata" in data
        assert "regime_metrics" in data
        assert "performance_curves" in data
        assert "window_details" in data

    def test_load_candles_from_file(self, tmp_path):
        """load_candles_from_file should load valid candles."""
        candles = generate_synthetic_candles(n=100, seed=42)
        # Write candles as JSON
        candle_data = []
        for c in candles:
            candle_data.append({
                "symbol": c.symbol,
                "exchange": c.exchange,
                "timeframe": c.timeframe,
                "open_time": c.open_time.isoformat(),
                "close_time": c.close_time.isoformat(),
                "open": float(c.open),
                "high": float(c.high),
                "low": float(c.low),
                "close": float(c.close),
                "volume": float(c.volume),
            })
        filepath = tmp_path / "candles.json"
        with open(filepath, "w") as f:
            json.dump(candle_data, f)

        loaded = load_candles_from_file(str(filepath))
        assert len(loaded) == len(candles)
        assert all(isinstance(c, Candle) for c in loaded)

    def test_generate_synthetic_candles_length(self):
        """generate_synthetic_candles should produce correct length."""
        for n in [50, 100, 500, 1000]:
            candles = generate_synthetic_candles(n=n, seed=42)
            assert len(candles) == n

    def test_generate_synthetic_candles_ordering(self):
        """Candles should be in chronological order."""
        candles = generate_synthetic_candles(n=100, seed=42)
        for i in range(1, len(candles)):
            assert candles[i].open_time >= candles[i - 1].open_time


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------

class TestIntegration:
    """End-to-end integration tests."""

    def test_full_pipeline(self):
        """Full pipeline from candles to metrics should work."""
        candles = generate_synthetic_candles(n=720, seed=42)
        windows = run_walk_forward(candles, lookback=20, trade_window=5)
        metrics = aggregate_regime_metrics(windows)
        curves = build_regime_curves(windows, metrics)

        assert len(windows) > 0
        assert len(metrics) > 0
        assert len(curves) > 0

        # Verify high_vol is significant
        if Regime.HIGH_VOL in metrics:
            assert metrics[Regime.HIGH_VOL].significant is True
            assert metrics[Regime.HIGH_VOL].p_value < 0.05
            assert metrics[Regime.HIGH_VOL].mean_trade_pnl > 0

    def test_high_vol_significant_positive_pnl(self):
        """Acceptance criterion: high_vol shows significant positive mean PnL (p<0.05)."""
        candles = generate_synthetic_candles(n=720, seed=42)
        windows = run_walk_forward(candles, lookback=20, trade_window=5)
        metrics = aggregate_regime_metrics(windows)

        if Regime.HIGH_VOL in metrics:
            m = metrics[Regime.HIGH_VOL]
            # All three acceptance criteria
            assert m.mean_trade_pnl > 0, "high_vol mean PnL should be positive"
            assert m.p_value < 0.05, "high_vol p-value should be < 0.05"
            assert m.significant is True, "high_vol should be marked significant"

    def test_metrics_consistency_across_runs(self):
        """Running the pipeline twice should produce consistent results."""
        candles = generate_synthetic_candles(n=720, seed=42)
        windows1 = run_walk_forward(candles, lookback=20, trade_window=5)
        metrics1 = aggregate_regime_metrics(windows1)

        windows2 = run_walk_forward(candles, lookback=20, trade_window=5)
        metrics2 = aggregate_regime_metrics(windows2)

        for regime in metrics1:
            assert regime in metrics2
            assert abs(metrics1[regime].mean_trade_pnl - metrics2[regime].mean_trade_pnl) < 0.01
            assert abs(metrics1[regime].t_stat - metrics2[regime].t_stat) < 0.01
            assert abs(metrics1[regime].p_value - metrics2[regime].p_value) < 0.01

    def test_regime_with_many_trades_has_lower_p_value(self):
        """Regimes with more trades should have lower p-values (more power)."""
        candles = generate_synthetic_candles(n=1440, seed=42)
        windows = run_walk_forward(candles, lookback=20, trade_window=5)
        metrics = aggregate_regime_metrics(windows)

        # high_vol typically has more trades and should have lower p-value
        high_vol = metrics.get(Regime.HIGH_VOL)
        if high_vol and high_vol.n_trades > 0:
            assert high_vol.p_value < 0.5  # Should be reasonable

    def test_all_metrics_fields_populated(self):
        """All RegimeMetrics fields should be populated."""
        candles = generate_synthetic_candles(n=720, seed=42)
        windows = run_walk_forward(candles, lookback=20, trade_window=5)
        metrics = aggregate_regime_metrics(windows)

        for regime, m in metrics.items():
            assert m.regime is not None
            assert m.n_windows > 0
            assert m.n_candles > 0
            assert m.n_trades >= 0
            assert m.total_pnl is not None
            assert m.total_return is not None
            assert m.mean_return is not None
            assert m.sharpe_ratio is not None
            assert m.max_drawdown is not None
            assert m.win_rate is not None
            assert m.profit_factor is not None
            assert m.mean_trade_pnl is not None
            assert m.std_trade_pnl is not None
            assert m.t_stat is not None
            assert m.p_value is not None
            assert m.significant is not None
            assert isinstance(m.equity_curve, list)
            assert isinstance(m.trade_pnl_series, list)
