from __future__ import annotations

from dataclasses import dataclass

from core.types import IndicatorSignal


@dataclass(frozen=True)
class WeightedScore:
    score: int


def normalize_weights(weights: dict[str, float]) -> dict[str, float]:
    total = sum(weights.values())
    if total <= 0:
        raise ValueError("weights total must be > 0")
    return {k: v / total for k, v in weights.items()}


def score_signals(*, signals: list[IndicatorSignal], weights: dict[str, float]) -> WeightedScore:
    """Compute a 0-100 score from indicator signals.

    The model is intentionally basic and should be refined per specs.
    """

    normalized = normalize_weights(weights)

    accum = 0.0
    for sig in signals:
        weight = normalized.get(sig.code, 0.0)
        accum += weight * float(max(0, min(sig.strength, 100)))

    return WeightedScore(score=int(round(max(0.0, min(accum, 100.0)))))
