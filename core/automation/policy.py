from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Mapping, Optional

from core.types import CostEstimate, Opportunity, OrderIntent


DecisionType = Literal["allow", "deny", "skip"]


@dataclass(frozen=True)
class PolicyDecision:
    decision: DecisionType
    reason: str
    metadata: Mapping[str, str] | None = None


@dataclass(frozen=True)
class Policy:
    """Pure decision logic for whether an opportunity may be executed."""

    name: str = "default"

    def decide(
        self,
        *,
        opportunity: Opportunity,
        cost: CostEstimate,
        proposed_intent: OrderIntent,
    ) -> PolicyDecision:
        # Placeholder: implement edge threshold checks and gating rules.
        return PolicyDecision(decision="skip", reason="policy not implemented")
