"""Cost-aware evaluation with regime segmentation.

Calculates performance metrics accounting for transaction costs
(fees, spread, slippage) and segments results by market regime
(bull/trending_up, bear/trending_down, ranging, high_vol).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

from core.backtest.engine import BacktestResult, Trade
from core.backtest.metrics import (
    calculate_max_drawdown,
    calculate_sharpe_ratio,
)
from core.strategy_eval.regime import RegimeDetector
from core.strategy_eval.types import MarketRegime, RegimePerformance


# ---------------------------------------------------------------------------
# Fee model
# ---------------------------------------------------------------------------


@dataclass
class FeeModel:
    """Transaction cost model for backtest cost adjustment."""

    maker_fee_rate: float = 0.001  # 0.1%
    taker_fee_rate: float = 0.002  # 0.2%
    spread_bps: float = 0.5  # 0.5 basis points
    slippage_bps: float = 0.5  # 0.5 basis points
    min_edge_bps: float = 3.5  # 35 bps minimum edge for taker

    def compute_trade_cost(self, entry_price: float, exit_price: float, size: float, is_maker: bool = False) -> float:
        """Compute total cost (fee + spread + slippage) for a single trade.

        Args:
            entry_price: Price at entry
            exit_price: Price at exit
            size: Trade size (quote currency amount)
            is_maker: True if maker order (lower fee)

        Returns:
            Total cost in quote currency
        """
        fee_rate = self.maker_fee_rate if is_maker else self.taker_fee_rate
        fee = size * fee_rate

        spread_cost = size * (self.spread_bps / 10000.0)
        slippage_cost = size * (self.slippage_bps / 10000.0)

        return fee + spread_cost + slippage_cost

    def compute_min_edge(self, price: float) -> float:
        """Minimum edge required in quote currency."""
        return price * (self.min_edge_bps / 10000.0)


# ---------------------------------------------------------------------------
# Cost-adjusted trade
# ---------------------------------------------------------------------------


@dataclass
class CostAdjustedTrade:
    """Trade with cost adjustment applied."""

    raw_pnl: float
    fee: float
    spread: float
    slippage: float
    total_cost: float
    cost_adjusted_pnl: float
    entry_price: float
    exit_price: float
    side: str
    size: float
    regime: MarketRegime = MarketRegime.TRANSITION


def adjust_trade(trade: Trade, fee_model: FeeModel) -> CostAdjustedTrade:
    """Apply cost adjustment to a single trade."""
    value = float(trade.entry_price) * float(trade.size)
    fee = value * fee_model.taker_fee_rate
    spread = value * (fee_model.spread_bps / 10000.0)
    slippage = value * (fee_model.slippage_bps / 10000.0)
    total_cost = fee + spread + slippage
    cost_adjusted_pnl = float(trade.pnl) - total_cost

    return CostAdjustedTrade(
        raw_pnl=float(trade.pnl),
        fee=fee,
        spread=spread,
        slippage=slippage,
        total_cost=total_cost,
        cost_adjusted_pnl=cost_adjusted_pnl,
        entry_price=float(trade.entry_price),
        exit_price=float(trade.exit_price),
        side=trade.side,
        size=float(trade.size),
    )


# ---------------------------------------------------------------------------
# Regime mapping helpers
# ---------------------------------------------------------------------------

_REGIME_LABELS = {
    MarketRegime.TRENDING_UP: "bull",
    MarketRegime.TRENDING_DOWN: "bear",
    MarketRegime.RANGING: "range",
    MarketRegime.HIGH_VOL: "high_vol",
    MarketRegime.LOW_VOL: "low_vol",
    MarketRegime.TRANSITION: "transition",
}


# ---------------------------------------------------------------------------
# Cost-aware regime evaluation
# ---------------------------------------------------------------------------


def evaluate_cost_aware_regimes(
    cost_trades: list[CostAdjustedTrade],
    regimes: list[MarketRegime],
    candles: Sequence,
    fee_model: FeeModel | None = None,
) -> list[RegimePerformance]:
    """Evaluate strategy performance per regime with cost adjustment.

    Args:
        cost_trades: Trades with cost data and regime labels
        regimes: Regime for each candle (used for candle counts)
        candles: Candle data for index lookup
        fee_model: Fee model for cost calculations

    Returns:
        List of RegimePerformance with cost-adjusted metrics
    """
    if fee_model is None:
        fee_model = FeeModel()

    # Group trades by regime
    regime_groups: dict[MarketRegime, list[CostAdjustedTrade]] = {}
    for regime in MarketRegime:
        regime_groups[regime] = []
    for ct in cost_trades:
        regime_groups[ct.regime].append(ct)

    results = []
    for regime, trades in regime_groups.items():
        n_trades = len(trades)
        n_candles = regimes.count(regime) if regime in _REGIME_LABELS else 0

        if n_trades == 0:
            results.append(
                RegimePerformance(
                    regime=regime,
                    n_candles=n_candles,
                    n_trades=0,
                    return_pct=0.0,
                    sharpe=0.0,
                    max_dd=0.0,
                    win_rate=0.0,
                    avg_trade_pnl=0.0,
                )
            )
            continue

        raw_pnls = [t.raw_pnl for t in trades]
        adj_pnls = [t.cost_adjusted_pnl for t in trades]
        total_raw = sum(raw_pnls)
        total_costs = sum(t.total_cost for t in trades)
        net_pnl = total_raw - total_costs

        # Average entry price for return calculation
        avg_entry = sum(t.entry_price for t in trades) / n_trades if trades else 1.0
        return_pct = net_pnl / avg_entry if avg_entry > 0 else 0.0

        # Win rate (cost-adjusted)
        win_rate = sum(1 for p in adj_pnls if p > 0) / n_trades

        # Average cost-adjusted PnL
        avg_adj_pnl = net_pnl / n_trades

        # Sharpe from adjusted returns
        if n_trades >= 2:
            mean_adj = sum(adj_pnls) / n_trades
            var_adj = sum((p - mean_adj) ** 2 for p in adj_pnls) / (n_trades - 1)
            std_adj = math.sqrt(var_adj) if var_adj > 0 else 0.0
            sharpe = (mean_adj / std_adj) * math.sqrt(365) if std_adj > 0 else 0.0
        else:
            sharpe = 0.0

        # Max drawdown from cumulative adjusted PnL
        cum_adj = [0.0]
        for p in adj_pnls:
            cum_adj.append(cum_adj[-1] + p)
        max_dd = calculate_max_drawdown(cum_adj)

        results.append(
            RegimePerformance(
                regime=regime,
                n_candles=n_candles,
                n_trades=n_trades,
                return_pct=return_pct,
                sharpe=sharpe,
                max_dd=max_dd,
                win_rate=win_rate,
                avg_trade_pnl=avg_adj_pnl,
            )
        )

    return results


# ---------------------------------------------------------------------------
# Full cost-aware evaluation
# ---------------------------------------------------------------------------


@dataclass
class CostAwareEvaluation:
    """Complete cost-aware evaluation with regime breakdown."""

    # Overall cost-adjusted metrics
    gross_pnl: float
    total_fees: float
    total_spread: float
    total_slippage: float
    total_costs: float
    net_pnl: float
    cost_ratio: float  # total_costs / gross_pnl (abs)

    # Original (unadjusted) metrics
    gross_sharpe: float
    gross_win_rate: float
    gross_profit_factor: float
    gross_max_dd: float
    gross_total_return: float

    # Cost-adjusted metrics
    net_sharpe: float
    net_win_rate: float
    net_profit_factor: float
    net_max_dd: float
    net_total_return: float

    # Regime breakdown
    regime_performance: list[RegimePerformance]

    # Raw cost-adjusted trades
    cost_trades: list[CostAdjustedTrade]


def evaluate_cost_aware(
    result: BacktestResult,
    candles: Sequence,
    fee_model: FeeModel | None = None,
    regime_detector: RegimeDetector | None = None,
) -> CostAwareEvaluation:
    """Run full cost-aware evaluation with regime segmentation.

    Args:
        result: BacktestResult from a standard backtest run
        candles: Candle data for regime detection
        fee_model: Fee model configuration
        regime_detector: Regime detector for segmentation

    Returns:
        CostAwareEvaluation with cost-adjusted and regime data
    """
    if fee_model is None:
        fee_model = FeeModel()
    if regime_detector is None:
        regime_detector = RegimeDetector()

    # Detect regimes for all candles
    regimes = regime_detector.detect_regimes(candles)

    # Adjust all trades for costs
    cost_trades: list[CostAdjustedTrade] = []
    for i, trade in enumerate(result.trades):
        ct = adjust_trade(trade, fee_model)
        # Assign regime based on trade index (approximate)
        trade_regime_idx = min(i, len(regimes) - 1)
        ct.regime = regimes[trade_regime_idx]
        cost_trades.append(ct)

    # Overall cost stats
    gross_pnl = result.total_pnl
    total_fees = sum(ct.fee for ct in cost_trades)
    total_spread = sum(ct.spread for ct in cost_trades)
    total_slippage = sum(ct.slippage for ct in cost_trades)
    total_costs = total_fees + total_spread + total_slippage
    net_pnl = gross_pnl - total_costs
    cost_ratio = total_costs / abs(gross_pnl) if gross_pnl != 0 else 0.0

    # Net return
    epsilon = 1e-9
    if abs(result.total_return) < epsilon:
        net_total_return = net_pnl / result.total_pnl if result.total_pnl else 0.0
    else:
        net_total_return = net_pnl / (result.total_pnl / result.total_return)

    # Net Sharpe from cost-adjusted returns
    adj_returns = [ct.cost_adjusted_pnl for ct in cost_trades]
    net_sharpe = calculate_sharpe_ratio(adj_returns) if adj_returns else 0.0

    # Net win rate from cost-adjusted PnL
    if cost_trades:
        net_win_rate = sum(1 for ct in cost_trades if ct.cost_adjusted_pnl > 0) / len(cost_trades)
    else:
        net_win_rate = 0.0

    # Net profit factor (cost-adjusted)
    gross_profit = sum(ct.cost_adjusted_pnl for ct in cost_trades if ct.cost_adjusted_pnl > 0)
    gross_loss = abs(sum(ct.cost_adjusted_pnl for ct in cost_trades if ct.cost_adjusted_pnl < 0))
    net_profit_factor = gross_profit / gross_loss if gross_loss > 0 else (float("inf") if gross_profit > 0 else 0.0)

    # Net max drawdown from cumulative adjusted PnL
    cum_adj = [0.0]
    for ct in cost_trades:
        cum_adj.append(cum_adj[-1] + ct.cost_adjusted_pnl)
    net_max_dd = calculate_max_drawdown(cum_adj)

    # Regime performance
    regime_perf = evaluate_cost_aware_regimes(cost_trades, regimes, candles, fee_model)

    return CostAwareEvaluation(
        gross_pnl=gross_pnl,
        total_fees=total_fees,
        total_spread=total_spread,
        total_slippage=total_slippage,
        total_costs=total_costs,
        net_pnl=net_pnl,
        cost_ratio=cost_ratio,
        gross_sharpe=result.sharpe_ratio,
        gross_win_rate=result.win_rate,
        gross_profit_factor=result.profit_factor,
        gross_max_dd=result.max_drawdown,
        gross_total_return=result.total_return,
        net_sharpe=net_sharpe,
        net_win_rate=net_win_rate,
        net_profit_factor=net_profit_factor,
        net_max_dd=net_max_dd,
        net_total_return=net_total_return,
        regime_performance=regime_perf,
        cost_trades=cost_trades,
    )


def to_dict(evaluation: CostAwareEvaluation) -> dict:
    """Serialize CostAwareEvaluation to a dict for JSON export."""
    return {
        "net_pnl": round(evaluation.net_pnl, 2),
        "gross_pnl": round(evaluation.gross_pnl, 2),
        "total_fees": round(evaluation.total_fees, 2),
        "total_spread": round(evaluation.total_spread, 2),
        "total_slippage": round(evaluation.total_slippage, 2),
        "total_costs": round(evaluation.total_costs, 2),
        "cost_ratio": round(evaluation.cost_ratio, 4),
        "net_sharpe": round(evaluation.net_sharpe, 4),
        "net_win_rate": round(evaluation.net_win_rate, 4),
        "net_profit_factor": round(evaluation.net_profit_factor, 4),
        "net_max_drawdown": round(evaluation.net_max_dd, 4),
        "net_total_return": round(evaluation.net_total_return, 4),
        "regime_breakdown": [
            {
                "regime": _REGIME_LABELS.get(r.regime, str(r.regime)),
                "n_candles": r.n_candles,
                "n_trades": r.n_trades,
                "return_pct": round(r.return_pct, 4),
                "sharpe": round(r.sharpe, 4),
                "max_drawdown": round(r.max_dd, 4),
                "win_rate": round(r.win_rate, 4),
                "avg_trade_pnl": round(r.avg_trade_pnl, 2),
            }
            for r in evaluation.regime_performance
        ],
        "cost_adjusted_trades": [
            {
                "entry_price": round(ct.entry_price, 2),
                "exit_price": round(ct.exit_price, 2),
                "side": ct.side,
                "raw_pnl": round(ct.raw_pnl, 2),
                "fee": round(ct.fee, 2),
                "spread": round(ct.spread, 2),
                "slippage": round(ct.slippage, 2),
                "cost_adjusted_pnl": round(ct.cost_adjusted_pnl, 2),
                "regime": _REGIME_LABELS.get(ct.regime, str(ct.regime)),
            }
            for ct in evaluation.cost_trades
        ],
    }
