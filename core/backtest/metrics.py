"""Performance metrics calculations for backtesting."""

from __future__ import annotations

import math
from decimal import Decimal
from typing import Sequence


class Trade:
    """Represents a completed trade."""

    def __init__(
        self,
        entry_price: Decimal,
        exit_price: Decimal,
        side: str,
        size: Decimal = Decimal("1.0"),
    ):
        self.entry_price = entry_price
        self.exit_price = exit_price
        self.side = side  # "BUY" or "SELL"
        self.size = size
        self.pnl = self._calculate_pnl()

    def _calculate_pnl(self) -> Decimal:
        """Calculate profit/loss for this trade."""
        if self.side == "BUY":
            return (self.exit_price - self.entry_price) * self.size
        else:  # SELL
            return (self.entry_price - self.exit_price) * self.size


def calculate_sharpe_ratio(returns: Sequence[float], risk_free_rate: float = 0.0, trading_days: int = 365) -> float:
    """Calculate Sharpe ratio from returns.
    
    Sharpe Ratio = (Mean Return - Risk Free Rate) / Std Dev of Returns
    
    Args:
        returns: Sequence of returns (e.g., daily returns)
        risk_free_rate: Annual risk-free rate (default 0.0)
        trading_days: Number of trading days per year for annualization (default 365 for crypto)
        
    Returns:
        Sharpe ratio (annualized assuming daily returns)
    """
    if not returns or len(returns) < 2:
        return 0.0

    mean_return = sum(returns) / len(returns)
    variance = sum((r - mean_return) ** 2 for r in returns) / (len(returns) - 1)
    std_dev = math.sqrt(variance) if variance > 0 else 0.0

    if std_dev == 0:
        return 0.0

    # Annualize (default 365 for crypto 24/7 trading)
    sharpe = ((mean_return - risk_free_rate) / std_dev) * math.sqrt(trading_days)
    return sharpe


def calculate_max_drawdown(equity_curve: Sequence[float]) -> float:
    """Calculate maximum drawdown from equity curve.
    
    Max Drawdown = max((peak - trough) / peak)
    
    Args:
        equity_curve: Sequence of equity values over time
        
    Returns:
        Maximum drawdown as a percentage (0.0 to 1.0)
    """
    if not equity_curve or len(equity_curve) < 2:
        return 0.0

    max_dd = 0.0
    peak = equity_curve[0]

    for value in equity_curve:
        if value > peak:
            peak = value
        dd = (peak - value) / peak if peak > 0 else 0.0
        if dd > max_dd:
            max_dd = dd

    return max_dd


def calculate_win_rate(trades: Sequence[Trade]) -> float:
    """Calculate win rate from trades.
    
    Win Rate = Number of Winning Trades / Total Trades
    
    Args:
        trades: Sequence of completed trades
        
    Returns:
        Win rate as percentage (0.0 to 1.0)
    """
    if not trades:
        return 0.0

    winning_trades = sum(1 for t in trades if t.pnl > 0)
    return winning_trades / len(trades)


def calculate_profit_factor(trades: Sequence[Trade]) -> float:
    """Calculate profit factor from trades.
    
    Profit Factor = Total Gross Profit / Total Gross Loss
    
    Args:
        trades: Sequence of completed trades
        
    Returns:
        Profit factor (> 1.0 is profitable)
    """
    if not trades:
        return 0.0

    gross_profit = sum(float(t.pnl) for t in trades if t.pnl > 0)
    gross_loss = abs(sum(float(t.pnl) for t in trades if t.pnl < 0))

    if gross_loss == 0:
        return float("inf") if gross_profit > 0 else 0.0

    return gross_profit / gross_loss
