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

__all__ = [
    "IndicatorContribution",
    "ScoringResult",
    "WeightedScore",
    "normalize_weights",
    "score_signals",
]
