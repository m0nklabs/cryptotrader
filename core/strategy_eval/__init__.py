"""Strategy evaluation framework.

Optimizes realistic net profitability after fees, slippage, latency, and drawdown.
Emphasizes walk-forward validation, anti-overfitting checks, regime awareness,
and rejection criteria for fake alpha.
"""

from __future__ import annotations

from core.strategy_eval.types import *  # noqa: F401,F403
from core.strategy_eval.walk_forward import WalkForwardResult, run_walk_forward  # noqa: F401
from core.strategy_eval.regime import RegimeDetector, detect_regimes  # noqa: F401
from core.strategy_eval.overfitting import (  # noqa: F401
    OverfittingCheck,
    check_overfitting,
    compute_parameter_stability,
)
from core.strategy_eval.evaluator import StrategyEvaluator, EvaluationReport  # noqa: F401
from core.strategy_eval.rejection import (  # noqa: F401
    RejectionCriteria,
    evaluate_rejection,
    is_fake_alpha,
)

__all__ = [
    "WalkForwardResult",
    "run_walk_forward",
    "RegimeDetector",
    "detect_regimes",
    "OverfittingCheck",
    "check_overfitting",
    "compute_parameter_stability",
    "StrategyEvaluator",
    "EvaluationReport",
    "RejectionCriteria",
    "evaluate_rejection",
    "is_fake_alpha",
]
