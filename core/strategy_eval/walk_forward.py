"""Walk-forward validation for strategy evaluation.

Implements rolling window backtest with train/test splits to validate
that strategy performance is robust and not overfitted to a specific period.
"""

from __future__ import annotations

from copy import deepcopy
import json
import logging
import math
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Sequence

from core.strategy_eval.types import (
    WalkForwardFold,
    WalkForwardResult,
)
from core.types import Candle
from core.backtest.engine import BacktestEngine, BacktestResult, Strategy
from core.backtest.metrics import Trade, calculate_sharpe_ratio
from core.fees.model import FeeModel
from core.risk.sizing import PositionSize

logger = logging.getLogger(__name__)


def _parse_timeframe_to_timedelta(timeframe: str) -> timedelta:
    """Convert a timeframe string (e.g., '1m', '5m', '1h', '4h', '1d') to a timedelta."""
    if not isinstance(timeframe, str) or not timeframe:
        raise ValueError("Timeframe must be a non-empty string")

    unit = timeframe[-1]
    value_str = timeframe[:-1]

    if not value_str.isdigit():
        raise ValueError(f"Invalid timeframe value in '{timeframe}'")

    value = int(value_str)

    if unit == "m":
        return timedelta(minutes=value)
    if unit == "h":
        return timedelta(hours=value)
    if unit == "d":
        return timedelta(days=value)
    raise ValueError(f"Unsupported timeframe unit: '{unit}' in '{timeframe}'")


def _trade_to_dict(trade: Trade) -> dict:
    """Convert a Trade object to a serializable dict."""
    return {
        "entry_price": float(trade.entry_price),
        "exit_price": float(trade.exit_price),
        "side": trade.side,
        "size": float(trade.size),
        "pnl": float(trade.pnl),
    }


def _clone_strategy(strategy: Strategy) -> Strategy:
    """Create an isolated strategy instance for a single walk-forward run."""
    return deepcopy(strategy)


# ---------------------------------------------------------------------------
# Walk-forward engine
# ---------------------------------------------------------------------------


@dataclass
class WalkForwardConfig:
    """Configuration for walk-forward validation."""

    train_size_days: int = 90  # training window in days
    test_size_days: int = 30  # testing window in days
    step_size_days: int = 15  # walk-forward step
    min_folds: int = 5  # minimum folds for significance
    lookback_candles: int = 200  # indicator lookback for warm-up


def _split_candles(
    candles: Sequence[Candle],
    start: datetime,
    end: datetime,
    end_exclusive: bool = False,
) -> list[Candle]:
    """Filter candles to a date range.

    Args:
        candles: All available candles.
        start: Start of the range (inclusive).
        end: End of the range.
        end_exclusive: If True, end is exclusive (candle at exactly *end* goes to the next window).

    Returns:
        Candles whose open_time falls within [start, end) or [start, end] depending on end_exclusive.
    """
    if end_exclusive:
        return [c for c in candles if start <= c.open_time < end]
    return [c for c in candles if start <= c.open_time <= end]


def _compute_fold_metrics(
    result: BacktestResult,
    train_return: float,
) -> WalkForwardFold:
    """Compute a fold's metrics."""
    oos_decay = train_return / result.total_return if abs(train_return) > 1e-9 else 0.0

    return WalkForwardFold(
        train_return=train_return,
        test_return=result.total_return,
        test_sharpe=result.sharpe_ratio,
        test_max_dd=result.max_drawdown,
        test_win_rate=result.win_rate,
        test_trades=len(result.trades),
        oos_decay=oos_decay,
    )


def run_walk_forward(
    strategy: Strategy,
    candles: Sequence[Candle],
    config: WalkForwardConfig | None = None,
    fee_model: FeeModel | None = None,
    position_size_config: PositionSize | None = None,
) -> WalkForwardResult:
    """Run walk-forward validation on a strategy.

    Splits the data into rolling train/test windows and evaluates
    the strategy on each fold. Returns aggregated results with
    overfitting assessment.

    Args:
        strategy: Strategy to evaluate
        candles: Historical candles (must be time-sorted)
        config: Walk-forward configuration
        fee_model: Optional fee model for cost-aware evaluation
        position_size_config: Position sizing config (default: Kelly)

    Returns:
        WalkForwardResult with aggregated metrics
    """
    if config is None:
        config = WalkForwardConfig()

    if position_size_config is None:
        position_size_config = PositionSize(
            method="kelly",
            kelly_fraction=Decimal("0.5"),
            win_rate=Decimal("0.55"),
            avg_win=Decimal("0.05"),
            avg_loss=Decimal("0.02"),
        )

    if not candles:
        return WalkForwardResult(
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
            oos_trades=[],
            total_oos_trades=0,
        )

    if fee_model is not None and not isinstance(strategy, _CostAwareStrategy):
        strategy = _CostAwareStrategy(strategy, fee_model)

    # Determine date range
    start_date = candles[0].open_time
    end_date = candles[-1].open_time

    # Generate fold boundaries
    folds: list[WalkForwardFold] = []
    current = start_date

    while current < end_date:
        train_end = current + timedelta(days=config.train_size_days)
        test_end = train_end + timedelta(days=config.test_size_days)

        # Check if test period extends beyond end_date
        partial_oos = test_end > end_date
        if partial_oos and test_end > end_date + timedelta(days=config.test_size_days):
            # Test period extends too far — skip if no train data
            if train_end > end_date:
                current = train_end + timedelta(days=config.step_size_days)
                continue

        # Warm-up: include lookback candles before training for indicator state
        warmup_start = current - timedelta(days=config.lookback_candles // 24)

        # Strict split: train uses [warmup_start, train_end) (exclusive end),
        # test uses [train_end, test_end] (inclusive end).
        # This prevents the boundary candle at train_end from appearing in both sets.
        # Also, warmup uses end_exclusive so it does not include the candle at 'current'.
        warmup_candles = _split_candles(candles, warmup_start, current, end_exclusive=True)
        train_candles = _split_candles(candles, current, train_end, end_exclusive=True)
        # For partial OOS, clip test candles to end_date
        if partial_oos:
            test_candles = _split_candles(candles, train_end, end_date)
        else:
            test_candles = _split_candles(candles, train_end, test_end)

        if not train_candles and not partial_oos:
            current = train_end + timedelta(days=config.step_size_days)
            continue

        if not test_candles and not partial_oos:
            current = train_end + timedelta(days=config.step_size_days)
            continue

        # Warm-up phase: run through warmup candles to build indicator state
        # but exclude them from the training return calculation.
        warmup_engine = BacktestEngine(
            candle_store=None,
            initial_capital=10000.0,
            position_size_config=position_size_config,
        )
        warmup_result = warmup_engine.run(_clone_strategy(strategy), warmup_candles)

        # Full training run (warmup + training candles)
        full_train_candles = warmup_candles + train_candles
        full_train_engine = BacktestEngine(
            candle_store=None,
            initial_capital=10000.0,
            position_size_config=position_size_config,
        )
        full_train_result = full_train_engine.run(_clone_strategy(strategy), full_train_candles)

        # Compute training return excluding warmup PnL to avoid inflating
        # training performance with warmup-period trades.
        warmup_pnl = warmup_result.total_pnl
        full_train_pnl = full_train_result.total_pnl

        # Equity after warmup phase – the true denominator for the training-period return.
        # warmup_pnl is float in BacktestResult, so keep this calculation in float space.
        warmup_equity = 10000.0 + float(warmup_pnl)
        if warmup_equity <= 0.0:
            train_return = 0.0
        else:
            train_return = (full_train_pnl - warmup_pnl) / warmup_equity

        # Run testing (fresh start for OOS evaluation)
        test_engine = BacktestEngine(
            candle_store=None,
            initial_capital=10000.0,
            position_size_config=position_size_config,
        )
        test_result = test_engine.run(_clone_strategy(strategy), test_candles)

        # Capture OOS trades as serializable dicts
        oos_trades = [_trade_to_dict(t) for t in test_result.trades]

        fold = WalkForwardFold(
            train_start=current,
            train_end=train_end,
            test_start=train_end,
            test_end=test_end,
            train_return=train_return,
            test_return=test_result.total_return,
            test_sharpe=test_result.sharpe_ratio,
            test_max_dd=test_result.max_drawdown,
            test_win_rate=test_result.win_rate,
            test_trades=len(test_result.trades),
            oos_decay=(test_result.total_return / train_return if abs(train_return) > 1e-9 else 0.0),
            oos_trades=oos_trades,
            oos_is_partial=partial_oos,
        )
        folds.append(fold)

        # Log OOS trades for this fold
        if oos_trades:
            logger.info(
                "OOS fold [%s -> %s]: %d trades, return=%.4f, trades=%s",
                fold.test_start.isoformat(),
                fold.test_end.isoformat(),
                len(oos_trades),
                fold.test_return,
                [f"{t['side']}@{t['entry_price']:.2f}->{t['exit_price']:.2f} (PnL={t['pnl']:.2f})" for t in oos_trades],
            )

        current = train_end + timedelta(days=config.step_size_days)

    # Aggregate metrics
    n = len(folds)
    if n == 0:
        return WalkForwardResult(
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
            oos_trades=[],
            total_oos_trades=0,
        )

    mean_train = sum(f.train_return for f in folds) / n
    mean_test = sum(f.test_return for f in folds) / n
    mean_oos_decay = sum(f.oos_decay for f in folds) / n

    # In-sample consistency: correlation between train and test returns
    if n >= 3:
        mean_x = mean_train
        mean_y = mean_test
        cov = sum((f.train_return - mean_x) * (f.test_return - mean_y) for f in folds) / (n - 1)
        std_x = math.sqrt(sum((f.train_return - mean_x) ** 2 for f in folds) / (n - 1))
        std_y = math.sqrt(sum((f.test_return - mean_y) ** 2 for f in folds) / (n - 1))
        consistency = cov / (std_x * std_y) if std_x > 0 and std_y > 0 else 0.0
    else:
        consistency = 0.0

    # OOS significance: test return significantly > 0
    test_returns = [f.test_return for f in folds]
    if n >= 2:
        mean_ret = sum(test_returns) / n
        variance = sum((r - mean_ret) ** 2 for r in test_returns) / (n - 1)
        std_ret = math.sqrt(variance)
        # t-statistic
        t_stat = mean_ret / (std_ret / math.sqrt(n)) if std_ret > 0 else 0.0
        # Approximate p-value (two-tailed) using normal approximation
        p_value = 2 * (1 - _normal_cdf(abs(t_stat)))
        oos_sig = p_value < 0.05
    else:
        oos_sig = mean_test > 0

    # Aggregated OOS metrics
    oos_sharpe = calculate_sharpe_ratio(test_returns)
    oos_max_dd = max(f.test_max_dd for f in folds)
    oos_win_rate = sum(f.test_win_rate for f in folds) / n

    # Aggregate OOS trades across all folds
    all_oos_trades: list[dict] = []
    total_oos_trades = 0
    for f in folds:
        all_oos_trades.extend(f.oos_trades)
        total_oos_trades += f.test_trades

    # Overfitting risk assessment
    if mean_oos_decay > 0.7:
        overfit_risk = "low"
    elif mean_oos_decay > 0.4:
        overfit_risk = "medium"
    else:
        overfit_risk = "high"

    # Log summary of OOS trades
    logger.info(
        "Walk-forward complete: %d folds, %d OOS trades, mean train=%.4f, mean test=%.4f, OOS decay=%.4f, overfitting=%s, significant=%s",
        n,
        total_oos_trades,
        mean_train,
        mean_test,
        mean_oos_decay,
        overfit_risk,
        oos_sig,
    )

    return WalkForwardResult(
        folds=folds,
        n_folds=n,
        mean_train_return=mean_train,
        mean_test_return=mean_test,
        mean_oos_decay=mean_oos_decay,
        in_sample_consistency=consistency,
        oos_significant=oos_sig,
        oos_sharpe=oos_sharpe,
        oos_max_dd=oos_max_dd,
        oos_win_rate=oos_win_rate,
        overfitting_risk=overfit_risk,
        oos_trades=all_oos_trades,
        total_oos_trades=total_oos_trades,
    )


def _normal_cdf(x: float) -> float:
    """Approximate standard normal CDF."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


# ---------------------------------------------------------------------------
# Cost-aware walk-forward
# ---------------------------------------------------------------------------


def run_cost_aware_walk_forward(
    strategy: Strategy,
    candles: Sequence[Candle],
    fee_model: FeeModel,
    config: WalkForwardConfig | None = None,
) -> WalkForwardResult:
    """Walk-forward with explicit cost deduction.

    Subtracts fees, spread, and slippage from each trade's PnL
    to give realistic net performance.
    """
    if config is None:
        config = WalkForwardConfig()

    # Wrap strategy to apply costs
    cost_strategy = _CostAwareStrategy(strategy, fee_model)

    return run_walk_forward(cost_strategy, candles, config, fee_model)


class _CostAwareStrategy:
    """Strategy wrapper that deducts costs from PnL."""

    def __init__(self, inner: Strategy, fee_model: FeeModel) -> None:
        self.inner = inner
        self.fee_model = fee_model

    def on_candle(self, candle, indicators):
        signal = self.inner.on_candle(candle, indicators)
        if signal and signal.side != "HOLD":
            # Apply cost adjustment to strength
            cost = self.fee_model.estimate_cost(
                gross_notional=Decimal(str(candle.close)),
                taker=True,
            )
            # Reduce strength proportionally to cost
            cost_bps = float(cost.estimated_total_cost) / float(candle.close) * 10000
            adjusted_strength = max(0, signal.strength - int(cost_bps))
            signal.strength = adjusted_strength
        return signal


def log_oos_trades(
    result: WalkForwardResult,
    output_dir: str | None = None,
) -> Path:
    """Log OOS trades to a JSON file.

    Args:
        result: WalkForwardResult containing OOS trade data.
        output_dir: Directory to write the log file to. Defaults to BACKTEST_OUTPUT_DIR env var or /tmp.

    Returns:
        Path to the written log file.
    """
    if output_dir is None:
        output_dir = os.getenv("BACKTEST_OUTPUT_DIR", "/tmp")

    output_path = Path(output_dir) / "oos_trades.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Load existing data if present
    existing: list[dict] = []
    if output_path.exists():
        try:
            with open(output_path, "r") as f:
                existing = json.load(f)
            if not isinstance(existing, list):
                existing = [existing]
        except (json.JSONDecodeError, OSError):
            existing = []

    # Build the log entry
    entry = {
        "n_folds": result.n_folds,
        "total_oos_trades": result.total_oos_trades,
        "mean_train_return": result.mean_train_return,
        "mean_test_return": result.mean_test_return,
        "mean_oos_decay": result.mean_oos_decay,
        "oos_significant": result.oos_significant,
        "oos_sharpe": result.oos_sharpe,
        "oos_max_dd": result.oos_max_dd,
        "oos_win_rate": result.oos_win_rate,
        "overfitting_risk": result.overfitting_risk,
        "folds": [
            {
                "train_start": f.train_start.isoformat(),
                "train_end": f.train_end.isoformat(),
                "test_start": f.test_start.isoformat(),
                "test_end": f.test_end.isoformat(),
                "train_return": f.train_return,
                "test_return": f.test_return,
                "test_sharpe": f.test_sharpe,
                "test_max_dd": f.test_max_dd,
                "test_win_rate": f.test_win_rate,
                "test_trades": f.test_trades,
                "oos_decay": f.oos_decay,
                "oos_is_partial": f.oos_is_partial,
                "oos_trades": f.oos_trades,
            }
            for f in result.folds
        ],
        "oos_trades": result.oos_trades,
    }

    existing.append(entry)

    with open(output_path, "w") as f:
        json.dump(existing, f, indent=2, default=str)

    logger.info("Wrote OOS trades to %s (total entries: %d)", output_path, len(existing))
    return output_path
