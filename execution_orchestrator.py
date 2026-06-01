"""Execution orchestrator — bridges AI consensus decisions to paper-order execution.

Converts ConsensusDecision into paper-order intents, applies risk gates
(VETO, budget, exposure, risk limits), and audit-logs the full decision path.

Paper-only: does not place live exchange orders.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Optional

from core.ai.types import (
    ConsensusDecision,
    RiskDecision,
    RiskGateResult,
    SignalAction,
)
from core.execution.paper import PaperExecutor, PaperOrder
from core.risk.limits import ExposureChecker, ExposureLimits
from core.risk.sizing import PositionSize, calculate_position_size

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Risk gate definitions
# ---------------------------------------------------------------------------


class GateName(str, Enum):
    VETO = "veto"
    BUDGET = "budget"
    EXPOSURE = "exposure"
    RISK_LIMIT = "risk_limit"
    POSITION_SIZE = "position_size"


@dataclass
class GateCheckResult:
    """Result of a single gate check."""

    gate: GateName
    passed: bool
    reason: str = ""
    details: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Execution orchestrator
# ---------------------------------------------------------------------------


class ExecutionOrchestrator:
    """Bridges AI consensus decisions to paper-order execution with risk gates.

    Workflow:
    1. Receive a ConsensusDecision from the AI multi-brain.
    2. Apply risk gates in order: VETO → Budget → Exposure → Risk limits.
    3. If all gates pass, create a paper-order intent and execute.
    4. Persist the full decision path (AI decision → risk decision → paper order).
    5. Audit-log every gate check and the final outcome.

    Paper-only: never places live exchange orders.
    """

    def __init__(
        self,
        paper_executor: Optional[PaperExecutor] = None,
        exposure_limits: Optional[ExposureLimits] = None,
        position_size_config: Optional[PositionSize] = None,
        daily_budget_usd: float = 100.0,
        monthly_budget_usd: float = 2000.0,
        max_position_size_per_symbol: Optional[Decimal] = None,
        max_total_exposure: Optional[Decimal] = None,
        max_positions: int = 10,
        confidence_threshold: float = 0.6,
        veto_mode: str = "hard",
    ) -> None:
        self.paper_executor = paper_executor or PaperExecutor()
        self.exposure_checker = ExposureChecker(
            limits=exposure_limits
            or ExposureLimits(
                max_position_size_per_symbol=max_position_size_per_symbol,
                max_total_exposure=max_total_exposure,
                max_positions=max_positions,
            )
        )
        self.position_size_config = position_size_config or PositionSize(
            method="kelly",
            win_rate=Decimal("0.55"),
            avg_win=Decimal("0.05"),
            avg_loss=Decimal("0.02"),
            kelly_fraction=Decimal("0.5"),
        )
        self.daily_budget_usd = daily_budget_usd
        self.monthly_budget_usd = monthly_budget_usd
        self.confidence_threshold = confidence_threshold
        self.veto_mode = veto_mode

        # Budget tracking (in-memory; persist to DB in production)
        self._daily_spend_usd: float = 0.0
        self._monthly_spend_usd: float = 0.0
        self._trade_count_today: int = 0

        # Decision path audit log
        self._audit_log: list[dict[str, Any]] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def evaluate_and_execute(
        self,
        consensus: ConsensusDecision,
        symbol: str,
        market_price: Decimal,
        portfolio_value: Decimal = Decimal("10000"),
        current_exposure: Decimal = Decimal("0"),
        current_positions: int = 0,
        timeframe: str = "1h",
    ) -> RiskDecision:
        """Evaluate a consensus decision against all risk gates and execute if all pass.

        Args:
            consensus: The aggregated AI consensus decision.
            symbol: Trading pair (e.g. "BTCUSD").
            market_price: Current market price for the symbol.
            portfolio_value: Total portfolio value in quote currency.
            current_exposure: Current total exposure across all positions.
            current_positions: Number of currently open positions.
            timeframe: Timeframe of the evaluation.

        Returns:
            RiskDecision with gate results and execution outcome.
        """
        start_time = datetime.now(timezone.utc)
        gate_results: list[GateCheckResult] = []

        # Step 1: VETO gate
        veto_result = self._check_veto_gate(consensus, symbol)
        gate_results.append(veto_result)
        if not veto_result.passed:
            return self._build_result(
                start_time=start_time,
                symbol=symbol,
                timeframe=timeframe,
                consensus=consensus,
                gate_results=gate_results,
                action="REJECTED",
                reason=veto_result.reason,
                market_price=market_price,
                portfolio_value=portfolio_value,
            )

        # Step 2: Budget gate
        budget_result = self._check_budget_gate(
            symbol=symbol,
            market_price=market_price,
            portfolio_value=portfolio_value,
        )
        gate_results.append(budget_result)
        if not budget_result.passed:
            return self._build_result(
                start_time=start_time,
                symbol=symbol,
                timeframe=timeframe,
                consensus=consensus,
                gate_results=gate_results,
                action="REJECTED",
                reason=budget_result.reason,
                market_price=market_price,
                portfolio_value=portfolio_value,
            )

        # Step 3: Exposure gate
        # Calculate proposed position size
        position_size = self._calculate_position_size(
            market_price=market_price,
            portfolio_value=portfolio_value,
            confidence=consensus.final_confidence,
        )
        position_value = market_price * position_size

        exposure_result = self._check_exposure_gate(
            symbol=symbol,
            position_value=position_value,
            current_exposure=current_exposure,
            portfolio_value=portfolio_value,
            current_positions=current_positions,
        )
        gate_results.append(exposure_result)
        if not exposure_result.passed:
            return self._build_result(
                start_time=start_time,
                symbol=symbol,
                timeframe=timeframe,
                consensus=consensus,
                gate_results=gate_results,
                action="REJECTED",
                reason=exposure_result.reason,
                market_price=market_price,
                portfolio_value=portfolio_value,
            )

        # Step 4: Risk limit gate
        risk_result = self._check_risk_limit_gate(
            symbol=symbol,
            market_price=market_price,
            position_size=position_size,
            portfolio_value=portfolio_value,
        )
        gate_results.append(risk_result)
        if not risk_result.passed:
            return self._build_result(
                start_time=start_time,
                symbol=symbol,
                timeframe=timeframe,
                consensus=consensus,
                gate_results=gate_results,
                action="REJECTED",
                reason=risk_result.reason,
                market_price=market_price,
                portfolio_value=portfolio_value,
            )

        # All gates passed — execute paper order
        order = self._execute_paper_order(
            symbol=symbol,
            side=consensus.final_action,
            qty=position_size,
            market_price=market_price,
        )

        # Update budget tracking
        self._update_budget(consensus)

        return self._build_result(
            start_time=start_time,
            symbol=symbol,
            timeframe=timeframe,
            consensus=consensus,
            gate_results=gate_results,
            action="EXECUTED",
            reason="All gates passed",
            paper_order=order,
            market_price=market_price,
            portfolio_value=portfolio_value,
            position_size=position_size,
            position_value=position_value,
        )

    def get_decision_path(self, symbol: str) -> list[dict[str, Any]]:
        """Get the audit log for a specific symbol."""
        return [entry for entry in self._audit_log if entry.get("symbol") == symbol]

    def get_audit_log(self) -> list[dict[str, Any]]:
        """Get the full audit log."""
        return list(self._audit_log)

    def reset_budget(self) -> None:
        """Reset daily and monthly budget tracking."""
        self._daily_spend_usd = 0.0
        self._monthly_spend_usd = 0.0
        self._trade_count_today = 0

    # ------------------------------------------------------------------
    # Gate checks
    # ------------------------------------------------------------------

    def _check_veto_gate(
        self,
        consensus: ConsensusDecision,
        symbol: str,
    ) -> GateCheckResult:
        """Check if any role has issued a hard VETO."""
        if consensus.vetoed_by is not None:
            reason = f"VETO by {consensus.vetoed_by.value}: {consensus.reasoning}"
            return GateCheckResult(
                gate=GateName.VETO,
                passed=False,
                reason=reason,
                details={"vetoed_by": consensus.vetoed_by.value},
            )

        # Only BUY/SELL are executable actions; anything else is rejected early.
        if consensus.final_action not in ("BUY", "SELL"):
            return GateCheckResult(
                gate=GateName.VETO,
                passed=False,
                reason=(
                    f"Consensus action not executable: {consensus.final_action} "
                    f"(conf={consensus.final_confidence:.2f})"
                ),
                details={
                    "final_action": consensus.final_action,
                    "confidence": consensus.final_confidence,
                },
            )

        if consensus.final_confidence < self.confidence_threshold:
            return GateCheckResult(
                gate=GateName.VETO,
                passed=False,
                reason=(
                    f"Confidence {consensus.final_confidence:.2f} below threshold "
                    f"{self.confidence_threshold:.2f} for {consensus.final_action}"
                ),
                details={
                    "final_action": consensus.final_action,
                    "confidence": consensus.final_confidence,
                    "confidence_threshold": self.confidence_threshold,
                },
            )

        return GateCheckResult(
            gate=GateName.VETO,
            passed=True,
            reason="No veto",
            details={"vetoed_by": consensus.vetoed_by.value if consensus.vetoed_by else None},
        )

    def _check_budget_gate(
        self,
        symbol: str,
        market_price: Decimal,
        portfolio_value: Decimal,
    ) -> GateCheckResult:
        """Check if we're within budget limits."""
        # Use a fixed AI cost estimate per trade (realistic for LLM calls)
        estimated_cost = 0.05  # ~$0.05 per AI evaluation

        if self._daily_spend_usd + estimated_cost > self.daily_budget_usd:
            return GateCheckResult(
                gate=GateName.BUDGET,
                passed=False,
                reason=f"Daily budget exceeded: ${self._daily_spend_usd:.2f}/${self.daily_budget_usd:.2f}",
                details={
                    "daily_spend": self._daily_spend_usd,
                    "daily_limit": self.daily_budget_usd,
                    "estimated_cost": estimated_cost,
                },
            )

        if self._monthly_spend_usd + estimated_cost > self.monthly_budget_usd:
            return GateCheckResult(
                gate=GateName.BUDGET,
                passed=False,
                reason=f"Monthly budget exceeded: ${self._monthly_spend_usd:.2f}/${self.monthly_budget_usd:.2f}",
                details={
                    "monthly_spend": self._monthly_spend_usd,
                    "monthly_limit": self.monthly_budget_usd,
                    "estimated_cost": estimated_cost,
                },
            )

        return GateCheckResult(
            gate=GateName.BUDGET,
            passed=True,
            reason="Within budget",
            details={
                "daily_spend": self._daily_spend_usd,
                "daily_limit": self.daily_budget_usd,
                "monthly_spend": self._monthly_spend_usd,
                "monthly_limit": self.monthly_budget_usd,
                "estimated_cost": estimated_cost,
            },
        )

    def _check_exposure_gate(
        self,
        symbol: str,
        position_value: Decimal,
        current_exposure: Decimal,
        portfolio_value: Decimal,
        current_positions: int,
    ) -> GateCheckResult:
        """Check exposure limits (position size, total exposure, position count)."""
        all_passed, reasons = self.exposure_checker.check_all(
            symbol=symbol,
            position_value=position_value,
            current_exposure=current_exposure,
            portfolio_value=portfolio_value,
            current_positions=current_positions,
        )

        if not all_passed:
            return GateCheckResult(
                gate=GateName.EXPOSURE,
                passed=False,
                reason="; ".join(reasons),
                details={"reasons": reasons, "position_value": str(position_value)},
            )

        return GateCheckResult(
            gate=GateName.EXPOSURE,
            passed=True,
            reason="Exposure within limits",
            details={
                "position_value": str(position_value),
                "current_exposure": str(current_exposure),
                "portfolio_value": str(portfolio_value),
                "current_positions": current_positions,
            },
        )

    def _check_risk_limit_gate(
        self,
        symbol: str,
        market_price: Decimal,
        position_size: Decimal,
        portfolio_value: Decimal,
    ) -> GateCheckResult:
        """Check risk limits (position sizing, ATR-based, etc.)."""
        # Use a fixed 2% downside stop for the simplified sizing estimate.
        stop_loss = market_price * Decimal("0.98")  # 2% stop loss

        try:
            calc_size = calculate_position_size(
                config=self.position_size_config,
                portfolio_value=portfolio_value,
                entry_price=market_price,
                stop_loss_price=stop_loss,
            )

            # Check if calculated position size is reasonable
            max_position = self.exposure_checker.limits.max_position_size_per_symbol
            if max_position is not None and calc_size > max_position:
                return GateCheckResult(
                    gate=GateName.RISK_LIMIT,
                    passed=False,
                    reason=f"Calculated position size {calc_size} exceeds max {max_position}",
                    details={
                        "calculated_size": str(calc_size),
                        "max_size": str(max_position),
                    },
                )

            return GateCheckResult(
                gate=GateName.RISK_LIMIT,
                passed=True,
                reason="Risk limits within bounds",
                details={
                    "calculated_size": str(calc_size),
                    "stop_loss": str(stop_loss),
                    "method": self.position_size_config.method,
                },
            )
        except ValueError as e:
            return GateCheckResult(
                gate=GateName.RISK_LIMIT,
                passed=False,
                reason=f"Risk calculation error: {e}",
                details={"error": str(e)},
            )

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def _calculate_position_size(
        self,
        market_price: Decimal,
        portfolio_value: Decimal,
        confidence: float,
    ) -> Decimal:
        """Calculate position size based on confidence and portfolio value."""
        # Kelly criterion with confidence weighting
        win_rate = self.position_size_config.win_rate or Decimal("0.55")
        avg_win = self.position_size_config.avg_win or Decimal("0.05")
        avg_loss = self.position_size_config.avg_loss or Decimal("0.02")

        # Kelly formula: f* = (p * b - q) / b
        p = float(win_rate)
        q = 1.0 - p
        b = float(avg_win) / float(avg_loss) if float(avg_loss) > 0 else 1.0
        kelly = (p * b - q) / b if b > 0 else 0.0

        # Apply confidence weighting
        kelly *= max(confidence, 0.1)

        # Apply kelly_fraction
        kelly *= float(self.position_size_config.kelly_fraction or Decimal("0.5"))

        # Cap at 25% of portfolio
        kelly = min(kelly, 0.25)

        # Convert to position size in units
        portfolio_percent = Decimal(str(kelly))
        risk_amount = portfolio_value * portfolio_percent
        risk_per_unit = float(market_price) * 0.02  # 2% risk per unit (stop loss distance)

        if risk_per_unit == 0:
            return Decimal("1.0")

        return (risk_amount / Decimal(str(risk_per_unit))).quantize(Decimal("0.00000001"))

    def _execute_paper_order(
        self,
        symbol: str,
        side: SignalAction,
        qty: Decimal,
        market_price: Decimal,
    ) -> PaperOrder:
        """Execute a paper order based on the consensus decision."""
        if side in ("BUY", "SELL"):
            order = self.paper_executor.execute_paper_order(
                symbol=symbol,
                side=side,
                qty=qty,
                order_type="market",
                market_price=market_price,
            )
            logger.info(
                "Paper order executed: %s %s %s %s @ %s (status=%s)",
                side,
                qty,
                symbol,
                "@",
                market_price,
                order.status,
            )
            return order
        else:
            logger.warning(
                "Unknown signal action %s for %s, treating as HOLD",
                side,
                symbol,
            )
            raise ValueError(f"Cannot execute order with action {side}")

    def _update_budget(self, consensus: ConsensusDecision) -> None:
        """Update budget tracking after a trade.

        Uses a fixed estimated cost per trade since the consensus
        total_cost_usd may be 0 for synthetic decisions.
        """
        trade_cost = 0.05  # Fixed cost per trade
        self._daily_spend_usd += trade_cost
        self._monthly_spend_usd += trade_cost
        self._trade_count_today += 1

    # ------------------------------------------------------------------
    # Result building
    # ------------------------------------------------------------------

    def _build_result(
        self,
        start_time: datetime,
        symbol: str,
        timeframe: str,
        consensus: ConsensusDecision,
        gate_results: list[GateCheckResult],
        action: str,
        reason: str,
        paper_order: Optional[PaperOrder] = None,
        market_price: Optional[Decimal] = None,
        portfolio_value: Optional[Decimal] = None,
        position_size: Optional[Decimal] = None,
        position_value: Optional[Decimal] = None,
    ) -> RiskDecision:
        """Build a RiskDecision from gate results and execution outcome."""
        latency_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
        normalized_gate_results = [
            RiskGateResult(
                gate=gr.gate.value,
                passed=gr.passed,
                reason=gr.reason,
                details=gr.details,
            )
            for gr in gate_results
        ]

        decision = RiskDecision(
            symbol=symbol,
            timeframe=timeframe,
            final_action=consensus.final_action,
            final_confidence=consensus.final_confidence,
            gate_results=normalized_gate_results,
            action=action,
            reason=reason,
            paper_order=paper_order,
            market_price=market_price,
            portfolio_value=portfolio_value,
            position_size=position_size,
            position_value=position_value,
            latency_ms=latency_ms,
            timestamp=start_time,
            verdicts=consensus.verdicts,
            vetoed_by=consensus.vetoed_by,
            reasoning=consensus.reasoning,
        )

        # Add to audit log
        audit_entry = {
            "symbol": symbol,
            "action": action,
            "reason": reason,
            "gate_results": [
                {
                    "gate": gr.gate,
                    "passed": gr.passed,
                    "reason": gr.reason,
                    "details": gr.details,
                }
                for gr in normalized_gate_results
            ],
            "paper_order_id": paper_order.order_id if paper_order else None,
            "market_price": str(market_price) if market_price else None,
            "portfolio_value": str(portfolio_value) if portfolio_value else None,
            "position_size": str(position_size) if position_size else None,
            "position_value": str(position_value) if position_value else None,
            "latency_ms": round(latency_ms, 2),
            "timestamp": start_time.isoformat(),
        }
        self._audit_log.append(audit_entry)

        logger.info(
            "Risk decision for %s: %s (%s) — %s",
            symbol,
            action,
            reason,
            f"paper_order={paper_order.order_id}" if paper_order else "no order",
        )

        return decision
