"""Type definitions for the strategy evaluation framework."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


# ---------------------------------------------------------------------------
# Market regimes
# ---------------------------------------------------------------------------


class MarketRegime(str, Enum):
    """Detected market regime."""

    TRENDING_UP = "trending_up"
    TRENDING_DOWN = "trending_down"
    RANGING = "ranging"
    HIGH_VOL = "high_volatility"
    LOW_VOL = "low_volatility"
    TRANSITION = "transition"


# ---------------------------------------------------------------------------
# Walk-forward
# ---------------------------------------------------------------------------


@dataclass
class WalkForwardFold:
    """One fold (window) in a walk-forward evaluation.

    Each fold has a training period for parameter optimization and a
    test (OOS = out-of-sample) period for performance validation.
    """

    train_start: datetime
    train_end: datetime
    test_start: datetime
    test_end: datetime
    train_return: float = 0.0
    test_return: float = 0.0
    test_sharpe: float = 0.0
    test_max_dd: float = 0.0
    test_win_rate: float = 0.0
    test_trades: int = 0
    oos_decay: float = 0.0  # test_return / train_return (0-1 = good, >1 = overfitted)
    oos_returns: list[float] = field(default_factory=list)  # per-trade OOS returns in this fold (PnL %)
    oos_trades: list[dict] = field(default_factory=list)  # per-trade OOS trade dicts (entry/exit price, side, PnL)
    oos_is_partial: bool = False  # fold's OOS period extends beyond available data


@dataclass
class WalkForwardResult:
    """Aggregated walk-forward evaluation results.

    Combines metrics across all folds to produce a unified OOS assessment.
    """

    folds: list[WalkForwardFold]
    n_folds: int
    mean_train_return: float
    mean_test_return: float
    mean_oos_decay: float
    in_sample_consistency: float  # correlation between train and test returns
    oos_significant: bool  # test return significantly > 0
    oos_sharpe: float  # aggregated Sharpe across test folds
    oos_max_dd: float  # worst test drawdown
    oos_win_rate: float  # mean test win rate
    overfitting_risk: str  # "low", "medium", "high"
    oos_returns: list[float] = field(default_factory=list)  # aggregate OOS returns across all folds (PnL %)
    oos_trades: list[dict] = field(default_factory=list)  # all OOS trade dicts across all folds
    total_oos_trades: int = 0  # total count of OOS trades across all folds


# ---------------------------------------------------------------------------
# Regime evaluation
# ---------------------------------------------------------------------------


@dataclass
class RegimePerformance:
    """Strategy performance within a specific regime.

    Each regime (e.g., TRENDING_UP, RANGING) gets its own performance
    summary including OOS-specific metrics.
    """

    regime: MarketRegime
    n_candles: int
    n_trades: int
    return_pct: float
    sharpe: float
    max_dd: float
    win_rate: float
    avg_trade_pnl: float
    oos_trades: int = 0  # count of OOS trades in this regime
    oos_returns: list[float] = field(default_factory=list)  # per-trade OOS returns in this regime (PnL %)


# ---------------------------------------------------------------------------
# Overfitting detection
# ---------------------------------------------------------------------------


@dataclass
class ParameterSweep:
    """Result of sweeping one parameter around its optimal value."""

    param_name: str
    param_values: list[Any]
    returns: list[float]
    best_value: Any
    best_return: float
    return_range: float  # max - min
    std_dev: float
    is_stable: bool  # stable if return_range < 2 * std_dev


@dataclass
class OverfittingCheck:
    """Results of overfitting analysis."""

    parameter_stability: list[ParameterSweep]
    multiple_testing_corrected: bool
    bonferroni_threshold: float
    effective_tests: int
    is_overfitted: bool
    overfit_score: float  # 0 = no overfit, 1 = severe overfit


# ---------------------------------------------------------------------------
# Rejection criteria
# ---------------------------------------------------------------------------


@dataclass
class RejectionCriteria:
    """Criteria for rejecting fake alpha."""

    min_trades: int = 30
    min_sharpe: float = 1.0
    min_win_rate: float = 0.45
    min_profit_factor: float = 1.2
    min_net_return: float = 0.02  # 2% minimum net return
    max_drawdown_limit: float = 0.15  # 15% max drawdown
    min_trade_count_per_regime: int = 5
    significance_level: float = 0.05  # p-value threshold


@dataclass
class RejectionResult:
    """Result of fake alpha rejection."""

    rejected: bool
    reasons: list[str]
    net_return: float
    gross_return: float
    total_costs: float
    cost_ratio: float  # costs / gross return
    sharpe: float
    win_rate: float
    profit_factor: float
    max_drawdown: float
    trade_count: int
    regime_diversity: int  # number of regimes with sufficient trades
    is_significant: bool  # statistically significant
    p_value: float


# ---------------------------------------------------------------------------
# Evaluation report
# ---------------------------------------------------------------------------


@dataclass
class EvaluationReport:
    """Comprehensive evaluation report for a strategy."""

    strategy_name: str
    symbol: str
    exchange: str
    timeframe: str
    period_start: datetime
    period_end: datetime
    initial_capital: float

    # Raw performance
    gross_return: float
    net_return: float
    total_fees: float
    total_spread: float
    total_slippage: float
    total_latency_cost: float
    total_costs: float
    cost_ratio: float

    # Risk metrics
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown: float
    calmar_ratio: float
    omega_ratio: float

    # Trade stats
    total_trades: int
    win_rate: float
    profit_factor: float
    avg_win: float
    avg_loss: float
    largest_win: float
    largest_loss: float
    avg_trade_duration_bars: float

    # Walk-forward
    walk_forward: WalkForwardResult | None = None

    # Regime analysis
    regime_performance: list[RegimePerformance] = field(default_factory=list)

    # Overfitting
    overfitting: OverfittingCheck | None = None

    # Rejection
    rejection: RejectionResult | None = None

    # Overall verdict
    verdict: str = "PASS"  # PASS, CONDITIONAL_PASS, REJECT
    confidence: float = 0.0  # 0-1 confidence score
