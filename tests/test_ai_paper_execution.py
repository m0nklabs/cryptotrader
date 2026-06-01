"""Tests for AI consensus → paper-order execution wiring with risk gates.

Covers:
- Pass: all gates pass, paper order created
- VETO: strategist VETO blocks order creation
- Budget exceeded: daily/monthly budget blocks order
- Risk-limit failure: exposure/position size blocks order
- Audit logging: decision path persisted and inspectable
"""

from __future__ import annotations

import os
import sys
from decimal import Decimal

import pytest

from core.ai.types import ConsensusDecision, RoleName, RoleVerdict
from core.execution.paper import PaperExecutor
from core.risk.limits import ExposureLimits

# Add workspace to path for local imports
workspace = os.environ.get("HERMES_KANBAN_WORKSPACE", os.getcwd())
if workspace not in sys.path:
    sys.path.insert(0, workspace)

from execution_orchestrator import ExecutionOrchestrator, GateName  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def orchestrator():
    """Default execution orchestrator."""
    return ExecutionOrchestrator(
        paper_executor=PaperExecutor(),
        daily_budget_usd=100.0,
        monthly_budget_usd=2000.0,
        max_positions=10,
        confidence_threshold=0.6,
        veto_mode="hard",
    )


@pytest.fixture
def buy_consensus():
    """A typical BUY consensus from the multi-brain."""
    return ConsensusDecision(
        final_action="BUY",
        final_confidence=0.75,
        verdicts=[
            RoleVerdict(
                role=RoleName.SCREENER,
                action="BUY",
                confidence=0.8,
                reasoning="Strong momentum",
            ),
            RoleVerdict(
                role=RoleName.TACTICAL,
                action="BUY",
                confidence=0.9,
                reasoning="Bullish breakout",
            ),
            RoleVerdict(
                role=RoleName.FUNDAMENTAL,
                action="BUY",
                confidence=0.7,
                reasoning="Positive sentiment",
            ),
            RoleVerdict(
                role=RoleName.STRATEGIST,
                action="BUY",
                confidence=0.85,
                reasoning="Favorable risk/reward",
            ),
        ],
        reasoning="Consensus: BUY (conf=0.75) | All roles agree",
    )


@pytest.fixture
def veto_consensus():
    """Consensus with a VETO from the strategist."""
    return ConsensusDecision(
        final_action="NEUTRAL",
        final_confidence=0.0,
        vetoed_by=RoleName.STRATEGIST,
        verdicts=[
            RoleVerdict(
                role=RoleName.SCREENER,
                action="BUY",
                confidence=0.8,
                reasoning="Strong momentum",
            ),
            RoleVerdict(
                role=RoleName.TACTICAL,
                action="BUY",
                confidence=0.9,
                reasoning="Bullish breakout",
            ),
            RoleVerdict(
                role=RoleName.STRATEGIST,
                action="VETO",
                confidence=1.0,
                reasoning="Portfolio correlation risk too high",
            ),
        ],
        reasoning="VETOED (hard) by strategist: Portfolio correlation risk too high",
    )


@pytest.fixture
def sell_consensus():
    """A typical SELL consensus."""
    return ConsensusDecision(
        final_action="SELL",
        final_confidence=0.65,
        verdicts=[
            RoleVerdict(
                role=RoleName.SCREENER,
                action="SELL",
                confidence=0.7,
                reasoning="Weak momentum",
            ),
            RoleVerdict(
                role=RoleName.TACTICAL,
                action="SELL",
                confidence=0.8,
                reasoning="Bearish reversal",
            ),
        ],
        reasoning="Consensus: SELL (conf=0.65)",
    )


# ---------------------------------------------------------------------------
# Pass path — all gates pass, paper order created
# ---------------------------------------------------------------------------


def test_pass_all_gates_buy(orchestrator, buy_consensus):
    """Test that a healthy BUY consensus passes all gates and creates a paper order."""
    result = orchestrator.evaluate_and_execute(
        consensus=buy_consensus,
        symbol="BTCUSD",
        market_price=Decimal("50000"),
        portfolio_value=Decimal("10000"),
        current_exposure=Decimal("0"),
        current_positions=0,
    )

    assert result.action == "EXECUTED"
    assert result.paper_order is not None
    assert result.paper_order.symbol == "BTCUSD"
    assert result.paper_order.side == "BUY"
    assert result.paper_order.status in ("FILLED", "PENDING")
    assert len(result.gate_results) == 4
    assert all(gr.passed for gr in result.gate_results)

    # Verify all gates
    gate_names = [
        gr.gate.value if hasattr(gr.gate, "value") else str(gr.gate)
        for gr in result.gate_results
    ]
    assert "veto" in gate_names
    assert "budget" in gate_names
    assert "exposure" in gate_names
    assert "risk_limit" in gate_names


def test_pass_all_gates_sell(orchestrator, sell_consensus):
    """Test that a SELL consensus also passes all gates."""
    result = orchestrator.evaluate_and_execute(
        consensus=sell_consensus,
        symbol="ETHUSD",
        market_price=Decimal("3000"),
        portfolio_value=Decimal("10000"),
        current_exposure=Decimal("0"),
        current_positions=0,
    )

    assert result.action == "EXECUTED"
    assert result.paper_order is not None
    assert result.paper_order.side == "SELL"


def test_position_size_calculated(orchestrator, buy_consensus):
    """Test that position size is calculated and included in result."""
    result = orchestrator.evaluate_and_execute(
        consensus=buy_consensus,
        symbol="BTCUSD",
        market_price=Decimal("50000"),
        portfolio_value=Decimal("10000"),
    )

    assert result.position_size is not None
    assert result.position_size > 0
    assert result.position_value is not None
    assert result.position_value > 0
    assert result.market_price == Decimal("50000")


def test_audit_log_entry_created(orchestrator, buy_consensus):
    """Test that a decision path entry is added to the audit log."""
    orchestrator.evaluate_and_execute(
        consensus=buy_consensus,
        symbol="BTCUSD",
        market_price=Decimal("50000"),
    )

    entries = orchestrator.get_decision_path("BTCUSD")
    assert len(entries) >= 1
    entry = entries[-1]
    assert entry["symbol"] == "BTCUSD"
    assert entry["action"] == "EXECUTED"
    assert entry["paper_order_id"] is not None
    assert entry["market_price"] == "50000"
    assert len(entry["gate_results"]) == 4


# ---------------------------------------------------------------------------
# VETO gate — blocks order creation
# ---------------------------------------------------------------------------


def test_veto_blocks_order(orchestrator, veto_consensus):
    """Test that a VETO from the strategist blocks order creation."""
    result = orchestrator.evaluate_and_execute(
        consensus=veto_consensus,
        symbol="BTCUSD",
        market_price=Decimal("50000"),
        portfolio_value=Decimal("10000"),
    )

    assert result.action == "REJECTED"
    assert result.paper_order is None
    assert "VETO" in result.reason.upper() or "veto" in result.reason.lower()

    # VETO gate should be the first failing gate
    veto_gate = next(
        (gr for gr in result.gate_results if gr.gate.value == GateName.VETO), None
    )
    assert veto_gate is not None
    assert veto_gate.passed is False


def test_neutral_consensus_becomes_rejected(orchestrator):
    """Test that a NEUTRAL consensus (no VETO, low confidence) is rejected."""
    neutral = ConsensusDecision(
        final_action="NEUTRAL",
        final_confidence=0.0,
        verdicts=[
            RoleVerdict(
                role=RoleName.SCREENER, action="BUY", confidence=0.8, reasoning=""
            ),
            RoleVerdict(
                role=RoleName.TACTICAL, action="SELL", confidence=0.8, reasoning=""
            ),
        ],
        reasoning="Tie between BUY and SELL",
    )

    result = orchestrator.evaluate_and_execute(
        consensus=neutral,
        symbol="BTCUSD",
        market_price=Decimal("50000"),
    )

    # NEUTRAL with 0.0 confidence should be rejected by VETO gate
    assert result.action == "REJECTED"


# ---------------------------------------------------------------------------
# Budget gate — budget exceeded blocks order
# ---------------------------------------------------------------------------


def test_budget_exceeded_daily(orchestrator):
    """Test that daily budget limit blocks order creation."""
    # Set budget to very low to force exhaustion
    orch = ExecutionOrchestrator(
        paper_executor=PaperExecutor(),
        daily_budget_usd=0.05,  # Very low daily budget
        monthly_budget_usd=2000.0,
    )

    consensus = ConsensusDecision(
        final_action="BUY",
        final_confidence=0.8,
        verdicts=[
            RoleVerdict(
                role=RoleName.SCREENER, action="BUY", confidence=0.8, reasoning=""
            ),
            RoleVerdict(
                role=RoleName.TACTICAL, action="BUY", confidence=0.9, reasoning=""
            ),
        ],
    )

    # First trade should succeed (within budget)
    result1 = orch.evaluate_and_execute(
        consensus=consensus,
        symbol="BTCUSD",
        market_price=Decimal("50000"),
    )
    assert result1.action == "EXECUTED"

    # Second trade should fail (budget exceeded)
    result2 = orch.evaluate_and_execute(
        consensus=consensus,
        symbol="ETHUSD",
        market_price=Decimal("3000"),
    )
    assert result2.action == "REJECTED"

    budget_gate = next(
        (gr for gr in result2.gate_results if gr.gate.value == GateName.BUDGET), None
    )
    assert budget_gate is not None
    assert budget_gate.passed is False


def test_budget_exceeded_monthly(orchestrator):
    """Test that monthly budget limit blocks order creation."""
    orch = ExecutionOrchestrator(
        paper_executor=PaperExecutor(),
        daily_budget_usd=100.0,
        monthly_budget_usd=0.04,  # Very low monthly budget (less than estimated_cost of 0.05)
    )

    consensus = ConsensusDecision(
        final_action="BUY",
        final_confidence=0.8,
        verdicts=[
            RoleVerdict(
                role=RoleName.SCREENER, action="BUY", confidence=0.8, reasoning=""
            ),
        ],
    )

    result = orch.evaluate_and_execute(
        consensus=consensus,
        symbol="BTCUSD",
        market_price=Decimal("50000"),
    )

    assert result.action == "REJECTED"
    budget_gate = next(
        (gr for gr in result.gate_results if gr.gate.value == GateName.BUDGET), None
    )
    assert budget_gate is not None
    assert budget_gate.passed is False


# ---------------------------------------------------------------------------
# Risk-limit gate — exposure/position size blocks order
# ---------------------------------------------------------------------------


def test_exposure_limit_exceeded(orchestrator):
    """Test that exposure limit blocks order when position too large."""
    orch = ExecutionOrchestrator(
        paper_executor=PaperExecutor(),
        exposure_limits=ExposureLimits(
            max_position_size_per_symbol=Decimal("100"),  # Very small
            max_total_exposure=Decimal("0.5"),
            max_positions=5,
        ),
    )

    consensus = ConsensusDecision(
        final_action="BUY",
        final_confidence=0.8,
        verdicts=[
            RoleVerdict(
                role=RoleName.SCREENER, action="BUY", confidence=0.8, reasoning=""
            ),
        ],
    )

    result = orch.evaluate_and_execute(
        consensus=consensus,
        symbol="BTCUSD",
        market_price=Decimal("50000"),
        portfolio_value=Decimal("10000"),
    )

    # Should be rejected due to position size exceeding limit
    assert result.action == "REJECTED"
    exposure_gate = next(
        (gr for gr in result.gate_results if gr.gate.value == GateName.EXPOSURE), None
    )
    assert exposure_gate is not None
    assert exposure_gate.passed is False


def test_position_count_limit_exceeded(orchestrator):
    """Test that max position count blocks new orders."""
    orch = ExecutionOrchestrator(
        paper_executor=PaperExecutor(),
        max_positions=2,
    )

    consensus = ConsensusDecision(
        final_action="BUY",
        final_confidence=0.8,
        verdicts=[
            RoleVerdict(
                role=RoleName.SCREENER, action="BUY", confidence=0.8, reasoning=""
            ),
        ],
    )

    result = orch.evaluate_and_execute(
        consensus=consensus,
        symbol="BTCUSD",
        market_price=Decimal("50000"),
        current_positions=2,  # Already at max
    )

    assert result.action == "REJECTED"
    exposure_gate = next(
        (gr for gr in result.gate_results if gr.gate.value == GateName.EXPOSURE), None
    )
    assert exposure_gate is not None
    assert exposure_gate.passed is False


def test_risk_limit_calculation_success(orchestrator, buy_consensus):
    """Test that risk limit calculation succeeds within bounds."""
    result = orchestrator.evaluate_and_execute(
        consensus=buy_consensus,
        symbol="BTCUSD",
        market_price=Decimal("50000"),
        portfolio_value=Decimal("10000"),
    )

    risk_gate = next(
        (gr for gr in result.gate_results if gr.gate.value == GateName.RISK_LIMIT), None
    )
    assert risk_gate is not None
    assert risk_gate.passed is True


# ---------------------------------------------------------------------------
# Audit logging
# ---------------------------------------------------------------------------


def test_audit_log_tracks_all_decisions(orchestrator):
    """Test that both EXECUTED and REJECTED decisions are logged."""
    buy = ConsensusDecision(
        final_action="BUY",
        final_confidence=0.8,
        verdicts=[
            RoleVerdict(
                role=RoleName.SCREENER, action="BUY", confidence=0.8, reasoning=""
            ),
        ],
    )
    veto = ConsensusDecision(
        final_action="NEUTRAL",
        final_confidence=0.0,
        vetoed_by=RoleName.STRATEGIST,
        verdicts=[
            RoleVerdict(
                role=RoleName.STRATEGIST, action="VETO", confidence=1.0, reasoning=""
            ),
        ],
    )

    orch = ExecutionOrchestrator(paper_executor=PaperExecutor())

    # Execute a passing trade
    orch.evaluate_and_execute(
        consensus=buy, symbol="BTCUSD", market_price=Decimal("50000")
    )
    # Execute a vetoed trade
    orch.evaluate_and_execute(
        consensus=veto, symbol="ETHUSD", market_price=Decimal("3000")
    )

    all_entries = orch.get_audit_log()
    assert len(all_entries) == 2

    # Find the BTCUSD entry
    btc_entries = [e for e in all_entries if e["symbol"] == "BTCUSD"]
    assert len(btc_entries) == 1
    assert btc_entries[0]["action"] == "EXECUTED"

    # Find the ETHUSD entry
    eth_entries = [e for e in all_entries if e["symbol"] == "ETHUSD"]
    assert len(eth_entries) == 1
    assert eth_entries[0]["action"] == "REJECTED"


def test_audit_log_has_gate_results(orchestrator):
    """Test that gate results are included in audit entries."""
    orch = ExecutionOrchestrator(paper_executor=PaperExecutor())
    consensus = ConsensusDecision(
        final_action="BUY",
        final_confidence=0.8,
        verdicts=[],
    )

    orch.evaluate_and_execute(
        consensus=consensus, symbol="BTCUSD", market_price=Decimal("50000")
    )

    entries = orch.get_decision_path("BTCUSD")
    assert len(entries) >= 1
    entry = entries[-1]
    assert "gate_results" in entry
    assert len(entry["gate_results"]) == 4

    # Verify each gate result has required fields
    for gr in entry["gate_results"]:
        assert "gate" in gr
        assert "passed" in gr
        assert "reason" in gr


def test_budget_reset_clears_spend(orchestrator):
    """Test that resetting budget clears the spend tracking."""
    orch = ExecutionOrchestrator(
        paper_executor=PaperExecutor(),
        daily_budget_usd=0.05,
    )

    consensus = ConsensusDecision(
        final_action="BUY",
        final_confidence=0.8,
        verdicts=[],
    )

    # First trade exhausts budget
    orch.evaluate_and_execute(
        consensus=consensus, symbol="BTCUSD", market_price=Decimal("50000")
    )

    # Second trade should fail
    result = orch.evaluate_and_execute(
        consensus=consensus, symbol="ETHUSD", market_price=Decimal("3000")
    )
    assert result.action == "REJECTED"

    # Reset budget
    orch.reset_budget()

    # Third trade should succeed again
    result = orch.evaluate_and_execute(
        consensus=consensus, symbol="SOLUSD", market_price=Decimal("100")
    )
    assert result.action == "EXECUTED"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_zero_confidence_consensus(orchestrator):
    """Test handling of zero-confidence consensus."""
    zero_conf = ConsensusDecision(
        final_action="NEUTRAL",
        final_confidence=0.0,
        verdicts=[],
    )

    result = orchestrator.evaluate_and_execute(
        consensus=zero_conf,
        symbol="BTCUSD",
        market_price=Decimal("50000"),
    )

    # Should be rejected (VETO gate catches zero-confidence NEUTRAL)
    assert result.action == "REJECTED"


def test_single_verdict_consensus(orchestrator):
    """Test consensus with only one role verdict."""
    single = ConsensusDecision(
        final_action="BUY",
        final_confidence=0.9,
        verdicts=[
            RoleVerdict(
                role=RoleName.TACTICAL,
                action="BUY",
                confidence=0.9,
                reasoning="Strong signal",
            ),
        ],
    )

    result = orchestrator.evaluate_and_execute(
        consensus=single,
        symbol="BTCUSD",
        market_price=Decimal("50000"),
    )

    # Single strong verdict should pass all gates
    assert result.action == "EXECUTED"


def test_high_confidence_consensus(orchestrator):
    """Test that high-confidence consensus creates larger positions."""
    high_conf = ConsensusDecision(
        final_action="BUY",
        final_confidence=0.95,
        verdicts=[
            RoleVerdict(
                role=RoleName.SCREENER, action="BUY", confidence=0.95, reasoning=""
            ),
            RoleVerdict(
                role=RoleName.TACTICAL, action="BUY", confidence=0.95, reasoning=""
            ),
            RoleVerdict(
                role=RoleName.FUNDAMENTAL, action="BUY", confidence=0.95, reasoning=""
            ),
            RoleVerdict(
                role=RoleName.STRATEGIST, action="BUY", confidence=0.95, reasoning=""
            ),
        ],
    )

    result = orchestrator.evaluate_and_execute(
        consensus=high_conf,
        symbol="BTCUSD",
        market_price=Decimal("50000"),
    )

    assert result.action == "EXECUTED"
    # High confidence should produce a reasonable position size
    assert result.position_size is not None
    assert result.position_size > 0


def test_market_price_reflected_in_order(orchestrator, buy_consensus):
    """Test that the market price is correctly reflected in the paper order."""
    result = orchestrator.evaluate_and_execute(
        consensus=buy_consensus,
        symbol="BTCUSD",
        market_price=Decimal("50000"),
    )

    assert result.market_price == Decimal("50000")
    if result.paper_order:
        assert result.paper_order.symbol == "BTCUSD"


def test_latency_tracked(orchestrator, buy_consensus):
    """Test that latency is tracked in the result."""
    result = orchestrator.evaluate_and_execute(
        consensus=buy_consensus,
        symbol="BTCUSD",
        market_price=Decimal("50000"),
    )

    assert result.latency_ms >= 0
    assert isinstance(result.latency_ms, float)
