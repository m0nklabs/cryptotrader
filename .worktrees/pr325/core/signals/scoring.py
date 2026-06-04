from __future__ import annotations

from dataclasses import dataclass

from core.types import IndicatorSignal


@dataclass(frozen=True)
class IndicatorContribution:
    """Per-indicator contribution to the final score."""

    code: str
    strength: int  # 0-100
    weight: float  # normalized weight
    contribution: float  # weight * strength
    reason: str


@dataclass(frozen=True)
class ScoringResult:
    """Result of signal scoring with explainability."""

    score: int  # final 0-100 score
    contributions: tuple[IndicatorContribution, ...]
    explanation: str


@dataclass(frozen=True)
class WeightedScore:
    """Legacy compatibility class."""

    score: int


def normalize_weights(weights: dict[str, float]) -> dict[str, float]:
    """Normalize weights to sum to 1.0.

    Args:
        weights: Dictionary of indicator codes to weights

    Returns:
        Normalized weights that sum to 1.0

    Raises:
        ValueError: If total weight is <= 0
    """
    total = sum(weights.values())
    if total <= 0:
        raise ValueError("weights total must be > 0")
    return {k: v / total for k, v in weights.items()}


def score_signals(*, signals: list[IndicatorSignal], weights: dict[str, float]) -> ScoringResult:
    """Compute a 0-100 score from indicator signals with explainability.

    Args:
        signals: List of indicator signals to score
        weights: Dictionary mapping indicator codes to weights (will be auto-normalized)

    Returns:
        ScoringResult containing score, per-indicator contributions, and human-readable explanation

    Edge cases:
        - Empty signals: returns score=0 with explanation
        - Zero weights: raises ValueError
        - Signal with no matching weight: contributes 0 to score
    """
    # Handle empty signals
    if not signals:
        return ScoringResult(
            score=0,
            contributions=(),
            explanation="No signals provided - score is 0",
        )

    # Normalize weights (raises ValueError if total <= 0)
    normalized = normalize_weights(weights)

    # Calculate per-indicator contributions
    contributions: list[IndicatorContribution] = []
    accum = 0.0

    for sig in signals:
        weight = normalized.get(sig.code, 0.0)
        # Clamp strength to 0-100 range
        clamped_strength = max(0, min(sig.strength, 100))
        contribution = weight * float(clamped_strength)
        accum += contribution

        contributions.append(
            IndicatorContribution(
                code=sig.code,
                strength=clamped_strength,
                weight=weight,
                contribution=contribution,
                reason=sig.reason,
            )
        )

    # Clamp final score to 0-100
    final_score = int(round(max(0.0, min(accum, 100.0))))

    # Build human-readable explanation
    explanation = _build_explanation(final_score, contributions)

    return ScoringResult(
        score=final_score,
        contributions=tuple(contributions),
        explanation=explanation,
    )


def _build_explanation(score: int, contributions: list[IndicatorContribution]) -> str:
    """Build human-readable explanation of the score.

    Args:
        score: Final computed score
        contributions: List of per-indicator contributions

    Returns:
        Human-readable explanation string
    """
    if not contributions:
        return "No signals provided - score is 0"

    lines = [f"Final score: {score}/100"]
    lines.append("\nPer-indicator contributions:")

    # Sort by contribution (descending) for readability
    sorted_contribs = sorted(contributions, key=lambda c: c.contribution, reverse=True)

    for contrib in sorted_contribs:
        lines.append(
            f"  • {contrib.code}: {contrib.contribution:.1f} pts "
            f"(weight={contrib.weight:.2f}, strength={contrib.strength})"
        )

    return "\n".join(lines)
