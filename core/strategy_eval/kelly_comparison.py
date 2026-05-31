"""Kelly sizing comparison for backtest evaluation.

Calculates and compares strategy performance using half-Kelly (0.5) and
full-Kelly (1.0) position sizing. Outputs both sizing variants side-by-side
in the evaluation output.

Usage:
    from core.strategy_eval.kelly_comparison import (
        compare_kelly_sizing,
        run_kelly_backtest,
    )
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from core.backtest.engine import BacktestResult, Trade
from core.backtest.metrics import (
    calculate_max_drawdown,
    calculate_profit_factor,
    calculate_sharpe_ratio,
    calculate_win_rate,
)
from core.risk.sizing import PositionSize, calculate_position_size


@dataclass
class KellySizingConfig:
    """Configuration for Kelly sizing comparison."""

    half_kelly_fraction: Decimal = Decimal("0.5")
    full_kelly_fraction: Decimal = Decimal("1.0")
    win_rate: Decimal | None = None
    avg_win: Decimal | None = None
    avg_loss: Decimal | None = None
    portfolio_value: Decimal = Decimal("10000")


@dataclass
class KellyBacktestResult:
    """Backtest result with Kelly sizing applied."""

    kelly_fraction: Decimal
    total_pnl: float
    total_return: float
    sharpe_ratio: float
    max_drawdown: float
    win_rate: float
    profit_factor: float
    final_equity: float
    position_size: Decimal
    adjusted_trades: list[Trade]


@dataclass
class KellySizingComparison:
    """Side-by-side comparison of half-Kelly vs full-Kelly sizing."""

    half_kelly: KellyBacktestResult
    full_kelly: KellyBacktestResult
    comparison: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Serialize to dict for JSON export."""
        return {
            "half_kelly": {
                "kelly_fraction": float(self.half_kelly.kelly_fraction),
                "total_pnl": round(self.half_kelly.total_pnl, 2),
                "total_return": round(self.half_kelly.total_return, 4),
                "sharpe_ratio": round(self.half_kelly.sharpe_ratio, 4),
                "max_drawdown": round(self.half_kelly.max_drawdown, 4),
                "win_rate": round(self.half_kelly.win_rate, 4),
                "profit_factor": round(self.half_kelly.profit_factor, 4),
                "final_equity": round(self.half_kelly.final_equity, 2),
                "position_size": float(self.half_kelly.position_size),
            },
            "full_kelly": {
                "kelly_fraction": float(self.full_kelly.kelly_fraction),
                "total_pnl": round(self.full_kelly.total_pnl, 2),
                "total_return": round(self.full_kelly.total_return, 4),
                "sharpe_ratio": round(self.full_kelly.sharpe_ratio, 4),
                "max_drawdown": round(self.full_kelly.max_drawdown, 4),
                "win_rate": round(self.full_kelly.win_rate, 4),
                "profit_factor": round(self.full_kelly.profit_factor, 4),
                "final_equity": round(self.full_kelly.final_equity, 2),
                "position_size": float(self.full_kelly.position_size),
            },
            "comparison": self.comparison,
        }


def _to_decimal(val: Decimal | float) -> Decimal:
    """Convert a value to Decimal."""
    if isinstance(val, Decimal):
        return val
    return Decimal(str(val))


def calculate_kelly_metrics(
    trades: list[Trade],
    equity_curve: list[float],
    kelly_fraction: Decimal,
    win_rate: Decimal,
    avg_win: Decimal,
    avg_loss: Decimal,
    portfolio_value: Decimal,
    entry_price: Decimal,
    stop_loss_price: Decimal,
) -> KellyBacktestResult:
    """Calculate backtest metrics with a specific Kelly fraction applied."""
    # Calculate position size using Kelly formula
    config = PositionSize(
        method="kelly",
        kelly_fraction=kelly_fraction,
        win_rate=win_rate,
        avg_win=avg_win,
        avg_loss=avg_loss,
    )
    position_size = calculate_position_size(config, portfolio_value, entry_price, stop_loss_price)

    # Calculate returns from equity curve
    returns = []
    for i in range(1, len(equity_curve)):
        if equity_curve[i - 1] > 0:
            returns.append((equity_curve[i] - equity_curve[i - 1]) / equity_curve[i - 1])

    # Calculate metrics
    sharpe = calculate_sharpe_ratio(returns)
    max_dd = calculate_max_drawdown(equity_curve)
    win_rate_val = calculate_win_rate(trades)
    profit_factor = calculate_profit_factor(trades)
    final_equity = equity_curve[-1] if equity_curve else float(portfolio_value)
    total_pnl = final_equity - float(portfolio_value)
    total_return = total_pnl / float(portfolio_value) if float(portfolio_value) > 0 else 0.0

    return KellyBacktestResult(
        kelly_fraction=kelly_fraction,
        total_pnl=total_pnl,
        total_return=total_return,
        sharpe_ratio=sharpe,
        max_drawdown=max_dd,
        win_rate=win_rate_val,
        profit_factor=profit_factor,
        final_equity=final_equity,
        position_size=position_size,
        adjusted_trades=trades,
    )


def compare_kelly_sizing(
    trades: list[Trade],
    equity_curve: list[float],
    config: KellySizingConfig | None = None,
) -> KellySizingComparison:
    """Compare half-Kelly (0.5) vs full-Kelly (1.0) position sizing."""
    if config is None:
        config = KellySizingConfig()

    # Use win_rate and avg_win/avg_loss from config or derive from trades
    wr = config.win_rate if config.win_rate is not None else calculate_win_rate(trades)
    avg_win = _to_decimal(config.avg_win) if config.avg_win is not None else None
    avg_loss = _to_decimal(config.avg_loss) if config.avg_loss is not None else None

    if avg_win is None or avg_loss is None:
        wins = [float(t.pnl) for t in trades if t.pnl > 0]
        losses = [abs(float(t.pnl)) for t in trades if t.pnl < 0]
        avg_win = Decimal(str(sum(wins) / len(wins))) if wins else Decimal("1.0")
        avg_loss = Decimal(str(sum(losses) / len(losses))) if losses else Decimal("1.0")

    entry_price = float(trades[0].entry_price) if trades else 100.0
    stop_loss_price = entry_price * 0.95  # 5% stop loss

    # Calculate with half-Kelly
    half_result = calculate_kelly_metrics(
        trades=trades,
        equity_curve=equity_curve,
        kelly_fraction=Decimal("0.5"),
        win_rate=_to_decimal(wr),
        avg_win=avg_win,
        avg_loss=avg_loss,
        portfolio_value=config.portfolio_value,
        entry_price=Decimal(str(entry_price)),
        stop_loss_price=Decimal(str(stop_loss_price)),
    )

    # Calculate with full-Kelly
    full_result = calculate_kelly_metrics(
        trades=trades,
        equity_curve=equity_curve,
        kelly_fraction=Decimal("1.0"),
        win_rate=_to_decimal(wr),
        avg_win=avg_win,
        avg_loss=avg_loss,
        portfolio_value=config.portfolio_value,
        entry_price=Decimal(str(entry_price)),
        stop_loss_price=Decimal(str(stop_loss_price)),
    )

    # Build comparison
    pnl_diff = full_result.total_pnl - half_result.total_pnl
    pnl_pct = (pnl_diff / half_result.total_pnl * 100) if half_result.total_pnl != 0 else 0.0
    sharpe_diff = full_result.sharpe_ratio - half_result.sharpe_ratio
    dd_diff = full_result.max_drawdown - half_result.max_drawdown
    size_ratio = float(full_result.position_size / half_result.position_size) if half_result.position_size > 0 else 0.0

    comparison = {
        "pnl_diff": round(pnl_diff, 2),
        "pnl_diff_pct": round(pnl_pct, 2),
        "sharpe_diff": round(sharpe_diff, 4),
        "max_dd_diff": round(dd_diff, 4),
        "position_size_ratio": round(size_ratio, 4),
        "half_kelly_position_size": float(half_result.position_size),
        "full_kelly_position_size": float(full_result.position_size),
    }

    return KellySizingComparison(
        half_kelly=half_result,
        full_kelly=full_result,
        comparison=comparison,
    )


def run_kelly_backtest(
    result: BacktestResult,
    config: KellySizingConfig | None = None,
) -> KellySizingComparison:
    """Run Kelly sizing comparison on a BacktestResult.

    Convenience wrapper that extracts trades and equity_curve from
    a BacktestResult and runs the comparison.
    """
    return compare_kelly_sizing(
        trades=result.trades,
        equity_curve=result.equity_curve,
        config=config,
    )


def to_dict(comparison: KellySizingComparison) -> dict:
    """Serialize KellySizingComparison to dict for JSON export."""
    return comparison.to_dict()
