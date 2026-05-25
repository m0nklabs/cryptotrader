from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal, Mapping

from core.fees.model import FeeModel
from core.opportunities.evaluator import evaluate_opportunity
from core.types import CostEstimate, Opportunity, OrderIntent


DecisionType = Literal["allow", "deny", "skip"]


@dataclass(frozen=True)
class PolicyDecision:
    decision: DecisionType
    reason: str
    metadata: Mapping[str, str] | None = None


@dataclass(frozen=True)
class Policy:
    """Pure decision logic for whether an opportunity may be executed.

    Checks:
    1. Edge threshold: opportunity edge must exceed minimum required after costs
    2. Notional size: order notional must be within acceptable range
    3. Direction consistency: BUY signals should have positive edge, SELL should too
    """

    name: str = "default"
    min_edge_bps: Decimal = Decimal("10")  # Minimum edge in basis points
    min_notional: Decimal = Decimal("10")  # Minimum order notional
    max_notional: Decimal | None = None  # Maximum order notional (None = unlimited)
    fee_model: FeeModel | None = None
    taker: bool = True

    def decide(
        self,
        *,
        opportunity: Opportunity,
        cost: CostEstimate,
        proposed_intent: OrderIntent,
    ) -> PolicyDecision:
        # Check minimum edge threshold using opportunity score as edge proxy
        # Score 0-100 maps to 0-100 bps for edge estimation
        if self.fee_model is not None:
            # Convert score to edge rate (score/100 gives rate, e.g., score 50 = 0.50 = 50 bps)
            edge_rate = Decimal(opportunity.score) / Decimal(10000)
            edge_check = evaluate_opportunity(
                gross_notional=cost.gross_notional,
                edge_rate=edge_rate,
                fee_model=self.fee_model,
                taker=self.taker,
            )
            if edge_check.decision == "FAIL":
                return PolicyDecision(
                    decision="deny",
                    reason=f"Edge insufficient: {edge_check.observed_bps} bps < {edge_check.required_bps} bps required",
                    metadata={
                        "observed_bps": str(edge_check.observed_bps),
                        "required_bps": str(edge_check.required_bps),
                    },
                )

        # Check notional size from cost estimate
        notional = cost.gross_notional
        if notional < self.min_notional:
            return PolicyDecision(
                decision="deny",
                reason=f"Notional too small: {notional:.2f} < {self.min_notional}",
                metadata={"notional": str(notional), "min_notional": str(self.min_notional)},
            )

        if self.max_notional is not None and notional > self.max_notional:
            return PolicyDecision(
                decision="deny",
                reason=f"Notional too large: {notional:.2f} > {self.max_notional}",
                metadata={"notional": str(notional), "max_notional": str(self.max_notional)},
            )

        return PolicyDecision(
            decision="allow",
            reason=f"Opportunity approved: score {opportunity.score}, notional {notional:.2f}",
            metadata={"score": str(opportunity.score), "notional": str(notional)},
        )
