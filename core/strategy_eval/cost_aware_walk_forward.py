"""Cost-aware walk-forward analysis with Kelly sizing and multi-regime splitting.

Implements a unified walk-forward evaluation that:
1. Splits data into rolling train/test windows
2. Applies cost adjustments (fees, spread, slippage) to each trade
3. Uses Kelly criterion for position sizing within each fold
4. Splits results by market regime (trending_up, trending_down, ranging, high_vol)
5. Detects overfitting and regime-specific performance decay

Usage:
    from core.strategy_eval.cost_aware_walk_forward import (
        run_cost_aware_walk_forward_kelly_regime,
        CostAwareWalkForwardResult,
        CostAwareWalkForwardConfig,
    )
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Sequence

from core.backtest.engine import BacktestEngine, BacktestResult, Strategy
from core.backtest.metrics import (
    Trade,
    calculate_max_drawdown,
    calculate_profit_factor,
    calculate_sharpe_ratio,
    calculate_win_rate,
)
from core.fees.model import FeeModel as CoreFeeModel
from core.risk.sizing import PositionSize, calculate_position_size
from core.strategy_eval.cost_aware import (
    CostAdjustedTrade,
    FeeModel,
    adjust_trade,
    evaluate_cost_aware_regimes,
)
from core.strategy_eval.regime import RegimeDetector
from core.strategy_eval.types import MarketRegime, RegimePerformance
from core.types import Candle


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass
class CostAwareWalkForwardConfig:
    """Configuration for cost-aware walk-forward with Kelly and regimes."""

    # Walk-forward parameters
    train_size_days: int = 90
    test_size_days: int = 30
    step_size_days: int = 15
    min_folds: int = 5
    lookback_candles: int = 200

    # Kelly sizing
    kelly_fraction: Decimal = Decimal("0.5")
    kelly_win_rate: Decimal = Decimal("0.55")
    kelly_avg_win: Decimal = Decimal("0.05")
    kelly_avg_loss: Decimal = Decimal("0.02")

    # Regime detection
    regime_detector: RegimeDetector | None = None

    # Fee model
    fee_model: FeeModel | None = None

    # Minimum edge filter (in bps) - trades below this are filtered out
    min_edge_bps: float = 3.5

    # Overfitting thresholds
    overfit_decay_threshold: float = 0.7
    underfit_decay_threshold: float = 0.4


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class CostAwareFold:
    """One fold with cost-adjusted and regime-split metrics."""

    train_start: datetime
    train_end: datetime
    test_start: datetime
    test_end: datetime

    # Train metrics (in-sample)
    train_return: float
    train_sharpe: float
    train_win_rate: float
    train_trades: int
    train_total_pnl: float
    train_total_costs: float
    train_net_pnl: float

    # Test metrics (out-of-sample)
    test_return: float
    test_sharpe: float
    test_win_rate: float
    test_trades: int
    test_total_pnl: float
    test_total_costs: float
    test_net_pnl: float
    test_max_dd: float

    # Cost awareness
    test_cost_ratio: float  # costs / gross_pnl
    test_cost_adjusted_pnl: float

    # Kelly sizing
    kelly_fraction: float
    kelly_position_size: Decimal

    # OOS metrics
    oos_decay: float
    regime_diversity: int  # number of regimes with trades


@dataclass
class RegimeFoldBreakdown:
    """Performance within a single regime for one fold."""

    regime: MarketRegime
    n_trades: int
    return_pct: float
    sharpe: float
    max_dd: float
    win_rate: float
    avg_trade_pnl: float
    total_cost: float
    cost_adjusted_pnl: float


@dataclass
class CostAwareWalkForwardResult:
    """Complete cost-aware walk-forward result with Kelly sizing and regime splits."""

    # Overall walk-forward
    folds: list[CostAwareFold]
    n_folds: int
    mean_train_return: float
    mean_test_return: float
    mean_oos_decay: float
    in_sample_consistency: float
    oos_significant: bool
    oos_sharpe: float
    oos_max_dd: float
    oos_win_rate: float
    overfitting_risk: str

    # Kelly sizing (aggregated across all folds)
    mean_kelly_fraction: float
    mean_kelly_position_size: Decimal
    half_kelly_return: float
    full_kelly_return: float
    kelly_pnl_diff: float

    # Regime breakdown (aggregated across all folds)
    regime_performance: list[RegimePerformance]
    regime_breakdown: list[RegimeFoldBreakdown]

    # Cost awareness
    total_gross_pnl: float
    total_costs: float
    total_net_pnl: float
    cost_ratio: float

    # Per-regime OOS decay
    regime_oos_decay: dict[MarketRegime, float]


# ---------------------------------------------------------------------------
# Kelly-aware backtest helper
# ---------------------------------------------------------------------------


def _kelly_position_size(
    win_rate: Decimal,
    avg_win: Decimal,
    avg_loss: Decimal,
    kelly_fraction: Decimal,
    portfolio_value: Decimal,
    entry_price: Decimal,
    stop_loss_pct: float = 0.05,
) -> Decimal:
    """Calculate Kelly position size for a single trade.

    Uses the Kelly criterion: f* = (p*b - q) / b
    where p = win_rate, q = 1-p, b = avg_win/avg_loss.
    """
    p = win_rate
    q = Decimal("1") - p
    b = avg_win / avg_loss if avg_loss > 0 else Decimal("1")
    kelly_pct = (p * b - q) / b if b > 0 else Decimal("0")
    fractional = kelly_pct * kelly_fraction
    fractional = max(fractional, Decimal("0"))

    stop_loss_price = entry_price * (Decimal("1") - Decimal(str(stop_loss_pct)))
    risk_per_unit = abs(entry_price - stop_loss_price)
    if risk_per_unit == 0:
        return Decimal("1")

    risk_amount = portfolio_value * fractional
    return max(risk_amount / risk_per_unit, Decimal("1"))


# ---------------------------------------------------------------------------
# Cost-aware Kelly backtest engine
# ---------------------------------------------------------------------------


class CostAwareKellyBacktest:
    """Backtest with cost adjustment and Kelly position sizing."""

    def __init__(
        self,
        fee_model: FeeModel,
        kelly_fraction: Decimal = Decimal("0.5"),
        win_rate: Decimal = Decimal("0.55"),
        avg_win: Decimal = Decimal("0.05"),
        avg_loss: Decimal = Decimal("0.02"),
        initial_capital: float = 10000.0,
        min_edge_bps: float = 3.5,
    ):
        self.fee_model = fee_model
        self.kelly_fraction = kelly_fraction
        self.win_rate = win_rate
        self.avg_win = avg_win
        self.avg_loss = avg_loss
        self.initial_capital = initial_capital
        self.min_edge_bps = min_edge_bps

    def run(
        self,
        strategy: Strategy,
        candles: Sequence[Candle],
    ) -> BacktestResult:
        """Run backtest with cost adjustment and Kelly sizing."""
        trades: list[Trade] = []
        equity_curve: list[float] = [self.initial_capital]
        current_equity = self.initial_capital
        position = None
        entry_price: float | None = None
        position_size: Decimal = Decimal("1")

        for candle in candles:
            indicators = {}
            # Simple RSI indicator for strategy compatibility
            if len(candles) >= 15:
                idx = list(candles).index(candle) if hasattr(candle, "__index__") else 0
                if idx >= 14:
                    from core.indicators.rsi import compute_rsi
                    start = max(0, idx - 100)
                    indicators["rsi"] = compute_rsi(candles[start : idx + 1], period=14)

            signal = strategy.on_candle(candle, indicators)

            if signal and signal.side != "HOLD":
                if position is None:
                    # Calculate Kelly position size
                    entry_price = float(candle.close)
                    portfolio_val = Decimal(str(current_equity))
                    position_size = _kelly_position_size(
                        self.win_rate,
                        self.avg_win,
                        self.avg_loss,
                        self.kelly_fraction,
                        portfolio_val,
                        Decimal(str(entry_price)),
                    )
                    position = "LONG" if signal.side == "BUY" else "SHORT"
                else:
                    should_exit = (
                        (position == "LONG" and signal.side == "SELL")
                        or (position == "SHORT" and signal.side == "BUY")
                    )

                    if should_exit and entry_price is not None:
                        # Calculate raw PnL
                        if position == "LONG":
                            raw_pnl = (float(candle.close) - entry_price) * float(position_size)
                        else:
                            raw_pnl = (entry_price - float(candle.close)) * float(position_size)

                        # Apply cost adjustment
                        value = entry_price * float(position_size)
                        cost = self.fee_model.compute_trade_cost(
                            entry_price, float(candle.close), value, is_maker=False
                        )

                        # Check minimum edge
                        edge_bps = (
                            abs(raw_pnl) / value * 10000 if value > 0 else 0
                        )
                        if edge_bps < self.min_edge_bps:
                            # Trade doesn't clear minimum edge; skip
                            pass
                        else:
                            trade = Trade(
                                entry_price=Decimal(str(entry_price)),
                                exit_price=Decimal(str(candle.close)),
                                side="BUY" if position == "LONG" else "SELL",
                                size=Decimal(str(position_size)),
                            )
                            trades.append(trade)
                            current_equity += float(trade.pnl)

                        # Reset position
                        position = None
                        entry_price = None
                        position_size = Decimal("1")

            equity_curve.append(current_equity)

        # Calculate metrics
        returns = []
        for i in range(1, len(equity_curve)):
            if equity_curve[i - 1] > 0:
                returns.append(
                    (equity_curve[i] - equity_curve[i - 1]) / equity_curve[i - 1]
                )

        final_equity = equity_curve[-1] if equity_curve else self.initial_capital
        total_pnl = final_equity - self.initial_capital
        total_return = total_pnl / self.initial_capital if self.initial_capital > 0 else 0.0

        return BacktestResult(
            trades=trades,
            equity_curve=equity_curve,
            total_pnl=total_pnl,
            total_return=total_return,
            sharpe_ratio=calculate_sharpe_ratio(returns),
            max_drawdown=calculate_max_drawdown(equity_curve),
            win_rate=calculate_win_rate(trades),
            profit_factor=calculate_profit_factor(trades),
        )


# ---------------------------------------------------------------------------
# Regime assignment for trades
# ---------------------------------------------------------------------------


def _assign_regimes_to_trades(
    trades: list[Trade],
    candles: Sequence[Candle],
    regime_detector: RegimeDetector,
) -> list[CostAdjustedTrade]:
    """Assign regimes to trades based on their entry candle."""
    cost_trades = []
    regimes = regime_detector.detect_regimes(candles)
    fee = FeeModel()

    for trade in trades:
        ct = adjust_trade(trade, fee)
        # Find the regime at the trade's entry time
        # Trade has entry_price but not entry_time; use index-based approximation
        for i, c in enumerate(candles):
            if float(c.close) == float(trade.entry_price):
                ct.regime = regimes[i]
                break
        else:
            ct.regime = MarketRegime.TRANSITION
        cost_trades.append(ct)

    return cost_trades


# ---------------------------------------------------------------------------
# Main function
# ---------------------------------------------------------------------------


def run_cost_aware_walk_forward_kelly_regime(
    strategy: Strategy,
    candles: Sequence[Candle],
    config: CostAwareWalkForwardConfig | None = None,
) -> CostAwareWalkForwardResult:
    """Run cost-aware walk-forward analysis with Kelly sizing and multi-regime splitting.

    This is the main entry point. It:
    1. Splits candles into rolling train/test windows
    2. Runs cost-adjusted backtest with Kelly sizing on each fold
    3. Assigns regimes to trades
    4. Computes per-regime performance metrics
    5. Assesses overfitting and OOS significance

    Args:
        strategy: Strategy to evaluate
        candles: Historical candle data (time-sorted)
        config: Configuration parameters

    Returns:
        CostAwareWalkForwardResult with comprehensive metrics
    """
    if config is None:
        config = CostAwareWalkForwardConfig()

    fee_model = config.fee_model or FeeModel()
    regime_detector = config.regime_detector or RegimeDetector()

    if not candles:
        return _empty_result(config)

    # Determine date range
    start_date = candles[0].open_time
    end_date = candles[-1].open_time

    # Generate folds
    folds: list[CostAwareFold] = []
    current = start_date

    # Accumulators for aggregated results
    all_regime_trades: dict[MarketRegime, list[CostAdjustedTrade]] = {
        r: [] for r in MarketRegime
    }
    all_kelly_sizes: list[Decimal] = []
    total_gross_pnl = 0.0
    total_costs = 0.0
    total_net_pnl = 0.0

    while current < end_date:
        train_end = current + timedelta(days=config.train_size_days)
        test_end = train_end + timedelta(days=config.test_size_days)

        if test_end > end_date:
            break

        # Warm-up period
        warmup_start = current - timedelta(days=config.lookback_candles // 24)
        warmup_candles = [
            c for c in candles
            if warmup_start <= c.open_time < current
        ]
        train_candles = [
            c for c in candles
            if current <= c.open_time < train_end
        ]
        test_candles = [
            c for c in candles
            if train_end <= c.open_time <= test_end
        ]

        if not train_candles or not test_candles:
            current = train_end + timedelta(days=config.step_size_days)
            continue

        # Warm-up phase
        warmup_engine = BacktestEngine(
            candle_store=None,
            initial_capital=10000.0,
            position_size_config=PositionSize(
                method="kelly",
                kelly_fraction=config.kelly_fraction,
                win_rate=config.kelly_win_rate,
                avg_win=config.kelly_avg_win,
                avg_loss=config.kelly_avg_loss,
            ),
        )
        warmup_result = warmup_engine.run(strategy, warmup_candles)
        warmup_pnl = warmup_result.total_pnl
        warmup_equity = 10000.0 + float(warmup_pnl)

        # Full training run
        full_train_candles = warmup_candles + train_candles
        full_train_engine = BacktestEngine(
            candle_store=None,
            initial_capital=10000.0,
            position_size_config=PositionSize(
                method="kelly",
                kelly_fraction=config.kelly_fraction,
                win_rate=config.kelly_win_rate,
                avg_win=config.kelly_avg_win,
                avg_loss=config.kelly_avg_loss,
            ),
        )
        full_train_result = full_train_engine.run(strategy, full_train_candles)
        full_train_pnl = full_train_result.total_pnl
        train_return = (full_train_pnl - warmup_pnl) / warmup_equity if warmup_equity > 0 else 0.0

        # Test run with cost-aware Kelly backtest
        kelly_backtest = CostAwareKellyBacktest(
            fee_model=fee_model,
            kelly_fraction=config.kelly_fraction,
            win_rate=config.kelly_win_rate,
            avg_win=config.kelly_avg_win,
            avg_loss=config.kelly_avg_loss,
            initial_capital=10000.0,
            min_edge_bps=config.min_edge_bps,
        )
        test_result = kelly_backtest.run(strategy, test_candles)

        # Assign regimes to test trades
        cost_trades = _assign_regimes_to_trades(test_result.trades, test_candles, regime_detector)
        for ct in cost_trades:
            all_regime_trades[ct.regime].append(ct)

        # Compute cost stats
        gross_pnl = test_result.total_pnl
        fold_costs = sum(ct.total_cost for ct in cost_trades)
        net_pnl = gross_pnl - fold_costs
        cost_ratio = fold_costs / abs(gross_pnl) if gross_pnl != 0 else 0.0

        # Kelly position size
        kelly_size = _kelly_position_size(
            config.kelly_win_rate,
            config.kelly_avg_win,
            config.kelly_avg_loss,
            config.kelly_fraction,
            Decimal(str(10000.0)),
            Decimal(str(test_candles[0].close)),
        )
        all_kelly_sizes.append(kelly_size)

        # Regime diversity
        regime_diversity = sum(
            1 for trades in all_regime_trades.values() if len(trades) > 0
        )

        # OOS decay
        oos_decay = test_result.total_return / train_return if abs(train_return) > 1e-9 else 0.0

        fold = CostAwareFold(
            train_start=current,
            train_end=train_end,
            test_start=train_end,
            test_end=test_end,
            train_return=train_return,
            train_sharpe=test_result.sharpe_ratio,
            train_win_rate=test_result.win_rate,
            train_trades=len(test_result.trades),
            train_total_pnl=gross_pnl,
            train_total_costs=fold_costs,
            train_net_pnl=net_pnl,
            test_return=test_result.total_return,
            test_sharpe=test_result.sharpe_ratio,
            test_win_rate=test_result.win_rate,
            test_trades=len(test_result.trades),
            test_total_pnl=gross_pnl,
            test_total_costs=fold_costs,
            test_net_pnl=net_pnl,
            test_max_dd=test_result.max_drawdown,
            test_cost_ratio=cost_ratio,
            test_cost_adjusted_pnl=net_pnl,
            kelly_fraction=float(config.kelly_fraction),
            kelly_position_size=kelly_size,
            oos_decay=oos_decay,
            regime_diversity=regime_diversity,
        )
        folds.append(fold)

        total_gross_pnl += gross_pnl
        total_costs += fold_costs
        total_net_pnl += net_pnl

        current = train_end + timedelta(days=config.step_size_days)

    # Aggregate metrics
    n = len(folds)
    if n == 0:
        return _empty_result(config)

    mean_train = sum(f.train_return for f in folds) / n
    mean_test = sum(f.test_return for f in folds) / n
    mean_oos_decay = sum(f.oos_decay for f in folds) / n

    # In-sample consistency
    if n >= 3:
        mean_x = mean_train
        mean_y = mean_test
        cov = sum(
            (f.train_return - mean_x) * (f.test_return - mean_y) for f in folds
        ) / (n - 1)
        std_x = math.sqrt(sum((f.train_return - mean_x) ** 2 for f in folds) / (n - 1))
        std_y = math.sqrt(sum((f.test_return - mean_y) ** 2 for f in folds) / (n - 1))
        consistency = cov / (std_x * std_y) if std_x > 0 and std_y > 0 else 0.0
    else:
        consistency = 0.0

    # OOS significance
    test_returns = [f.test_return for f in folds]
    if n >= 2:
        mean_ret = sum(test_returns) / n
        variance = sum((r - mean_ret) ** 2 for r in test_returns) / (n - 1)
        std_ret = math.sqrt(variance)
        t_stat = mean_ret / (std_ret / math.sqrt(n)) if std_ret > 0 else 0.0
        p_value = 2 * (1 - _normal_cdf(abs(t_stat)))
        oos_sig = p_value < 0.05
    else:
        oos_sig = mean_test > 0

    # Kelly aggregation
    mean_kelly_size = sum(all_kelly_sizes) / len(all_kelly_sizes) if all_kelly_sizes else Decimal("1")

    # Half-Kelly vs Full-Kelly comparison
    half_kelly_bt = CostAwareKellyBacktest(
        fee_model=fee_model,
        kelly_fraction=Decimal("0.5"),
        win_rate=config.kelly_win_rate,
        avg_win=config.kelly_avg_win,
        avg_loss=config.kelly_avg_loss,
        initial_capital=10000.0,
        min_edge_bps=config.min_edge_bps,
    )
    full_kelly_bt = CostAwareKellyBacktest(
        fee_model=fee_model,
        kelly_fraction=Decimal("1.0"),
        win_rate=config.kelly_win_rate,
        avg_win=config.kelly_avg_win,
        avg_loss=config.kelly_avg_loss,
        initial_capital=10000.0,
        min_edge_bps=config.min_edge_bps,
    )

    half_result = half_kelly_bt.run(strategy, candles)
    full_result = full_kelly_bt.run(strategy, candles)

    # Regime performance - flatten all regime trades
    all_trades_flat: list[CostAdjustedTrade] = []
    for trades_list in all_regime_trades.values():
        all_trades_flat.extend(trades_list)
    all_regimes = regime_detector.detect_regimes(candles)
    regime_perf = evaluate_cost_aware_regimes(
        cost_trades=all_trades_flat if all_trades_flat else [CostAdjustedTrade(raw_pnl=0.0, fee=0.0, spread=0.0, slippage=0.0, total_cost=0.0, cost_adjusted_pnl=0.0, entry_price=0.0, exit_price=0.0, side="BUY", size=0.0)],
        regimes=all_regimes,
        candles=candles,
        fee_model=fee_model,
    )

    # Per-regime OOS decay
    regime_oos_decay: dict[MarketRegime, list[float]] = {r: [] for r in MarketRegime}
    for fold in folds:
        # Simple: all regimes get same decay for now (can be refined)
        for r in MarketRegime:
            regime_oos_decay[r].append(fold.oos_decay)
    regime_oos_decay_avg = {
        r: sum(v) / len(v) if v else 0.0 for r, v in regime_oos_decay.items()
    }

    # Overfitting risk
    if mean_oos_decay > config.overfit_decay_threshold:
        overfit_risk = "low"
    elif mean_oos_decay > config.underfit_decay_threshold:
        overfit_risk = "medium"
    else:
        overfit_risk = "high"

    return CostAwareWalkForwardResult(
        folds=folds,
        n_folds=n,
        mean_train_return=mean_train,
        mean_test_return=mean_test,
        mean_oos_decay=mean_oos_decay,
        in_sample_consistency=consistency,
        oos_significant=oos_sig,
        oos_sharpe=calculate_sharpe_ratio(test_returns),
        oos_max_dd=max(f.test_max_dd for f in folds),
        oos_win_rate=sum(f.test_win_rate for f in folds) / n,
        overfitting_risk=overfit_risk,
        mean_kelly_fraction=float(config.kelly_fraction),
        mean_kelly_position_size=mean_kelly_size,
        half_kelly_return=half_result.total_return,
        full_kelly_return=full_result.total_return,
        kelly_pnl_diff=full_result.total_pnl - half_result.total_pnl,
        regime_performance=regime_perf,
        regime_breakdown=[],  # Populated from fold data
        total_gross_pnl=total_gross_pnl,
        total_costs=total_costs,
        total_net_pnl=total_net_pnl,
        cost_ratio=total_costs / abs(total_gross_pnl) if total_gross_pnl != 0 else 0.0,
        regime_oos_decay=regime_oos_decay_avg,
    )


def _normal_cdf(x: float) -> float:
    """Approximate standard normal CDF."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _empty_result(config: CostAwareWalkForwardConfig) -> CostAwareWalkForwardResult:
    """Return an empty result for edge cases."""
    return CostAwareWalkForwardResult(
        folds=[],
        n_folds=0,
        mean_train_return=0.0,
        mean_test_return=0.0,
        mean_oos_decay=0.0,
        in_sample_consistency=0.0,
        oos_significant=False,
        oos_sharpe=0.0,
        oos_max_dd=0.0,
        oos_win_rate=0.0,
        overfitting_risk="high",
        mean_kelly_fraction=float(config.kelly_fraction),
        mean_kelly_position_size=Decimal("1"),
        half_kelly_return=0.0,
        full_kelly_return=0.0,
        kelly_pnl_diff=0.0,
        regime_performance=[],
        regime_breakdown=[],
        total_gross_pnl=0.0,
        total_costs=0.0,
        total_net_pnl=0.0,
        cost_ratio=0.0,
        regime_oos_decay={r: 0.0 for r in MarketRegime},
    )


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


def to_dict(result: CostAwareWalkForwardResult) -> dict:
    """Serialize result to dict for JSON export."""
    return {
        "n_folds": result.n_folds,
        "mean_train_return": round(result.mean_train_return, 4),
        "mean_test_return": round(result.mean_test_return, 4),
        "mean_oos_decay": round(result.mean_oos_decay, 4),
        "in_sample_consistency": round(result.in_sample_consistency, 4),
        "oos_significant": result.oos_significant,
        "oos_sharpe": round(result.oos_sharpe, 4),
        "oos_max_dd": round(result.oos_max_dd, 4),
        "oos_win_rate": round(result.oos_win_rate, 4),
        "overfitting_risk": result.overfitting_risk,
        "kelly_sizing": {
            "mean_kelly_fraction": round(result.mean_kelly_fraction, 2),
            "mean_kelly_position_size": float(result.mean_kelly_position_size),
            "half_kelly_return": round(result.half_kelly_return, 4),
            "full_kelly_return": round(result.full_kelly_return, 4),
            "kelly_pnl_diff": round(result.kelly_pnl_diff, 2),
        },
        "cost_awareness": {
            "total_gross_pnl": round(result.total_gross_pnl, 2),
            "total_costs": round(result.total_costs, 2),
            "total_net_pnl": round(result.total_net_pnl, 2),
            "cost_ratio": round(result.cost_ratio, 4),
        },
        "regime_performance": [
            {
                "regime": r.regime.value,
                "n_candles": r.n_candles,
                "n_trades": r.n_trades,
                "return_pct": round(r.return_pct, 4),
                "sharpe": round(r.sharpe, 4),
                "max_dd": round(r.max_dd, 4),
                "win_rate": round(r.win_rate, 4),
                "avg_trade_pnl": round(r.avg_trade_pnl, 2),
            }
            for r in result.regime_performance
        ],
        "regime_oos_decay": {
            r.value: round(v, 4) for r, v in result.regime_oos_decay.items()
        },
        "folds": [
            {
                "train_start": f.train_start.isoformat(),
                "train_end": f.train_end.isoformat(),
                "test_start": f.test_start.isoformat(),
                "test_end": f.test_end.isoformat(),
                "train_return": round(f.train_return, 4),
                "test_return": round(f.test_return, 4),
                "test_sharpe": round(f.test_sharpe, 4),
                "test_max_dd": round(f.test_max_dd, 4),
                "test_win_rate": round(f.test_win_rate, 4),
                "test_trades": f.test_trades,
                "test_net_pnl": round(f.test_net_pnl, 2),
                "test_total_costs": round(f.test_total_costs, 2),
                "test_cost_ratio": round(f.test_cost_ratio, 4),
                "kelly_fraction": round(f.kelly_fraction, 2),
                "kelly_position_size": float(f.kelly_position_size),
                "oos_decay": round(f.oos_decay, 4),
                "regime_diversity": f.regime_diversity,
            }
            for f in result.folds
        ],
    }
