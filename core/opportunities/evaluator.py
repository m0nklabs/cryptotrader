"""Opportunity evaluator: determines if an opportunity clears minimum edge threshold after costs.

This module provides a deterministic, unit-tested evaluator that decides if a trading
opportunity has sufficient edge to cover estimated costs (fees, spread, slippage).

Key features:
- Pure function with no DB access or network calls
- Uses existing FeeModel/CostEstimate to compute minimum edge requirements
- Returns structured decision + detailed reasoning

Usage:
    from decimal import Decimal
    from core.opportunities.evaluator import evaluate_opportunity
    from core.fees.model import FeeModel
    from core.types import FeeBreakdown
    
    fee_model = FeeModel(FeeBreakdown(...))
    result = evaluate_opportunity(
        gross_notional=Decimal("1000"),
        edge_rate=Decimal("0.005"),  # 50 bps
        fee_model=fee_model,
        taker=True,
    )
    
    if result.decision == "PASS":
        print(f"Opportunity passes: {result.reasons}")
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from core.fees.model import FeeModel
from core.types import CostEstimate

EvaluationDecision = Literal["PASS", "FAIL"]


@dataclass(frozen=True)
class EvaluationResult:
    """Result of opportunity evaluation.
    
    Attributes:
        decision: PASS if opportunity clears threshold, FAIL otherwise
        required_bps: Minimum edge required in basis points
        observed_bps: Observed edge in basis points
        reasons: List of human-readable reason strings
        cost_estimate: Full cost estimate details (optional)
    """
    
    decision: EvaluationDecision
    required_bps: Decimal
    observed_bps: Decimal
    reasons: tuple[str, ...]
    cost_estimate: CostEstimate | None = None


def evaluate_opportunity(
    *,
    gross_notional: Decimal,
    edge_rate: Decimal,
    fee_model: FeeModel,
    taker: bool = True,
    cost_estimate: CostEstimate | None = None,
) -> EvaluationResult:
    """Evaluate if an opportunity has sufficient edge after costs.
    
    This is a pure function with no side effects - it only performs calculations
    and returns a decision with detailed reasoning.
    
    Args:
        gross_notional: Position size in quote currency (must be positive)
        edge_rate: Expected edge as a decimal rate (e.g., 0.005 = 50 bps)
        fee_model: Fee model to use for cost estimation
        taker: True for taker fees, False for maker fees
        cost_estimate: Optional pre-computed cost estimate (if None, will compute)
    
    Returns:
        EvaluationResult with decision (PASS/FAIL), required/observed edge in bps,
        and detailed reason strings
    
    Raises:
        ValueError: If gross_notional <= 0 or edge_rate < 0
    
    Examples:
        >>> from decimal import Decimal
        >>> from core.fees.model import FeeModel
        >>> from core.types import FeeBreakdown
        >>> 
        >>> fee_model = FeeModel(FeeBreakdown(
        ...     currency="USD",
        ...     maker_fee_rate=Decimal("0.001"),
        ...     taker_fee_rate=Decimal("0.002"),
        ...     assumed_spread_bps=10,
        ...     assumed_slippage_bps=5,
        ... ))
        >>> 
        >>> # Pass case: 50 bps edge vs 35 bps required
        >>> result = evaluate_opportunity(
        ...     gross_notional=Decimal("1000"),
        ...     edge_rate=Decimal("0.005"),
        ...     fee_model=fee_model,
        ...     taker=True,
        ... )
        >>> result.decision
        'PASS'
        >>> result.observed_bps
        Decimal('50.00')
        >>> result.required_bps
        Decimal('35.00')
    """
    # Validation
    if gross_notional <= 0:
        raise ValueError(f"gross_notional must be positive, got {gross_notional}")
    if edge_rate < 0:
        raise ValueError(f"edge_rate must be non-negative, got {edge_rate}")
    
    # Compute cost estimate if not provided
    estimate = cost_estimate or fee_model.estimate_cost(
        gross_notional=gross_notional,
        taker=taker,
    )
    
    # Convert edge_rate to basis points
    BPS_IN_PERCENT = Decimal(10_000)
    observed_bps = (edge_rate * BPS_IN_PERCENT).quantize(Decimal("0.01"))
    required_bps = estimate.minimum_edge_bps
    
    # Make decision
    reasons: list[str] = []
    
    if observed_bps >= required_bps:
        decision: EvaluationDecision = "PASS"
        surplus_bps = (observed_bps - required_bps).quantize(Decimal("0.01"))
        reasons.append(
            f"Edge {observed_bps} bps >= required {required_bps} bps (surplus: {surplus_bps} bps)"
        )
        
        # Add cost breakdown context
        reasons.append(
            f"Estimated costs: fees={estimate.estimated_fees} "
            f"spread={estimate.estimated_spread_cost} "
            f"slippage={estimate.estimated_slippage_cost} "
            f"total={estimate.estimated_total_cost} {estimate.fee_currency}"
        )
    else:
        decision = "FAIL"
        deficit_bps = (required_bps - observed_bps).quantize(Decimal("0.01"))
        reasons.append(
            f"Edge {observed_bps} bps < required {required_bps} bps (deficit: {deficit_bps} bps)"
        )
        
        # Add cost breakdown context
        reasons.append(
            f"Estimated costs: fees={estimate.estimated_fees} "
            f"spread={estimate.estimated_spread_cost} "
            f"slippage={estimate.estimated_slippage_cost} "
            f"total={estimate.estimated_total_cost} {estimate.fee_currency}"
        )
    
    return EvaluationResult(
        decision=decision,
        required_bps=required_bps,
        observed_bps=observed_bps,
        reasons=tuple(reasons),
        cost_estimate=estimate,
    )
