"""P&L calculation utilities for portfolio tracking.

Provides functions for:
- Unrealized P&L calculation
- Realized P&L calculation
- Cost basis calculations (FIFO, LIFO, average)
- Performance metrics (return %, Sharpe ratio, max drawdown)
"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

CostBasisMethod = Literal["FIFO", "LIFO", "average"]


def calculate_unrealized_pnl(
    quantity: Decimal,
    avg_entry_price: Decimal,
    current_price: Decimal,
) -> Decimal:
    """Calculate unrealized P&L for an open position.
    
    Formula: (current_price - entry_price) * quantity
    
    Args:
        quantity: Position quantity (positive for long, negative for short)
        avg_entry_price: Average entry price
        current_price: Current market price
        
    Returns:
        Unrealized P&L (positive = profit, negative = loss)
    """
    return (current_price - avg_entry_price) * quantity


def calculate_realized_pnl(
    sell_quantity: Decimal,
    sell_price: Decimal,
    buy_quantity: Decimal,
    buy_price: Decimal,
) -> Decimal:
    """Calculate realized P&L for a closed position.
    
    Formula: (sell_price - buy_price) * quantity
    
    Args:
        sell_quantity: Quantity sold
        sell_price: Average sell price
        buy_quantity: Quantity bought
        buy_price: Average buy price
        
    Returns:
        Realized P&L (positive = profit, negative = loss)
    """
    # Use the smaller quantity for the calculation
    closed_qty = min(abs(sell_quantity), abs(buy_quantity))
    return (sell_price - buy_price) * closed_qty


def calculate_position_value(
    quantity: Decimal,
    current_price: Decimal,
) -> Decimal:
    """Calculate current value of a position.
    
    Args:
        quantity: Position quantity
        current_price: Current market price
        
    Returns:
        Position value in quote currency
    """
    return abs(quantity) * current_price


def calculate_return_percentage(
    initial_value: Decimal,
    final_value: Decimal,
) -> Decimal:
    """Calculate percentage return.
    
    Formula: ((final - initial) / initial) * 100
    
    Args:
        initial_value: Starting value
        final_value: Ending value
        
    Returns:
        Return percentage
    """
    if initial_value == 0:
        return Decimal("0")
    
    return ((final_value - initial_value) / initial_value) * Decimal("100")


def calculate_total_pnl(
    unrealized_pnl: Decimal,
    realized_pnl: Decimal,
) -> Decimal:
    """Calculate total P&L (unrealized + realized).
    
    Args:
        unrealized_pnl: Unrealized P&L
        realized_pnl: Realized P&L
        
    Returns:
        Total P&L
    """
    return unrealized_pnl + realized_pnl


def calculate_equity(
    cash_balance: Decimal,
    position_value: Decimal,
    unrealized_pnl: Decimal,
) -> Decimal:
    """Calculate total portfolio equity.
    
    Formula: cash + position_value + unrealized_pnl
    
    Args:
        cash_balance: Available cash
        position_value: Total position value
        unrealized_pnl: Unrealized P&L
        
    Returns:
        Total equity
    """
    return cash_balance + position_value + unrealized_pnl


def calculate_average_cost(
    existing_qty: Decimal,
    existing_avg_price: Decimal,
    new_qty: Decimal,
    new_price: Decimal,
) -> Decimal:
    """Calculate average cost basis when adding to a position.
    
    Args:
        existing_qty: Existing position quantity
        existing_avg_price: Existing average price
        new_qty: New quantity being added
        new_price: New entry price
        
    Returns:
        New average price
    """
    total_qty = existing_qty + new_qty
    if total_qty == 0:
        return Decimal("0")
    
    total_cost = (existing_qty * existing_avg_price) + (new_qty * new_price)
    return total_cost / total_qty


def calculate_sharpe_ratio(
    returns: list[Decimal],
    risk_free_rate: Decimal = Decimal("0"),
) -> Decimal:
    """Calculate Sharpe ratio from a series of returns.
    
    Formula: (mean_return - risk_free_rate) / std_dev_return
    
    Args:
        returns: List of period returns
        risk_free_rate: Risk-free rate (default: 0)
        
    Returns:
        Sharpe ratio (higher is better)
    """
    if not returns or len(returns) < 2:
        return Decimal("0")
    
    # Calculate mean return
    mean_return = sum(returns) / len(returns)
    
    # Calculate standard deviation
    variance = sum((r - mean_return) ** 2 for r in returns) / (len(returns) - 1)
    std_dev = variance ** Decimal("0.5")
    
    if std_dev == 0:
        return Decimal("0")
    
    return (mean_return - risk_free_rate) / std_dev


def calculate_max_drawdown(equity_curve: list[Decimal]) -> tuple[Decimal, Decimal]:
    """Calculate maximum drawdown from equity curve.
    
    Args:
        equity_curve: List of equity values over time
        
    Returns:
        Tuple of (max_drawdown_percentage, max_drawdown_amount)
    """
    if not equity_curve or len(equity_curve) < 2:
        return Decimal("0"), Decimal("0")
    
    max_equity = equity_curve[0]
    max_drawdown_pct = Decimal("0")
    max_drawdown_amt = Decimal("0")
    
    for equity in equity_curve:
        if equity > max_equity:
            max_equity = equity
        
        drawdown_amt = max_equity - equity
        if max_equity > 0:
            drawdown_pct = (drawdown_amt / max_equity) * Decimal("100")
            
            if drawdown_pct > max_drawdown_pct:
                max_drawdown_pct = drawdown_pct
                max_drawdown_amt = drawdown_amt
    
    return max_drawdown_pct, max_drawdown_amt


def calculate_win_rate(
    winning_trades: int,
    total_trades: int,
) -> Decimal:
    """Calculate win rate percentage.
    
    Args:
        winning_trades: Number of profitable trades
        total_trades: Total number of trades
        
    Returns:
        Win rate percentage (0-100)
    """
    if total_trades == 0:
        return Decimal("0")
    
    return (Decimal(winning_trades) / Decimal(total_trades)) * Decimal("100")


def calculate_profit_factor(
    gross_profit: Decimal,
    gross_loss: Decimal,
) -> Decimal:
    """Calculate profit factor.
    
    Formula: gross_profit / abs(gross_loss)
    
    Args:
        gross_profit: Total profit from winning trades
        gross_loss: Total loss from losing trades
        
    Returns:
        Profit factor (>1 is profitable, <1 is losing)
    """
    if gross_loss == 0:
        return Decimal("999") if gross_profit > 0 else Decimal("0")
    
    return gross_profit / abs(gross_loss)
