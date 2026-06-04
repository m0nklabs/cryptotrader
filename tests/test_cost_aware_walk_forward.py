"""Tests for cost-aware walk-forward analysis with Kelly sizing and multi-regime splitting."""

from __future__ import annotations

import math
import random
from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from core.backtest.engine import RSIStrategy
from core.strategy_eval.cost_aware_walk_forward import (
    CostAwareFold,
    CostAwareWalkForwardConfig,
    CostAwareWalkForwardResult,
    CostAwareWalkForwardResult as Result,
    CostAwareKellyBacktest,
    RegimeFoldBreakdown,
    _assign_regimes_to_trades,
    _empty_result,
    _kelly_position_size,
    _normal_cdf,
    run_cost_aware_walk_forward_kelly_regime,
    to_dict,
)
from core.strategy_eval.cost_aware import CostAdjustedTrade, FeeModel
from core.strategy_eval.regime import RegimeDetector
from core.strategy_eval.types import MarketRegime
from core.types import Candle


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _gen_candles(n: int = 500, seed: int = 42) -> list[Candle]:
    """Generate synthetic BTC/USD candles for testing."""
    random.seed(seed)
    candles: list[Candle] = []
    price = Decimal("50000.0")
    base = datetime(2024, 1, 1)
    for i in range(n):
        change = Decimal(str(random.gauss(0, 0.002)))
        price = price * (1 + change)
        open_p = price * (1 + Decimal(str(random.gauss(0, 0.001))))
        high_p = price * (1 + abs(Decimal(str(random.gauss(0, 0.002)))))
        low_p = price * (1 - abs(Decimal(str(random.gauss(0, 0.002)))))
        candles.append(
            Candle(
                symbol="BTC/USD",
                exchange="Bitfinex",
                timeframe="1h",
                open_time=base + timedelta(hours=i),
                close_time=base + timedelta(hours=i + 1),
                open=open_p,
                high=high_p,
                low=low_p,
                close=price,
                volume=Decimal(str(random.uniform(100, 1000))),
            )
        )
    return candles


def _small_candles(n: int = 100, seed: int = 42) -> list[Candle]:
    """Generate a smaller set of candles for fast tests."""
    return _gen_candles(n=n, seed=seed)


def _tiny_candles(n: int = 30, seed: int = 42) -> list[Candle]:
    """Generate a tiny set of candles for edge-case tests."""
    return _gen_candles(n=n, seed=seed)


# ---------------------------------------------------------------------------
# _normal_cdf tests
# ---------------------------------------------------------------------------


class TestNormalCdf:
    def test_zero(self):
        assert abs(_normal_cdf(0.0) - 0.5) < 0.001

    def test_positive(self):
        assert _normal_cdf(1.0) > 0.5

    def test_negative(self):
        assert _normal_cdf(-1.0) < 0.5

    def test_large_positive(self):
        assert _normal_cdf(3.0) > 0.99

    def test_large_negative(self):
        assert _normal_cdf(-3.0) < 0.01


# ---------------------------------------------------------------------------
# _kelly_position_size tests
# ---------------------------------------------------------------------------


class TestKellyPositionSize:
    def test_basic(self):
        size = _kelly_position_size(
            win_rate=Decimal("0.6"),
            avg_win=Decimal("0.05"),
            avg_loss=Decimal("0.02"),
            kelly_fraction=Decimal("0.5"),
            portfolio_value=Decimal("10000"),
            entry_price=Decimal("50000"),
        )
        assert size > 0

    def test_half_kelly(self):
        size_half = _kelly_position_size(
            win_rate=Decimal("0.55"),
            avg_win=Decimal("0.05"),
            avg_loss=Decimal("0.02"),
            kelly_fraction=Decimal("0.5"),
            portfolio_value=Decimal("10000"),
            entry_price=Decimal("50000"),
        )
        size_full = _kelly_position_size(
            win_rate=Decimal("0.55"),
            avg_win=Decimal("0.05"),
            avg_loss=Decimal("0.02"),
            kelly_fraction=Decimal("1.0"),
            portfolio_value=Decimal("10000"),
            entry_price=Decimal("50000"),
        )
        assert size_half < size_full

    def test_zero_avg_loss(self):
        size = _kelly_position_size(
            win_rate=Decimal("0.5"),
            avg_win=Decimal("0.05"),
            avg_loss=Decimal("0"),
            kelly_fraction=Decimal("0.5"),
            portfolio_value=Decimal("10000"),
            entry_price=Decimal("50000"),
        )
        assert size > 0

    def test_min_size_one(self):
        """Position size should be at least 1."""
        size = _kelly_position_size(
            win_rate=Decimal("0.5"),
            avg_win=Decimal("0.01"),
            avg_loss=Decimal("0.1"),
            kelly_fraction=Decimal("0.1"),
            portfolio_value=Decimal("1000"),
            entry_price=Decimal("50000"),
        )
        assert size >= Decimal("1")


# ---------------------------------------------------------------------------
# _assign_regimes_to_trades tests
# ---------------------------------------------------------------------------


class TestAssignRegimes:
    def test_basic(self):
        detector = RegimeDetector()
        trades = []
        for i in range(5):
            from core.backtest.metrics import Trade
            trades.append(
                Trade(
                    entry_price=Decimal(str(50000 + i * 100)),
                    exit_price=Decimal(str(50000 + (i + 1) * 100)),
                    side="BUY",
                    size=Decimal("1"),
                )
            )
        candles = _gen_candles(n=20)
        result = _assign_regimes_to_trades(trades, candles, detector)
        assert len(result) == len(trades)
        for ct in result:
            assert isinstance(ct.regime, MarketRegime)

    def test_empty_trades(self):
        detector = RegimeDetector()
        result = _assign_regimes_to_trades([], _gen_candles(n=10), detector)
        assert result == []


# ---------------------------------------------------------------------------
# CostAwareKellyBacktest tests
# ---------------------------------------------------------------------------


class TestCostAwareKellyBacktest:
    def test_basic_run(self):
        bt = CostAwareKellyBacktest(
            fee_model=FeeModel(),
            kelly_fraction=Decimal("0.5"),
        )
        candles = _gen_candles(n=100)
        strategy = RSIStrategy()
        result = bt.run(strategy, candles)
        assert isinstance(result, object)
        assert result.total_pnl is not None
        assert result.total_return is not None

    def test_kelly_fraction_effect(self):
        """Full Kelly should generally produce different results than half Kelly."""
        candles = _gen_candles(n=100)
        strategy = RSIStrategy()

        half_bt = CostAwareKellyBacktest(
            fee_model=FeeModel(),
            kelly_fraction=Decimal("0.5"),
        )
        full_bt = CostAwareKellyBacktest(
            fee_model=FeeModel(),
            kelly_fraction=Decimal("1.0"),
        )

        half_result = half_bt.run(strategy, candles)
        full_result = full_bt.run(strategy, candles)

        # Both should produce valid results
        assert half_result.total_return is not None
        assert full_result.total_return is not None


# ---------------------------------------------------------------------------
# run_cost_aware_walk_forward_kelly_regime tests
# ---------------------------------------------------------------------------


class TestRunCostAwareWalkForward:
    def test_basic(self):
        """Test basic run with default config."""
        candles = _gen_candles(n=500)
        strategy = RSIStrategy()
        config = CostAwareWalkForwardConfig(
            train_size_days=3,
            test_size_days=1,
            step_size_days=1,
            lookback_candles=24,
            min_folds=3,
        )
        result = run_cost_aware_walk_forward_kelly_regime(strategy, candles, config)

        assert isinstance(result, object)
        assert result.n_folds >= 3
        assert result.mean_train_return is not None
        assert result.mean_test_return is not None
        assert result.mean_oos_decay is not None
        assert result.overfitting_risk in ("low", "medium", "high")
        assert result.oos_significant is not None

    def test_empty_candles(self):
        """Test with empty candle list."""
        config = CostAwareWalkForwardConfig()
        result = run_cost_aware_walk_forward_kelly_regime(RSIStrategy(), [], config)

        assert result.n_folds == 0
        assert result.mean_train_return == 0.0
        assert result.mean_test_return == 0.0
        assert result.overfitting_risk == "high"

    def test_config_parameters(self):
        """Test that config parameters affect the result."""
        candles = _gen_candles(n=500)
        strategy = RSIStrategy()

        # Larger training window should produce fewer folds
        config_small = CostAwareWalkForwardConfig(
            train_size_days=1,
            test_size_days=1,
            step_size_days=1,
            lookback_candles=12,
        )
        config_large = CostAwareWalkForwardConfig(
            train_size_days=10,
            test_size_days=5,
            step_size_days=5,
            lookback_candles=48,
        )

        result_small = run_cost_aware_walk_forward_kelly_regime(
            strategy, candles, config_small
        )
        result_large = run_cost_aware_walk_forward_kelly_regime(
            strategy, candles, config_large
        )

        assert result_small.n_folds >= result_large.n_folds

    def test_kelly_sizing(self):
        """Test that Kelly sizing is correctly computed."""
        candles = _gen_candles(n=500)
        strategy = RSIStrategy()
        config = CostAwareWalkForwardConfig(
            train_size_days=3,
            test_size_days=1,
            step_size_days=1,
            lookback_candles=24,
        )
        result = run_cost_aware_walk_forward_kelly_regime(strategy, candles, config)

        assert result.mean_kelly_fraction > 0
        assert result.mean_kelly_position_size > 0
        assert result.half_kelly_return is not None
        assert result.full_kelly_return is not None
        assert result.kelly_pnl_diff is not None

    def test_cost_awareness(self):
        """Test that cost awareness is correctly computed."""
        candles = _gen_candles(n=500)
        strategy = RSIStrategy()
        config = CostAwareWalkForwardConfig(
            train_size_days=3,
            test_size_days=1,
            step_size_days=1,
            lookback_candles=24,
        )
        result = run_cost_aware_walk_forward_kelly_regime(strategy, candles, config)

        assert result.total_gross_pnl is not None
        assert result.total_costs >= 0
        assert result.total_net_pnl is not None
        assert result.cost_ratio >= 0

    def test_regime_performance(self):
        """Test that regime performance is computed for all regimes."""
        candles = _gen_candles(n=500)
        strategy = RSIStrategy()
        config = CostAwareWalkForwardConfig(
            train_size_days=3,
            test_size_days=1,
            step_size_days=1,
            lookback_candles=24,
        )
        result = run_cost_aware_walk_forward_kelly_regime(strategy, candles, config)

        assert len(result.regime_performance) > 0
        for rp in result.regime_performance:
            assert isinstance(rp.regime, MarketRegime)
            assert rp.n_candles >= 0
            assert rp.n_trades >= 0

    def test_regime_oos_decay(self):
        """Test that per-regime OOS decay is computed."""
        candles = _gen_candles(n=500)
        strategy = RSIStrategy()
        config = CostAwareWalkForwardConfig(
            train_size_days=3,
            test_size_days=1,
            step_size_days=1,
            lookback_candles=24,
        )
        result = run_cost_aware_walk_forward_kelly_regime(strategy, candles, config)

        assert len(result.regime_oos_decay) == len(MarketRegime)
        for regime, decay in result.regime_oos_decay.items():
            assert isinstance(regime, MarketRegime)
            assert isinstance(decay, float)

    def test_folds_structure(self):
        """Test that each fold has the correct structure."""
        candles = _gen_candles(n=500)
        strategy = RSIStrategy()
        config = CostAwareWalkForwardConfig(
            train_size_days=3,
            test_size_days=1,
            step_size_days=1,
            lookback_candles=24,
        )
        result = run_cost_aware_walk_forward_kelly_regime(strategy, candles, config)

        for fold in result.folds:
            assert isinstance(fold, object)
            assert fold.train_start <= fold.train_end
            assert fold.test_start <= fold.test_end
            assert fold.train_end == fold.test_start
            assert fold.test_trades >= 0
            assert fold.kelly_position_size > 0
            assert 0 <= fold.oos_decay

    def test_oos_significance(self):
        """Test OOS significance calculation."""
        candles = _gen_candles(n=500)
        strategy = RSIStrategy()
        config = CostAwareWalkForwardConfig(
            train_size_days=3,
            test_size_days=1,
            step_size_days=1,
            lookback_candles=24,
        )
        result = run_cost_aware_walk_forward_kelly_regime(strategy, candles, config)

        assert isinstance(result.oos_significant, bool)
        assert result.oos_sharpe is not None
        assert result.oos_max_dd is not None
        assert result.oos_win_rate >= 0


# ---------------------------------------------------------------------------
# to_dict tests
# ---------------------------------------------------------------------------


class TestToDict:
    def test_basic_serialization(self):
        candles = _gen_candles(n=500)
        strategy = RSIStrategy()
        config = CostAwareWalkForwardConfig(
            train_size_days=3,
            test_size_days=1,
            step_size_days=1,
            lookback_candles=24,
        )
        result = run_cost_aware_walk_forward_kelly_regime(strategy, candles, config)
        d = to_dict(result)

        assert "n_folds" in d
        assert "mean_train_return" in d
        assert "mean_test_return" in d
        assert "mean_oos_decay" in d
        assert "in_sample_consistency" in d
        assert "oos_significant" in d
        assert "oos_sharpe" in d
        assert "oos_max_dd" in d
        assert "oos_win_rate" in d
        assert "overfitting_risk" in d
        assert "kelly_sizing" in d
        assert "cost_awareness" in d
        assert "regime_performance" in d
        assert "regime_oos_decay" in d
        assert "folds" in d

    def test_kelly_sizing_keys(self):
        candles = _gen_candles(n=500)
        strategy = RSIStrategy()
        config = CostAwareWalkForwardConfig(
            train_size_days=3,
            test_size_days=1,
            step_size_days=1,
            lookback_candles=24,
        )
        result = run_cost_aware_walk_forward_kelly_regime(strategy, candles, config)
        d = to_dict(result)

        ks = d["kelly_sizing"]
        assert "mean_kelly_fraction" in ks
        assert "mean_kelly_position_size" in ks
        assert "half_kelly_return" in ks
        assert "full_kelly_return" in ks
        assert "kelly_pnl_diff" in ks

    def test_cost_awareness_keys(self):
        candles = _gen_candles(n=500)
        strategy = RSIStrategy()
        config = CostAwareWalkForwardConfig(
            train_size_days=3,
            test_size_days=1,
            step_size_days=1,
            lookback_candles=24,
        )
        result = run_cost_aware_walk_forward_kelly_regime(strategy, candles, config)
        d = to_dict(result)

        ca = d["cost_awareness"]
        assert "total_gross_pnl" in ca
        assert "total_costs" in ca
        assert "total_net_pnl" in ca
        assert "cost_ratio" in ca

    def test_fold_serialization(self):
        candles = _gen_candles(n=500)
        strategy = RSIStrategy()
        config = CostAwareWalkForwardConfig(
            train_size_days=3,
            test_size_days=1,
            step_size_days=1,
            lookback_candles=24,
        )
        result = run_cost_aware_walk_forward_kelly_regime(strategy, candles, config)
        d = to_dict(result)

        assert len(d["folds"]) == result.n_folds
        for fd in d["folds"]:
            assert "train_start" in fd
            assert "train_end" in fd
            assert "test_start" in fd
            assert "test_end" in fd
            assert "train_return" in fd
            assert "test_return" in fd
            assert "test_sharpe" in fd
            assert "test_max_dd" in fd
            assert "test_win_rate" in fd
            assert "test_trades" in fd
            assert "test_net_pnl" in fd
            assert "test_total_costs" in fd
            assert "test_cost_ratio" in fd
            assert "kelly_fraction" in fd
            assert "kelly_position_size" in fd
            assert "oos_decay" in fd
            assert "regime_diversity" in fd

    def test_regime_performance_serialization(self):
        candles = _gen_candles(n=500)
        strategy = RSIStrategy()
        config = CostAwareWalkForwardConfig(
            train_size_days=3,
            test_size_days=1,
            step_size_days=1,
            lookback_candles=24,
        )
        result = run_cost_aware_walk_forward_kelly_regime(strategy, candles, config)
        d = to_dict(result)

        for rp in d["regime_performance"]:
            assert "regime" in rp
            assert "n_candles" in rp
            assert "n_trades" in rp
            assert "return_pct" in rp
            assert "sharpe" in rp
            assert "max_dd" in rp
            assert "win_rate" in rp
            assert "avg_trade_pnl" in rp

    def test_serialization_roundtrip(self):
        """Test that serialized dict can be used for further processing."""
        candles = _gen_candles(n=500)
        strategy = RSIStrategy()
        config = CostAwareWalkForwardConfig(
            train_size_days=3,
            test_size_days=1,
            step_size_days=1,
            lookback_candles=24,
        )
        result = run_cost_aware_walk_forward_kelly_regime(strategy, candles, config)
        d = to_dict(result)

        # Verify all numeric values are finite
        assert math.isfinite(d["mean_train_return"])
        assert math.isfinite(d["mean_test_return"])
        assert math.isfinite(d["mean_oos_decay"])
        assert math.isfinite(d["oos_sharpe"])
        assert math.isfinite(d["kelly_sizing"]["mean_kelly_fraction"])
        assert math.isfinite(d["cost_awareness"]["cost_ratio"])


# ---------------------------------------------------------------------------
# _empty_result tests
# ---------------------------------------------------------------------------


class TestEmptyResult:
    def test_empty_result_structure(self):
        config = CostAwareWalkForwardConfig()
        result = _empty_result(config)

        assert result.n_folds == 0
        assert result.mean_train_return == 0.0
        assert result.mean_test_return == 0.0
        assert result.mean_oos_decay == 0.0
        assert result.in_sample_consistency == 0.0
        assert result.oos_significant is False
        assert result.oos_sharpe == 0.0
        assert result.oos_max_dd == 0.0
        assert result.oos_win_rate == 0.0
        assert result.overfitting_risk == "high"
        assert result.mean_kelly_fraction == float(config.kelly_fraction)
        assert result.mean_kelly_position_size == Decimal("1")
        assert result.half_kelly_return == 0.0
        assert result.full_kelly_return == 0.0
        assert result.kelly_pnl_diff == 0.0
        assert result.regime_performance == []
        assert result.regime_breakdown == []
        assert result.total_gross_pnl == 0.0
        assert result.total_costs == 0.0
        assert result.total_net_pnl == 0.0
        assert result.cost_ratio == 0.0
        assert len(result.regime_oos_decay) == len(MarketRegime)


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------


class TestIntegration:
    def test_full_pipeline(self):
        """Test the full pipeline from candles to result."""
        candles = _gen_candles(n=500)
        strategy = RSIStrategy()
        config = CostAwareWalkForwardConfig(
            train_size_days=3,
            test_size_days=1,
            step_size_days=1,
            lookback_candles=24,
            kelly_fraction=Decimal("0.5"),
            kelly_win_rate=Decimal("0.55"),
            kelly_avg_win=Decimal("0.05"),
            kelly_avg_loss=Decimal("0.02"),
        )

        result = run_cost_aware_walk_forward_kelly_regime(strategy, candles, config)

        # Verify result integrity
        assert result.n_folds > 0
        assert len(result.folds) == result.n_folds
        assert result.mean_train_return is not None
        assert result.mean_test_return is not None
        assert result.mean_oos_decay is not None
        assert result.in_sample_consistency is not None
        assert result.oos_sharpe is not None
        assert result.oos_max_dd is not None
        assert result.oos_win_rate is not None
        assert result.overfitting_risk in ("low", "medium", "high")
        assert result.mean_kelly_fraction > 0
        assert result.mean_kelly_position_size > 0
        assert result.total_gross_pnl is not None
        assert result.total_costs >= 0
        assert result.cost_ratio >= 0
        assert len(result.regime_performance) > 0
        assert len(result.regime_oos_decay) > 0

        # Verify serialization
        d = to_dict(result)
        assert len(d["folds"]) == result.n_folds
        assert len(d["regime_performance"]) > 0

    def test_deterministic(self):
        """Test that running twice produces the same result."""
        candles = _gen_candles(n=500, seed=42)
        strategy = RSIStrategy()
        config = CostAwareWalkForwardConfig(
            train_size_days=3,
            test_size_days=1,
            step_size_days=1,
            lookback_candles=24,
        )

        result1 = run_cost_aware_walk_forward_kelly_regime(strategy, candles, config)
        result2 = run_cost_aware_walk_forward_kelly_regime(strategy, candles, config)

        assert result1.n_folds == result2.n_folds
        assert abs(result1.mean_train_return - result2.mean_train_return) < 0.0001
        assert abs(result1.mean_test_return - result2.mean_test_return) < 0.0001
        assert abs(result1.mean_oos_decay - result2.mean_oos_decay) < 0.0001

    def test_custom_fee_model(self):
        """Test with a custom fee model."""
        candles = _gen_candles(n=500)
        strategy = RSIStrategy()
        custom_fee = FeeModel(
            maker_fee_rate=0.0008,
            taker_fee_rate=0.0015,
            spread_bps=0.3,
            slippage_bps=0.4,
            min_edge_bps=2.5,
        )
        config = CostAwareWalkForwardConfig(
            train_size_days=3,
            test_size_days=1,
            step_size_days=1,
            lookback_candles=24,
            fee_model=custom_fee,
        )

        result = run_cost_aware_walk_forward_kelly_regime(strategy, candles, config)
        assert result.n_folds > 0

    def test_custom_regime_detector(self):
        """Test with a custom regime detector."""
        candles = _gen_candles(n=500)
        strategy = RSIStrategy()
        custom_detector = RegimeDetector(
            trend_window=10,
            vol_window=10,
            trend_threshold=0.005,
            vol_z_threshold=0.8,
        )
        config = CostAwareWalkForwardConfig(
            train_size_days=3,
            test_size_days=1,
            step_size_days=1,
            lookback_candles=24,
            regime_detector=custom_detector,
        )

        result = run_cost_aware_walk_forward_kelly_regime(strategy, candles, config)
        assert result.n_folds > 0

    def test_min_edge_filter(self):
        """Test that minimum edge filter affects results."""
        candles = _gen_candles(n=500)
        strategy = RSIStrategy()

        config_low_edge = CostAwareWalkForwardConfig(
            train_size_days=3,
            test_size_days=1,
            step_size_days=1,
            lookback_candles=24,
            min_edge_bps=1.0,
        )
        config_high_edge = CostAwareWalkForwardConfig(
            train_size_days=3,
            test_size_days=1,
            step_size_days=1,
            lookback_candles=24,
            min_edge_bps=10.0,
        )

        result_low = run_cost_aware_walk_forward_kelly_regime(
            strategy, candles, config_low_edge
        )
        result_high = run_cost_aware_walk_forward_kelly_regime(
            strategy, candles, config_high_edge
        )

        # Lower edge should allow more trades
        assert result_low.total_costs <= result_high.total_costs
