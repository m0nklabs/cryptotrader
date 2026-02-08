"""Consensus engine — weighted voting across agent roles.

Aggregates individual RoleVerdicts into a single ConsensusDecision.
Supports:
- Weighted confidence voting
- Hard VETO (any role VETO blocks the trade)
- Soft VETO (reduces confidence)
- Confidence calibration with historical accuracy
- Agreement multiplier for unanimous votes
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

# Confidence boost when all roles agree (multiplicative)
DEFAULT_AGREEMENT_MULTIPLIER = 1.15

# Minimum sample size before calibration kicks in
DEFAULT_MIN_CALIBRATION_SAMPLES = 10


class ConsensusEngine:
    """Weighted voting consensus engine.

    Algorithm:
    1. Check for any VETO — if found, handle according to veto_mode.
    2. Compute weighted score per action (BUY, SELL, NEUTRAL).
    3. Apply confidence calibration based on historical accuracy (if enabled).
    4. Winning action must exceed confidence threshold.
    5. Must have at least ``min_agreement`` roles agreeing.
    6. Apply agreement multiplier if all roles agree.
    """

    def __init__(
        self,
        confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
        min_agreement: int = DEFAULT_MIN_AGREEMENT,
        veto_mode: str = "hard",  # "hard" or "soft"
        agreement_multiplier: float = DEFAULT_AGREEMENT_MULTIPLIER,
        enable_calibration: bool = False,
        min_calibration_samples: int = DEFAULT_MIN_CALIBRATION_SAMPLES,
    ) -> None:
        self.confidence_threshold = confidence_threshold
        self.min_agreement = min_agreement
        self.veto_mode = veto_mode
        self.agreement_multiplier = agreement_multiplier
        self.enable_calibration = enable_calibration
        self.min_calibration_samples = min_calibration_samples

        # Historical accuracy tracking per role (role_name -> accuracy)
        # In production, this would be loaded from database
        self._role_accuracy: dict[str, float] = {}
        self._role_sample_counts: dict[str, int] = {}

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

            if self.veto_mode == "hard":
                # Hard VETO: override majority, final action is NEUTRAL
                return ConsensusDecision(
                    final_action="NEUTRAL",
                    final_confidence=0.0,
                    verdicts=verdicts,
                    reasoning=f"VETOED (hard) by {vetoer.role.value}: {vetoer.reasoning}",
                    vetoed_by=vetoer.role,
                )
            else:
                # Soft VETO: reduce confidence but continue evaluation
                # Remove VETO from verdicts and apply penalty later
                logger.info("Soft VETO from %s, reducing confidence", vetoer.role.value)
                non_veto_verdicts = [v for v in verdicts if v.action != "VETO"]
                if not non_veto_verdicts:
                    # All VETOs, treat as hard
                    return ConsensusDecision(
                        final_action="NEUTRAL",
                        final_confidence=0.0,
                        verdicts=verdicts,
                        reasoning=f"All roles VETOED, treated as hard VETO. First: {vetoer.reasoning}",
                        vetoed_by=vetoer.role,
                    )
                # Continue with non-VETO verdicts but track the veto
                verdicts_to_process = non_veto_verdicts
                soft_veto_penalty = 0.5  # Reduce final confidence by 50%
        else:
            verdicts_to_process = verdicts
            soft_veto_penalty = 1.0

        # Step 2: Weighted scoring with optional calibration
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

        for verdict in verdicts_to_process:
            role = RoleRegistry.get(verdict.role)
            weight = role.weight if role else 1.0

            # Apply calibration if enabled
            if self.enable_calibration:
                weight = self._apply_calibration(verdict.role.value, weight)

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

        # Step 4: Check for unanimous agreement and boost confidence
        if len(verdicts_to_process) >= 2:
            unique_actions = set(v.action for v in verdicts_to_process)
            if len(unique_actions) == 1 and best_action != "NEUTRAL":
                # All roles agree on non-NEUTRAL action
                best_score = min(1.0, best_score * self.agreement_multiplier)
                logger.info(
                    "Unanimous agreement on %s — boosting confidence to %.2f",
                    best_action,
                    best_score,
                )

        # Step 5: Apply soft VETO penalty if applicable
        if soft_veto_penalty < 1.0:
            best_score *= soft_veto_penalty
            logger.info("Applied soft VETO penalty, confidence now %.2f", best_score)

        # Step 6: Check thresholds
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

        # Build reasoning summary with decision chain
        reasoning_parts = []
        for v in verdicts:
            role_str = f"{v.role.value}: {v.action} (conf={v.confidence:.2f})"
            if v.reasoning:
                # Truncate long reasoning to keep summary readable
                reason_snippet = v.reasoning[:100] + "..." if len(v.reasoning) > 100 else v.reasoning
                role_str += f" [{reason_snippet}]"
            reasoning_parts.append(role_str)

        reasoning = f"Consensus: {best_action} (conf={best_score:.2f}) | " + " | ".join(reasoning_parts)

        # Include soft VETO info if applicable
        if veto_verdicts and self.veto_mode == "soft":
            reasoning += f" | Soft VETO applied by {veto_verdicts[0].role.value}"

        return ConsensusDecision(
            final_action=best_action,
            final_confidence=best_score,
            verdicts=verdicts,  # Include ALL verdicts, even VETOs
            reasoning=reasoning,
            vetoed_by=veto_verdicts[0].role if veto_verdicts and self.veto_mode == "hard" else None,
        )

    def _apply_calibration(self, role_name: str, base_weight: float) -> float:
        """Apply confidence calibration based on historical accuracy.

        Args:
            role_name: Name of the role
            base_weight: Base weight from role config

        Returns:
            Calibrated weight adjusted for historical accuracy
        """
        # Check if we have enough samples for this role
        sample_count = self._role_sample_counts.get(role_name, 0)
        if sample_count < self.min_calibration_samples:
            return base_weight

        # Get historical accuracy (default to 0.5 if unknown)
        accuracy = self._role_accuracy.get(role_name, 0.5)

        # Bayesian weight adjustment:
        # - accuracy > 0.5 → increase weight
        # - accuracy < 0.5 → decrease weight
        # - accuracy = 0.5 → no change
        calibration_factor = accuracy / 0.5  # Range: 0.0 to 2.0
        calibrated = base_weight * calibration_factor

        logger.debug(
            "Role %s calibration: %.1f%% accuracy → weight %.2f -> %.2f",
            role_name,
            accuracy * 100,
            base_weight,
            calibrated,
        )

        return calibrated

    def update_role_accuracy(self, role_name: str, was_correct: bool) -> None:
        """Update historical accuracy for a role (for calibration).

        This should be called after each trade outcome is known.
        In production, this would persist to database.

        Args:
            role_name: Name of the role
            was_correct: Whether the role's verdict was correct
        """
        current_accuracy = self._role_accuracy.get(role_name, 0.5)
        current_count = self._role_sample_counts.get(role_name, 0)

        # Exponential moving average with more weight on recent samples
        alpha = 0.1  # Learning rate
        new_accuracy = (1 - alpha) * current_accuracy + alpha * (1.0 if was_correct else 0.0)

        self._role_accuracy[role_name] = new_accuracy
        self._role_sample_counts[role_name] = current_count + 1

        logger.info(
            "Updated %s accuracy: %.1f%% -> %.1f%% (n=%d)",
            role_name,
            current_accuracy * 100,
            new_accuracy * 100,
            self._role_sample_counts[role_name],
        )

    def get_role_accuracy(self, role_name: str) -> tuple[float, int]:
        """Get accuracy stats for a role.

        Returns:
            Tuple of (accuracy, sample_count)
        """
        return (
            self._role_accuracy.get(role_name, 0.5),
            self._role_sample_counts.get(role_name, 0),
        )
