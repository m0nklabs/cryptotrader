"""Signals and opportunity scoring.

This package is implemented against the canonical requirements in docs.
"""

from core.signals.scoring import (
    IndicatorContribution,
    ScoringResult,
    WeightedScore,
    normalize_weights,
    score_signals,
)
from core.signals.weights import (
    DEFAULT_WEIGHTS,
    get_weights,
    get_weights_async,
    load_weights_from_db,
)

__all__ = [
    "IndicatorContribution",
    "ScoringResult",
    "WeightedScore",
    "normalize_weights",
    "score_signals",
    "DEFAULT_WEIGHTS",
    "get_weights",
    "get_weights_async",
    "load_weights_from_db",
]
