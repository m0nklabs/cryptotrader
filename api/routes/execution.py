"""Execution API routes — decision path and paper-order endpoints.

Provides endpoints for:
- Evaluating AI consensus decisions against risk gates
- Creating paper-order intents
- Inspecting the full decision path (audit trail)
"""

from __future__ import annotations

import logging
from decimal import Decimal as DecimalType
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from core.ai.types import ConsensusDecision, RoleName, RoleVerdict, SignalAction

from execution_orchestrator import ExecutionOrchestrator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/execution", tags=["execution"])

# Global orchestrator instance
_orchestrator: ExecutionOrchestrator | None = None

_VALID_SIGNAL_ACTIONS: set[str] = {"BUY", "SELL", "NEUTRAL", "VETO"}


def get_orchestrator() -> ExecutionOrchestrator:
    """Get or create the global execution orchestrator."""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = ExecutionOrchestrator()
    return _orchestrator


def _role_from_payload(value: Any) -> RoleName:
    """Return a valid role name from request payload data."""
    try:
        return RoleName(str(value or RoleName.SCREENER.value))
    except ValueError:
        return RoleName.SCREENER


def _action_from_payload(value: Any) -> SignalAction:
    """Return a valid signal action from request payload data."""
    action = str(value or "NEUTRAL").upper()
    if action in _VALID_SIGNAL_ACTIONS:
        return action  # type: ignore[return-value]
    return "NEUTRAL"


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class EvaluateRequest(BaseModel):
    """Request to evaluate a consensus decision against risk gates."""

    symbol: str = Field(..., description="Trading pair, e.g. BTCUSD")
    final_action: SignalAction = Field(..., description="Consensus action: BUY, SELL, NEUTRAL, VETO")
    final_confidence: float = Field(..., ge=0.0, le=1.0, description="Consensus confidence 0-1")
    market_price: float = Field(..., gt=0, description="Current market price")
    portfolio_value: float = 10000.0
    current_exposure: float = 0.0
    current_positions: int = 0
    timeframe: str = "1h"
    vetoed_by: RoleName | None = None
    reasoning: str = ""
    verdicts: list[dict[str, Any]] = Field(default_factory=list)


class GateResultResponse(BaseModel):
    """Single gate check result."""

    gate: str
    passed: bool
    reason: str
    details: dict[str, Any]


class RiskDecisionResponse(BaseModel):
    """Complete risk-gate evaluation result."""

    symbol: str
    timeframe: str
    final_action: SignalAction
    final_confidence: float
    gate_results: list[GateResultResponse]
    action: str  # EXECUTED or REJECTED
    reason: str
    paper_order_id: int | None = None
    market_price: float | None = None
    portfolio_value: float | None = None
    position_size: float | None = None
    position_value: float | None = None
    latency_ms: float = 0.0
    vetoed_by: str | None = None
    reasoning: str = ""


class AuditEntryResponse(BaseModel):
    """Single audit log entry."""

    symbol: str
    action: str
    reason: str
    gate_results: list[dict[str, Any]]
    paper_order_id: int | None = None
    market_price: float | None = None
    portfolio_value: float | None = None
    position_size: float | None = None
    position_value: float | None = None
    latency_ms: float
    timestamp: str


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------


@router.post("/evaluate", response_model=RiskDecisionResponse)
async def evaluate_consensus(req: EvaluateRequest) -> RiskDecisionResponse:
    """Evaluate a consensus decision against all risk gates.

    Takes an AI consensus decision, runs it through the risk gates
    (VETO, Budget, Exposure, Risk limits), and either executes a
    paper order or rejects with the reason.
    """
    orch = get_orchestrator()

    # Reconstruct the ConsensusDecision from the request
    consensus = ConsensusDecision(
        final_action=req.final_action,
        final_confidence=req.final_confidence,
        verdicts=[
            RoleVerdict(
                role=_role_from_payload(v.get("role")),
                action=_action_from_payload(v.get("action")),
                confidence=float(v.get("confidence", 0.5)),
                reasoning=str(v.get("reasoning", "")),
            )
            for v in req.verdicts
        ],
        reasoning=req.reasoning,
        vetoed_by=req.vetoed_by,
    )

    result = orch.evaluate_and_execute(
        consensus=consensus,
        symbol=req.symbol,
        market_price=DecimalType(str(req.market_price)),
        portfolio_value=DecimalType(str(req.portfolio_value)),
        current_exposure=DecimalType(str(req.current_exposure)),
        current_positions=req.current_positions,
        timeframe=req.timeframe,
    )

    return RiskDecisionResponse(
        symbol=result.symbol,
        timeframe=result.timeframe,
        final_action=result.final_action,
        final_confidence=result.final_confidence,
        gate_results=[
            GateResultResponse(
                gate=gr.gate.value if hasattr(gr.gate, "value") else str(gr.gate),
                passed=gr.passed,
                reason=gr.reason,
                details=gr.details,
            )
            for gr in result.gate_results
        ],
        action=result.action,
        reason=result.reason,
        paper_order_id=result.paper_order.order_id if result.paper_order else None,
        market_price=float(result.market_price) if result.market_price else None,
        portfolio_value=float(result.portfolio_value) if result.portfolio_value else None,
        position_size=float(result.position_size) if result.position_size else None,
        position_value=float(result.position_value) if result.position_value else None,
        latency_ms=result.latency_ms,
        vetoed_by=result.vetoed_by.value if result.vetoed_by else None,
        reasoning=result.reasoning,
    )


@router.post("/paper-order", response_model=RiskDecisionResponse)
async def create_paper_order(req: EvaluateRequest) -> RiskDecisionResponse:
    """Create a paper order from a consensus decision.

    Convenience endpoint that evaluates and executes in one call.
    """
    return await evaluate_consensus(req)


@router.get("/decision-path/{symbol}", response_model=list[AuditEntryResponse])
async def get_decision_path(symbol: str) -> list[AuditEntryResponse]:
    """Get the full decision path (audit trail) for a symbol."""
    orch = get_orchestrator()
    entries = orch.get_decision_path(symbol)

    return [
        AuditEntryResponse(
            symbol=e.get("symbol", symbol),
            action=e.get("action", "REJECTED"),
            reason=e.get("reason", ""),
            gate_results=e.get("gate_results", []),
            paper_order_id=e.get("paper_order_id"),
            market_price=e.get("market_price"),
            portfolio_value=e.get("portfolio_value"),
            position_size=e.get("position_size"),
            position_value=e.get("position_value"),
            latency_ms=e.get("latency_ms", 0.0),
            timestamp=e.get("timestamp", ""),
        )
        for e in entries
    ]


@router.get("/decision-path", response_model=list[AuditEntryResponse])
async def get_all_decision_paths() -> list[AuditEntryResponse]:
    """Get the full audit log for all symbols."""
    orch = get_orchestrator()
    entries = orch.get_audit_log()

    return [
        AuditEntryResponse(
            symbol=e.get("symbol", ""),
            action=e.get("action", "REJECTED"),
            reason=e.get("reason", ""),
            gate_results=e.get("gate_results", []),
            paper_order_id=e.get("paper_order_id"),
            market_price=e.get("market_price"),
            portfolio_value=e.get("portfolio_value"),
            position_size=e.get("position_size"),
            position_value=e.get("position_value"),
            latency_ms=e.get("latency_ms", 0.0),
            timestamp=e.get("timestamp", ""),
        )
        for e in entries
    ]


@router.get("/paper-summary")
async def get_paper_summary() -> dict[str, Any]:
    """Get a comprehensive paper trading summary."""
    orch = get_orchestrator()
    executor = orch.paper_executor

    summary = executor.get_paper_summary()
    summary["budget"] = {
        "daily_spend_usd": orch._daily_spend_usd,
        "daily_limit_usd": orch.daily_budget_usd,
        "monthly_spend_usd": orch._monthly_spend_usd,
        "monthly_limit_usd": orch.monthly_budget_usd,
        "trade_count_today": orch._trade_count_today,
    }
    summary["audit_entries"] = len(orch.get_audit_log())

    return summary
