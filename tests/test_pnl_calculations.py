"""Tests for P&L calculation utilities."""

from __future__ import annotations

from decimal import Decimal

from core.portfolio.pnl import (
    calculate_unrealized_pnl,
    calculate_realized_pnl,
    calculate_position_value,
    calculate_return_percentage,
    calculate_total_pnl,
    calculate_equity,
    calculate_average_cost,
    calculate_sharpe_ratio,
    calculate_max_drawdown,
    calculate_win_rate,
    calculate_profit_factor,
)


def test_calculate_unrealized_pnl_long_profit():
    """Test unrealized P&L for a profitable long position."""
    pnl = calculate_unrealized_pnl(
        quantity=Decimal("10"),
        avg_entry_price=Decimal("100"),
        current_price=Decimal("110"),
    )
    assert pnl == Decimal("100")  # (110 - 100) * 10


def test_calculate_unrealized_pnl_long_loss():
    """Test unrealized P&L for a losing long position."""
    pnl = calculate_unrealized_pnl(
        quantity=Decimal("10"),
        avg_entry_price=Decimal("100"),
        current_price=Decimal("90"),
    )
    assert pnl == Decimal("-100")  # (90 - 100) * 10


def test_calculate_realized_pnl():
    """Test realized P&L calculation."""
    pnl = calculate_realized_pnl(
        sell_quantity=Decimal("5"),
        sell_price=Decimal("110"),
        buy_quantity=Decimal("5"),
        buy_price=Decimal("100"),
    )
    assert pnl == Decimal("50")  # (110 - 100) * 5


def test_calculate_position_value():
    """Test position value calculation."""
    value = calculate_position_value(
        quantity=Decimal("10"),
        current_price=Decimal("100"),
    )
    assert value == Decimal("1000")


def test_calculate_return_percentage():
    """Test return percentage calculation."""
    ret_pct = calculate_return_percentage(
        initial_value=Decimal("1000"),
        final_value=Decimal("1100"),
    )
    assert ret_pct == Decimal("10")  # 10% gain


def test_calculate_return_percentage_zero_initial():
    """Test return percentage with zero initial value."""
    ret_pct = calculate_return_percentage(
        initial_value=Decimal("0"),
        final_value=Decimal("1000"),
    )
    assert ret_pct == Decimal("0")


def test_calculate_total_pnl():
    """Test total P&L calculation."""
    total = calculate_total_pnl(
        unrealized_pnl=Decimal("100"),
        realized_pnl=Decimal("50"),
    )
    assert total == Decimal("150")


def test_calculate_equity():
    """Test equity calculation."""
    equity = calculate_equity(
        cash_balance=Decimal("1000"),
        position_value=Decimal("500"),
        unrealized_pnl=Decimal("50"),
    )
    assert equity == Decimal("1550")


def test_calculate_average_cost():
    """Test average cost calculation when adding to position."""
    avg_cost = calculate_average_cost(
        existing_qty=Decimal("5"),
        existing_avg_price=Decimal("100"),
        new_qty=Decimal("5"),
        new_price=Decimal("110"),
    )
    assert avg_cost == Decimal("105")  # (5*100 + 5*110) / 10


def test_calculate_average_cost_zero_quantity():
    """Test average cost with zero total quantity."""
    avg_cost = calculate_average_cost(
        existing_qty=Decimal("5"),
        existing_avg_price=Decimal("100"),
        new_qty=Decimal("-5"),
        new_price=Decimal("110"),
    )
    assert avg_cost == Decimal("0")


def test_calculate_sharpe_ratio():
    """Test Sharpe ratio calculation."""
    returns = [Decimal("0.01"), Decimal("0.02"), Decimal("-0.01"), Decimal("0.03")]
    sharpe = calculate_sharpe_ratio(returns)
    assert sharpe != Decimal("0")


def test_calculate_sharpe_ratio_empty():
    """Test Sharpe ratio with empty returns."""
    sharpe = calculate_sharpe_ratio([])
    assert sharpe == Decimal("0")


def test_calculate_max_drawdown():
    """Test max drawdown calculation."""
    equity_curve = [
        Decimal("1000"),
        Decimal("1100"),
        Decimal("900"),  # 18.18% drawdown
        Decimal("950"),
        Decimal("1200"),
    ]
    max_dd_pct, max_dd_amt = calculate_max_drawdown(equity_curve)
    
    # Max drawdown should be from 1100 to 900 = 200 USD or ~18.18%
    assert max_dd_amt == Decimal("200")
    assert abs(max_dd_pct - Decimal("18.181818181818181818181818182")) < Decimal("0.01")


def test_calculate_max_drawdown_empty():
    """Test max drawdown with empty equity curve."""
    max_dd_pct, max_dd_amt = calculate_max_drawdown([])
    assert max_dd_pct == Decimal("0")
    assert max_dd_amt == Decimal("0")


def test_calculate_win_rate():
    """Test win rate calculation."""
    win_rate = calculate_win_rate(
        winning_trades=7,
        total_trades=10,
    )
    assert win_rate == Decimal("70")


def test_calculate_win_rate_zero_trades():
    """Test win rate with zero trades."""
    win_rate = calculate_win_rate(
        winning_trades=0,
        total_trades=0,
    )
    assert win_rate == Decimal("0")


def test_calculate_profit_factor():
    """Test profit factor calculation."""
    pf = calculate_profit_factor(
        gross_profit=Decimal("1000"),
        gross_loss=Decimal("500"),
    )
    assert pf == Decimal("2")


def test_calculate_profit_factor_zero_loss():
    """Test profit factor with zero loss."""
    pf = calculate_profit_factor(
        gross_profit=Decimal("1000"),
        gross_loss=Decimal("0"),
    )
    assert pf == Decimal("999")  # Large number indicating all wins
