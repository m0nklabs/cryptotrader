"""Tests for Kelly sizing comparison module."""

from decimal import Decimal
from core.backtest.engine import BacktestResult, Trade
from core.strategy_eval.kelly_comparison import (
    KellyBacktestResult,
    KellySizingComparison,
    KellySizingConfig,
    calculate_kelly_metrics,
    compare_kelly_sizing,
    run_kelly_backtest,
)


class TestKellySizingConfig:
    """Tests for KellySizingConfig."""

    def test_default_config(self):
        """Test default configuration values."""
        config = KellySizingConfig()
        assert config.half_kelly_fraction == Decimal("0.5")
        assert config.full_kelly_fraction == Decimal("1.0")
        assert config.portfolio_value == Decimal("10000")

    def test_custom_config(self):
        """Test custom configuration values."""
        config = KellySizingConfig(
            half_kelly_fraction=Decimal("0.25"),
            full_kelly_fraction=Decimal("1.0"),
            portfolio_value=Decimal("50000"),
        )
        assert config.half_kelly_fraction == Decimal("0.25")
        assert config.portfolio_value == Decimal("50000")


class TestCalculateKellyMetrics:
    """Tests for calculate_kelly_metrics."""

    def test_basic_calculation(self):
        """Test basic Kelly metric calculation."""
        trades = [
            Trade(entry_price=Decimal("100"), exit_price=Decimal("110"), side="BUY"),
            Trade(entry_price=Decimal("100"), exit_price=Decimal("90"), side="SELL"),
            Trade(entry_price=Decimal("100"), exit_price=Decimal("120"), side="BUY"),
        ]
        equity_curve = [10000.0, 10100.0, 10000.0, 10200.0]

        result = calculate_kelly_metrics(
            trades=trades,
            equity_curve=equity_curve,
            kelly_fraction=Decimal("0.5"),
            win_rate=Decimal("0.667"),
            avg_win=Decimal("10"),
            avg_loss=Decimal("10"),
            portfolio_value=Decimal("10000"),
            entry_price=Decimal("100"),
            stop_loss_price=Decimal("95"),
        )

        assert isinstance(result, KellyBacktestResult)
        assert result.kelly_fraction == Decimal("0.5")
        assert result.position_size > 0

    def test_half_vs_full_kelly_ratio(self):
        """Test that full-Kelly produces roughly 2x the position size of half-Kelly."""
        trades = [
            Trade(entry_price=Decimal("76402"), exit_price=Decimal("79976"), side="SELL"),
            Trade(entry_price=Decimal("79976"), exit_price=Decimal("81865"), side="BUY"),
        ]
        equity_curve = [10000.0, 10100.0, 10200.0]

        half = calculate_kelly_metrics(
            trades=trades,
            equity_curve=equity_curve,
            kelly_fraction=Decimal("0.5"),
            win_rate=Decimal("0.6"),
            avg_win=Decimal("1000"),
            avg_loss=Decimal("500"),
            portfolio_value=Decimal("10000"),
            entry_price=Decimal("76402"),
            stop_loss_price=Decimal("72582"),
        )

        full = calculate_kelly_metrics(
            trades=trades,
            equity_curve=equity_curve,
            kelly_fraction=Decimal("1.0"),
            win_rate=Decimal("0.6"),
            avg_win=Decimal("1000"),
            avg_loss=Decimal("500"),
            portfolio_value=Decimal("10000"),
            entry_price=Decimal("76402"),
            stop_loss_price=Decimal("72582"),
        )

        # Full Kelly should be roughly 2x half Kelly
        assert full.position_size > half.position_size
        ratio = float(full.position_size / half.position_size)
        assert 1.9 <= ratio <= 2.1


class TestCompareKellySizing:
    """Tests for compare_kelly_sizing."""

    def test_compare_basic(self):
        """Test basic comparison."""
        trades = [
            Trade(entry_price=Decimal("100"), exit_price=Decimal("110"), side="BUY"),
            Trade(entry_price=Decimal("100"), exit_price=Decimal("95"), side="SELL"),
        ]
        equity_curve = [10000.0, 10100.0, 10050.0]

        result = compare_kelly_sizing(trades=trades, equity_curve=equity_curve)

        assert isinstance(result, KellySizingComparison)
        assert result.half_kelly.kelly_fraction == Decimal("0.5")
        assert result.full_kelly.kelly_fraction == Decimal("1.0")

    def test_compare_with_custom_config(self):
        """Test comparison with custom configuration."""
        trades = [
            Trade(entry_price=Decimal("100"), exit_price=Decimal("110"), side="BUY"),
        ]
        equity_curve = [10000.0, 10100.0]

        config = KellySizingConfig(
            portfolio_value=Decimal("50000"),
            win_rate=Decimal("0.7"),
        )

        result = compare_kelly_sizing(trades=trades, equity_curve=equity_curve, config=config)

        assert isinstance(result, KellySizingComparison)
        assert "pnl_diff" in result.comparison
        assert "position_size_ratio" in result.comparison

    def test_compare_serialization(self):
        """Test that to_dict serializes correctly."""
        trades = [
            Trade(entry_price=Decimal("100"), exit_price=Decimal("110"), side="BUY"),
        ]
        equity_curve = [10000.0, 10100.0]

        result = compare_kelly_sizing(trades=trades, equity_curve=equity_curve)
        d = result.to_dict()

        assert "half_kelly" in d
        assert "full_kelly" in d
        assert "comparison" in d
        assert "kelly_fraction" in d["half_kelly"]
        assert "total_pnl" in d["full_kelly"]


class TestRunKellyBacktest:
    """Tests for run_kelly_backtest."""

    def test_run_on_backtest_result(self):
        """Test running Kelly comparison on a BacktestResult."""
        trades = [
            Trade(entry_price=Decimal("100"), exit_price=Decimal("110"), side="BUY"),
            Trade(entry_price=Decimal("100"), exit_price=Decimal("90"), side="SELL"),
        ]
        equity_curve = [10000.0, 10100.0, 10000.0]

        backtest_result = BacktestResult(
            trades=trades,
            equity_curve=equity_curve,
            total_pnl=0.0,
            total_return=0.0,
            sharpe_ratio=0.5,
            max_drawdown=0.1,
            win_rate=0.5,
            profit_factor=1.0,
        )

        result = run_kelly_backtest(backtest_result)

        assert isinstance(result, KellySizingComparison)
        assert result.half_kelly.total_pnl == backtest_result.total_pnl

    def test_run_with_config(self):
        """Test running with custom config."""
        trades = [
            Trade(entry_price=Decimal("100"), exit_price=Decimal("120"), side="BUY"),
        ]
        equity_curve = [10000.0, 10200.0]

        config = KellySizingConfig(
            portfolio_value=Decimal("20000"),
            win_rate=Decimal("0.8"),
            avg_win=Decimal("20"),
            avg_loss=Decimal("10"),
        )

        result = run_kelly_backtest(
            BacktestResult(
                trades=trades,
                equity_curve=equity_curve,
                total_pnl=200.0,
                total_return=0.02,
                sharpe_ratio=0.5,
                max_drawdown=0.05,
                win_rate=0.8,
                profit_factor=1.5,
            ),
            config=config,
        )

        assert isinstance(result, KellySizingComparison)


class TestToDict:
    """Tests for to_dict serialization."""

    def test_to_dict(self):
        """Test to_dict function."""
        trades = [
            Trade(entry_price=Decimal("100"), exit_price=Decimal("110"), side="BUY"),
        ]
        equity_curve = [10000.0, 10100.0]

        result = compare_kelly_sizing(trades=trades, equity_curve=equity_curve)

        from core.strategy_eval.kelly_comparison import to_dict

        d = to_dict(result)

        assert isinstance(d, dict)
        assert "half_kelly" in d
        assert "full_kelly" in d
        assert "comparison" in d
