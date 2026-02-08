"""Consensus engine — weighted voting across agent roles.

Aggregates individual RoleVerdicts into a single ConsensusDecision.
Supports:
- Weighted confidence voting
- Hard VETO (any role VETO blocks the trade)
- Configurable thresholds
"""

from __future__ import annotations

import logging

from core.ai.types import (
    ConsensusDecision,
    RoleVerdict,
    SignalAction,
)

logger = logging.getLogger(__name__)

# Minimum weighted confidence to act
DEFAULT_CONFIDENCE_THRESHOLD = 0.6

# Minimum number of agreeing roles to act
DEFAULT_MIN_AGREEMENT = 2


class ConsensusEngine:
    """Weighted voting consensus engine.

    Algorithm:
    1. Check for any VETO — if found, final action is NEUTRAL + vetoed_by.
    2. Compute weighted score per action (BUY, SELL, NEUTRAL).
    3. Winning action must exceed confidence threshold.
    4. Must have at least ``min_agreement`` roles agreeing.
    """

    def __init__(
        self,
        confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
        min_agreement: int = DEFAULT_MIN_AGREEMENT,
    ) -> None:
        self.confidence_threshold = confidence_threshold
        self.min_agreement = min_agreement

    def aggregate(self, verdicts: list[RoleVerdict]) -> ConsensusDecision:
        """Aggregate role verdicts into a consensus decision.

        Args:
            verdicts: List of verdicts from individual roles.

        Returns:
            A ConsensusDecision with the final action and reasoning.
        """
        if not verdicts:
            return ConsensusDecision(
                final_action="NEUTRAL",
                final_confidence=0.0,
                verdicts=verdicts,
                reasoning="No verdicts to aggregate.",
            )

        # Step 1: Check for VETOs
        veto_verdicts = [v for v in verdicts if v.action == "VETO"]
        if veto_verdicts:
            vetoer = veto_verdicts[0]
            return ConsensusDecision(
                final_action="NEUTRAL",
                final_confidence=0.0,
                verdicts=verdicts,
                reasoning=f"VETOED by {vetoer.role.value}: {vetoer.reasoning}",
                vetoed_by=vetoer.role,
            )

        # Step 2: Weighted scoring
        action_scores: dict[SignalAction, float] = {
            "BUY": 0.0,
            "SELL": 0.0,
            "NEUTRAL": 0.0,
        }
        action_counts: dict[SignalAction, int] = {
            "BUY": 0,
            "SELL": 0,
            "NEUTRAL": 0,
        }

        # Import RoleRegistry here to get weights
        from core.ai.roles.base import RoleRegistry

        for verdict in verdicts:
            role = RoleRegistry.get(verdict.role)
            weight = role.weight if role else 1.0
            action = verdict.action
            if action in action_scores:
                action_scores[action] += verdict.confidence * weight
                action_counts[action] += 1

        # Step 3: Find winning action
        total_weight = sum(action_scores.values()) or 1.0
        best_action: SignalAction = "NEUTRAL"
        best_score = 0.0

        for action, score in action_scores.items():
            normalized = score / total_weight
            if normalized > best_score:
                best_score = normalized
                best_action = action

        # Detect 50/50 tie between BUY and SELL before applying thresholds
        buy_score = action_scores.get("BUY", 0.0) / total_weight
        sell_score = action_scores.get("SELL", 0.0) / total_weight
        is_tie = buy_score > 0 and sell_score > 0 and abs(buy_score - sell_score) < 1e-9

        # Step 4: Check thresholds
        if best_score < self.confidence_threshold:
            logger.info(
                "Consensus confidence %.2f below threshold %.2f — NEUTRAL",
                best_score,
                self.confidence_threshold,
            )
            best_action = "NEUTRAL"
            best_score = 0.5 if is_tie else 0.0

        if action_counts.get(best_action, 0) < self.min_agreement:
            logger.info(
                "Only %d roles agree on %s (need %d) — NEUTRAL",
                action_counts.get(best_action, 0),
                best_action,
                self.min_agreement,
            )
            if best_action != "NEUTRAL":
                best_action = "NEUTRAL"
                best_score = 0.5 if is_tie else 0.0

        # Build reasoning summary
        reasoning_parts = [f"{v.role.value}: {v.action} (conf={v.confidence:.2f})" for v in verdicts]
        reasoning = f"Consensus: {best_action} | " + " | ".join(reasoning_parts)

        return ConsensusDecision(
            final_action=best_action,
            final_confidence=best_score,
            verdicts=verdicts,
            reasoning=reasoning,
        )
