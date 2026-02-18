"""Backtest report generation.

This module provides functionality to generate detailed reports from backtest results.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any


@dataclass
class BacktestReport:
    """Comprehensive backtest report with all metrics and trade details."""

    # Metadata
    strategy_name: str
    exchange: str
    symbol: str
    timeframe: str
    start_date: str
    end_date: str
    initial_capital: float

    # Summary metrics
    total_pnl: float
    total_return: float
    sharpe_ratio: float
    max_drawdown: float
    win_rate: float
    profit_factor: float

    # Trade statistics
    num_trades: int
    num_winning_trades: int
    num_losing_trades: int
    avg_win: float
    avg_loss: float
    largest_win: float
    largest_loss: float

    # Equity curve
    final_equity: float
    peak_equity: float
    equity_curve: list[float]

    # Trade log
    trades: list[dict[str, Any]]


def generate_report(
    strategy_name: str,
    exchange: str,
    symbol: str,
    timeframe: str,
    start_date: datetime,
    end_date: datetime,
    initial_capital: float,
    result: Any,  # BacktestResult
) -> BacktestReport:
    """Generate a comprehensive backtest report.

    Args:
        strategy_name: Name of the strategy
        exchange: Exchange name
        symbol: Trading symbol
        timeframe: Candle timeframe
        start_date: Backtest start date
        end_date: Backtest end date
        initial_capital: Initial capital
        result: BacktestResult from engine

    Returns:
        BacktestReport with all metrics and trade details
    """
    # Calculate trade statistics
    winning_trades = [t for t in result.trades if t.pnl > 0]
    losing_trades = [t for t in result.trades if t.pnl < 0]

    num_winning = len(winning_trades)
    num_losing = len(losing_trades)

    avg_win = sum(float(t.pnl) for t in winning_trades) / num_winning if num_winning > 0 else 0.0
    avg_loss = sum(float(t.pnl) for t in losing_trades) / num_losing if num_losing > 0 else 0.0

    largest_win = max((float(t.pnl) for t in winning_trades), default=0.0)
    largest_loss = min((float(t.pnl) for t in losing_trades), default=0.0)

    # Equity curve statistics
    final_equity = result.equity_curve[-1] if result.equity_curve else initial_capital
    peak_equity = max(result.equity_curve) if result.equity_curve else initial_capital

    # Convert trades to dict format
    trades_list = [
        {
            "entry_price": float(t.entry_price),
            "exit_price": float(t.exit_price),
            "side": t.side,
            "size": float(t.size),
            "pnl": float(t.pnl),
        }
        for t in result.trades
    ]

    return BacktestReport(
        strategy_name=strategy_name,
        exchange=exchange,
        symbol=symbol,
        timeframe=timeframe,
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
        initial_capital=initial_capital,
        total_pnl=result.total_pnl,
        total_return=result.total_return,
        sharpe_ratio=result.sharpe_ratio,
        max_drawdown=result.max_drawdown,
        win_rate=result.win_rate,
        profit_factor=result.profit_factor,
        num_trades=len(result.trades),
        num_winning_trades=num_winning,
        num_losing_trades=num_losing,
        avg_win=avg_win,
        avg_loss=avg_loss,
        largest_win=largest_win,
        largest_loss=largest_loss,
        final_equity=final_equity,
        peak_equity=peak_equity,
        equity_curve=result.equity_curve,
        trades=trades_list,
    )


def report_to_dict(report: BacktestReport) -> dict[str, Any]:
    """Convert a BacktestReport to a dictionary.

    Args:
        report: BacktestReport instance

    Returns:
        Dictionary representation of the report
    """
    return asdict(report)


def print_report_summary(report: BacktestReport) -> None:
    """Print a formatted summary of the backtest report.

    Args:
        report: BacktestReport instance
    """
    print("\n" + "=" * 60)
    print(f"BACKTEST REPORT: {report.strategy_name}")
    print("=" * 60)
    print(f"\nMarket: {report.exchange} {report.symbol} ({report.timeframe})")
    print(f"Period: {report.start_date} to {report.end_date}")
    print(f"Initial Capital: ${report.initial_capital:,.2f}")

    print("\n" + "-" * 60)
    print("PERFORMANCE METRICS")
    print("-" * 60)
    print(f"Total P&L:        ${report.total_pnl:,.2f}")
    print(f"Total Return:     {report.total_return * 100:.2f}%")
    print(f"Sharpe Ratio:     {report.sharpe_ratio:.2f}")
    print(f"Max Drawdown:     {report.max_drawdown * 100:.2f}%")
    print(f"Win Rate:         {report.win_rate * 100:.2f}%")
    print(f"Profit Factor:    {report.profit_factor:.2f}")

    print("\n" + "-" * 60)
    print("TRADE STATISTICS")
    print("-" * 60)
    print(f"Total Trades:     {report.num_trades}")
    print(f"Winning Trades:   {report.num_winning_trades}")
    print(f"Losing Trades:    {report.num_losing_trades}")
    print(f"Avg Win:          ${report.avg_win:.2f}")
    print(f"Avg Loss:         ${report.avg_loss:.2f}")
    print(f"Largest Win:      ${report.largest_win:.2f}")
    print(f"Largest Loss:     ${report.largest_loss:.2f}")

    print("\n" + "-" * 60)
    print("EQUITY")
    print("-" * 60)
    print(f"Final Equity:     ${report.final_equity:,.2f}")
    print(f"Peak Equity:      ${report.peak_equity:,.2f}")

    print("\n" + "=" * 60)
