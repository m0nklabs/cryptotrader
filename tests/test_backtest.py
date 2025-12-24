"""Tests for backtesting metrics calculations."""

from decimal import Decimal
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.backtest.metrics import (
    Trade,
    calculate_max_drawdown,
    calculate_profit_factor,
    calculate_sharpe_ratio,
    calculate_win_rate,
)


# ========== Trade tests ==========


def test_trade_calculates_pnl_for_buy() -> None:
    """Trade calculates P&L correctly for BUY side."""
    trade = Trade(
        entry_price=Decimal("100.0"),
        exit_price=Decimal("110.0"),
        side="BUY",
        size=Decimal("1.0"),
    )
    assert trade.pnl == Decimal("10.0")


def test_trade_calculates_pnl_for_sell() -> None:
    """Trade calculates P&L correctly for SELL side."""
    trade = Trade(
        entry_price=Decimal("110.0"),
        exit_price=Decimal("100.0"),
        side="SELL",
        size=Decimal("1.0"),
    )
    assert trade.pnl == Decimal("10.0")


def test_trade_handles_loss() -> None:
    """Trade handles losing trades correctly."""
    trade = Trade(
        entry_price=Decimal("100.0"),
        exit_price=Decimal("90.0"),
        side="BUY",
        size=Decimal("1.0"),
    )
    assert trade.pnl == Decimal("-10.0")


# ========== Sharpe Ratio tests ==========


def test_sharpe_ratio_with_empty_returns() -> None:
    """Sharpe ratio returns 0 for empty returns."""
    assert calculate_sharpe_ratio([]) == 0.0


def test_sharpe_ratio_with_single_return() -> None:
    """Sharpe ratio returns 0 for single return."""
    assert calculate_sharpe_ratio([0.01]) == 0.0


def test_sharpe_ratio_with_zero_std() -> None:
    """Sharpe ratio returns 0 when std dev is 0."""
    returns = [0.01, 0.01, 0.01, 0.01]
    assert calculate_sharpe_ratio(returns) == 0.0


def test_sharpe_ratio_with_positive_returns() -> None:
    """Sharpe ratio is positive for positive returns."""
    returns = [0.01, 0.02, 0.015, 0.012, 0.018]
    sharpe = calculate_sharpe_ratio(returns)
    assert sharpe > 0


def test_sharpe_ratio_with_negative_returns() -> None:
    """Sharpe ratio is negative for negative returns."""
    returns = [-0.01, -0.02, -0.015, -0.012, -0.018]
    sharpe = calculate_sharpe_ratio(returns)
    assert sharpe < 0


# ========== Max Drawdown tests ==========


def test_max_drawdown_with_empty_curve() -> None:
    """Max drawdown returns 0 for empty equity curve."""
    assert calculate_max_drawdown([]) == 0.0


def test_max_drawdown_with_single_value() -> None:
    """Max drawdown returns 0 for single value."""
    assert calculate_max_drawdown([100.0]) == 0.0


def test_max_drawdown_with_no_drawdown() -> None:
    """Max drawdown is 0 when equity only increases."""
    equity = [100.0, 110.0, 120.0, 130.0]
    assert calculate_max_drawdown(equity) == 0.0


def test_max_drawdown_calculates_correctly() -> None:
    """Max drawdown calculates correctly for typical equity curve."""
    equity = [100.0, 110.0, 90.0, 85.0, 95.0]  # Peak at 110, trough at 85
    max_dd = calculate_max_drawdown(equity)
    expected = (110.0 - 85.0) / 110.0  # ~0.227
    assert abs(max_dd - expected) < 0.001


def test_max_drawdown_tracks_highest_peak() -> None:
    """Max drawdown tracks the highest peak seen."""
    equity = [100.0, 120.0, 110.0, 130.0, 100.0]  # Peak at 130, trough at 100
    max_dd = calculate_max_drawdown(equity)
    expected = (130.0 - 100.0) / 130.0  # ~0.231
    assert abs(max_dd - expected) < 0.001


# ========== Win Rate tests ==========


def test_win_rate_with_no_trades() -> None:
    """Win rate returns 0 for no trades."""
    assert calculate_win_rate([]) == 0.0


def test_win_rate_all_winners() -> None:
    """Win rate is 100% when all trades win."""
    trades = [
        Trade(Decimal("100"), Decimal("110"), "BUY"),
        Trade(Decimal("100"), Decimal("105"), "BUY"),
    ]
    assert calculate_win_rate(trades) == 1.0


def test_win_rate_all_losers() -> None:
    """Win rate is 0% when all trades lose."""
    trades = [
        Trade(Decimal("100"), Decimal("90"), "BUY"),
        Trade(Decimal("100"), Decimal("95"), "BUY"),
    ]
    assert calculate_win_rate(trades) == 0.0


def test_win_rate_mixed() -> None:
    """Win rate calculates correctly for mixed results."""
    trades = [
        Trade(Decimal("100"), Decimal("110"), "BUY"),  # Win
        Trade(Decimal("100"), Decimal("90"), "BUY"),  # Loss
        Trade(Decimal("110"), Decimal("100"), "SELL"),  # Win
    ]
    assert calculate_win_rate(trades) == 2.0 / 3.0


# ========== Profit Factor tests ==========


def test_profit_factor_with_no_trades() -> None:
    """Profit factor returns 0 for no trades."""
    assert calculate_profit_factor([]) == 0.0


def test_profit_factor_only_winners() -> None:
    """Profit factor is infinity with only winners."""
    trades = [
        Trade(Decimal("100"), Decimal("110"), "BUY"),
        Trade(Decimal("100"), Decimal("105"), "BUY"),
    ]
    assert calculate_profit_factor(trades) == float("inf")


def test_profit_factor_only_losers() -> None:
    """Profit factor is 0 with only losers."""
    trades = [
        Trade(Decimal("100"), Decimal("90"), "BUY"),
        Trade(Decimal("100"), Decimal("95"), "BUY"),
    ]
    assert calculate_profit_factor(trades) == 0.0


def test_profit_factor_calculates_correctly() -> None:
    """Profit factor calculates correctly for mixed results."""
    trades = [
        Trade(Decimal("100"), Decimal("120"), "BUY"),  # +20
        Trade(Decimal("100"), Decimal("90"), "BUY"),  # -10
        Trade(Decimal("100"), Decimal("110"), "BUY"),  # +10
    ]
    # Gross profit = 30, Gross loss = 10, PF = 3.0
    assert calculate_profit_factor(trades) == 3.0
