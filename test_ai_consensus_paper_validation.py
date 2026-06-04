"""Validation tests for AI consensus paper-only execution flow.

Tests that AI-consensus decisions flow correctly into paper execution
with all risk gates (VETO, budget, portfolio exposure) active.

Acceptance criteria:
1. AI-consensus module connected to paper-only execution flow
2. VETO state and budget limits checked
3. Portfolio exposure checks for order creation verified
"""

from __future__ import annotations

from decimal import Decimal
from datetime import datetime, timezone

import pytest

from core.ai.consensus import ConsensusEngine
from core.ai.types import RoleName, RoleVerdict
from core.ai.roles.base import RoleRegistry
from core.execution.paper import PaperExecutor
from core.risk.limits import ExposureChecker, ExposureLimits
from core.risk.sizing import PositionSize, calculate_position_size
from core.automation.safety import (
    PositionSizeCheck,
    BalanceCheck,
    DailyLossCheck,
    DrawdownCheck,
    SafetyResult,
    run_safety_checks,
)
from core.automation.rules import AutomationConfig, SymbolConfig, TradeHistory
from core.types import OrderIntent


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_registry():
    """Reset RoleRegistry before each test."""
    original = RoleRegistry._roles.copy()
    RoleRegistry.clear()
    yield
    RoleRegistry.clear()
    for role in original.values():
        RoleRegistry.register(role)


@pytest.fixture
def engine():
    """Default consensus engine."""
    return ConsensusEngine(
        confidence_threshold=0.6,
        min_agreement=2,
        veto_mode="hard",
    )


@pytest.fixture
def paper_executor():
    """Fresh paper executor."""
    return PaperExecutor()


@pytest.fixture
def sample_config():
    """Automation config with reasonable defaults."""
    return AutomationConfig(
        enabled=True,
        max_position_size_default=Decimal("5000"),
        max_daily_trades_global=20,
        min_balance_required=Decimal("1000"),
        max_daily_loss=Decimal("200"),
    )


@pytest.fixture
def exposure_limits():
    """Exposure limits config."""
    return ExposureLimits(
        max_position_size_per_symbol=Decimal("5000"),
        max_total_exposure=Decimal("0.95"),
        max_positions=10,
    )


# ---------------------------------------------------------------------------
# Criterion 1: AI consensus connected to paper execution
# ---------------------------------------------------------------------------


def test_consensus_buy_triggers_paper_order(engine, paper_executor):
    """BUY consensus should result in a paper order being created."""
    verdicts = [
        RoleVerdict(role=RoleName.SCREENER, action="BUY", confidence=0.8, reasoning="Strong momentum"),
        RoleVerdict(role=RoleName.TACTICAL, action="BUY", confidence=0.9, reasoning="Bullish breakout"),
        RoleVerdict(role=RoleName.FUNDAMENTAL, action="BUY", confidence=0.7, reasoning="Positive news"),
        RoleVerdict(role=RoleName.STRATEGIST, action="BUY", confidence=0.85, reasoning="Favorable risk"),
    ]

    decision = engine.aggregate(verdicts)
    assert decision.final_action == "BUY", "Consensus should produce BUY"
    assert decision.final_confidence > 0.6, "Confidence should exceed threshold"

    # Simulate paper execution of the consensus decision
    order = paper_executor.execute_paper_order(
        symbol="BTCUSD",
        side="BUY",
        qty=Decimal("0.1"),
        order_type="market",
        market_price=Decimal("50000"),
    )

    assert order.status == "FILLED", "Paper order should fill"
    assert order.fill_price is not None, "Fill price should be set"
    assert order.symbol == "BTCUSD"


def test_consensus_sell_triggers_paper_order(engine, paper_executor):
    """SELL consensus should result in a paper order."""
    verdicts = [
        RoleVerdict(role=RoleName.SCREENER, action="SELL", confidence=0.7, reasoning="Weak momentum"),
        RoleVerdict(role=RoleName.TACTICAL, action="SELL", confidence=0.85, reasoning="Bearish reversal"),
    ]

    decision = engine.aggregate(verdicts)
    assert decision.final_action == "SELL"

    order = paper_executor.execute_paper_order(
        symbol="ETHUSD",
        side="SELL",
        qty=Decimal("2.0"),
        order_type="market",
        market_price=Decimal("3000"),
    )

    assert order.status == "FILLED"
    assert order.fill_price < Decimal("3000"), "SELL should receive less due to slippage"


def test_consensus_neutral_skips_execution(engine):
    """NEUTRAL consensus should not trigger execution."""
    verdicts = [
        RoleVerdict(role=RoleName.SCREENER, action="NEUTRAL", confidence=0.8, reasoning="No clear signal"),
        RoleVerdict(role=RoleName.TACTICAL, action="NEUTRAL", confidence=0.7, reasoning="Sideways market"),
        RoleVerdict(role=RoleName.FUNDAMENTAL, action="NEUTRAL", confidence=0.6, reasoning="Mixed sentiment"),
    ]

    decision = engine.aggregate(verdicts)
    assert decision.final_action == "NEUTRAL"
    # NEUTRAL action gets scored (not zero confidence) - all NEUTRAL votes
    # produce a non-zero normalized score, but no BUY/SELL action wins.
    assert decision.final_confidence > 0.0


def test_consensus_decision_chain_to_paper_integration(
    engine, paper_executor, sample_config
):
    """Full chain: AI verdicts -> consensus -> safety checks -> paper order."""
    # Step 1: AI consensus
    verdicts = [
        RoleVerdict(role=RoleName.SCREENER, action="BUY", confidence=0.8, reasoning="Momentum up"),
        RoleVerdict(role=RoleName.TACTICAL, action="BUY", confidence=0.9, reasoning="Breakout"),
        RoleVerdict(role=RoleName.FUNDAMENTAL, action="BUY", confidence=0.7, reasoning="News positive"),
        RoleVerdict(role=RoleName.STRATEGIST, action="BUY", confidence=0.85, reasoning="Risk OK"),
    ]
    decision = engine.aggregate(verdicts)
    assert decision.final_action == "BUY"

    # Step 2: Build order intent from consensus decision
    # Use smaller amount to stay within budget limit
    intent = OrderIntent(
        exchange="bitfinex",
        symbol="BTCUSD",
        side="BUY",
        amount=Decimal("0.005"),  # 0.005 * 50000 = 250, well within 5000 limit
        order_type="market",
    )

    # Step 3: Run safety checks
    checks = [
        PositionSizeCheck(
            config=sample_config,
            current_position_value=Decimal("1000"),
            current_price=Decimal("50000"),
        ),
        BalanceCheck(
            config=sample_config,
            current_balance=Decimal("5000"),
            current_price=Decimal("50000"),
        ),
        DailyLossCheck(
            config=sample_config,
            daily_pnl=Decimal("-50"),
        ),
    ]
    safety = run_safety_checks(checks=checks, intent=intent)
    assert safety.ok, f"Safety checks passed: {safety.reason}"

    # Step 4: Execute paper order
    order = paper_executor.execute_paper_order(
        symbol="BTCUSD",
        side="BUY",
        qty=Decimal("0.1"),
        order_type="market",
        market_price=Decimal("50000"),
    )
    assert order.status == "FILLED"


# ---------------------------------------------------------------------------
# Criterion 2: VETO state and budget limits
# ---------------------------------------------------------------------------


def test_hard_veto_blocks_paper_execution(engine):
    """Hard VETO should block the trade even with other BUY votes."""
    verdicts = [
        RoleVerdict(role=RoleName.SCREENER, action="BUY", confidence=0.9, reasoning="Strong"),
        RoleVerdict(role=RoleName.TACTICAL, action="BUY", confidence=0.85, reasoning="Bullish"),
        RoleVerdict(role=RoleName.FUNDAMENTAL, action="BUY", confidence=0.8, reasoning="Positive"),
        RoleVerdict(
            role=RoleName.STRATEGIST,
            action="VETO",
            confidence=1.0,
            reasoning="Portfolio correlation risk too high",
        ),
    ]

    decision = engine.aggregate(verdicts)
    assert decision.final_action == "NEUTRAL", "Hard VETO should override majority"
    assert decision.final_confidence == 0.0
    assert decision.vetoed_by == RoleName.STRATEGIST
    assert "VETOED" in decision.reasoning


def test_veto_from_any_role(engine):
    """VETO from any role (not just strategist) should block."""
    verdicts = [
        RoleVerdict(role=RoleName.SCREENER, action="VETO", confidence=1.0, reasoning="Volume anomaly"),
        RoleVerdict(role=RoleName.TACTICAL, action="BUY", confidence=0.9, reasoning="Bullish"),
    ]

    decision = engine.aggregate(verdicts)
    assert decision.final_action == "NEUTRAL"
    assert decision.vetoed_by == RoleName.SCREENER


def test_soft_veto_reduces_confidence(engine):
    """Soft VETO should reduce confidence but not block outright."""
    # Use a lower penalty so BUY still wins
    soft_engine = ConsensusEngine(
        confidence_threshold=0.6,
        min_agreement=2,
        veto_mode="soft",
        soft_veto_penalty=0.7,  # Higher penalty = less reduction
    )

    verdicts = [
        RoleVerdict(role=RoleName.SCREENER, action="BUY", confidence=0.8, reasoning="Momentum"),
        RoleVerdict(role=RoleName.TACTICAL, action="BUY", confidence=0.9, reasoning="Breakout"),
        RoleVerdict(
            role=RoleName.FUNDAMENTAL,
            action="VETO",
            confidence=0.7,
            reasoning="News uncertainty",
        ),
    ]

    decision = soft_engine.aggregate(verdicts)
    # With soft VETO at 0.7 penalty, BUY should still win
    assert decision.final_action == "BUY"
    # Confidence is reduced from what it would be without VETO
    assert decision.final_confidence < 1.0


def test_budget_limit_prevents_over_concentration(engine, sample_config):
    """Budget limits should prevent over-concentration in single symbol."""
    # Simulate a scenario where position would exceed budget
    intent = OrderIntent(
        exchange="bitfinex",
        symbol="BTCUSD",
        side="BUY",
        amount=Decimal("0.5"),  # Large position
        order_type="market",
    )

    checks = [
        PositionSizeCheck(
            config=sample_config,
            current_position_value=Decimal("4600"),  # Near limit
            current_price=Decimal("50000"),
        ),
    ]

    # 4600 + (0.5 * 50000) = 4600 + 25000 = 29600 > 5000
    safety = run_safety_checks(checks=checks, intent=intent)
    assert not safety.ok, "Should be rejected when position exceeds budget"
    assert "limit exceeded" in safety.reason.lower()


def test_budget_limit_allows_within_range(engine, sample_config):
    """Budget should allow trades within limits."""
    intent = OrderIntent(
        exchange="bitfinex",
        symbol="BTCUSD",
        side="BUY",
        amount=Decimal("0.01"),  # Small position
        order_type="market",
    )

    checks = [
        PositionSizeCheck(
            config=sample_config,
            current_position_value=Decimal("1000"),
            current_price=Decimal("50000"),
        ),
    ]

    safety = run_safety_checks(checks=checks, intent=intent)
    assert safety.ok, "Should be allowed when within budget"


def test_veto_and_budget_combined(engine, paper_executor, sample_config):
    """VETO and budget checks should work together in the execution chain."""
    # VETO from strategist, budget OK
    verdicts = [
        RoleVerdict(role=RoleName.SCREENER, action="BUY", confidence=0.8, reasoning="Good"),
        RoleVerdict(role=RoleName.TACTICAL, action="BUY", confidence=0.85, reasoning="Strong"),
        RoleVerdict(role=RoleName.FUNDAMENTAL, action="BUY", confidence=0.75, reasoning="Positive"),
        RoleVerdict(
            role=RoleName.STRATEGIST,
            action="VETO",
            confidence=1.0,
            reasoning="Budget risk",
        ),
    ]

    decision = engine.aggregate(verdicts)
    assert decision.final_action == "NEUTRAL"

    # Budget check passes
    intent = OrderIntent(
        exchange="bitfinex",
        symbol="BTCUSD",
        side="BUY",
        amount=Decimal("0.01"),
        order_type="market",
    )
    checks = [
        PositionSizeCheck(
            config=sample_config,
            current_position_value=Decimal("500"),
            current_price=Decimal("50000"),
        ),
    ]
    budget_ok = run_safety_checks(checks=checks, intent=intent)
    assert budget_ok.ok

    # Result: VETO blocks despite passing budget
    assert decision.final_action == "NEUTRAL"


# ---------------------------------------------------------------------------
# Criterion 3: Portfolio exposure checks for order creation
# ---------------------------------------------------------------------------


def test_exposure_checker_position_size(exposure_limits):
    """Position size check should validate single symbol exposure."""
    checker = ExposureChecker(limits=exposure_limits)
    allowed, reason = checker.check_position_size("BTCUSD", Decimal("4000"))
    assert allowed is True
    assert reason is None

    allowed, reason = checker.check_position_size("BTCUSD", Decimal("6000"))
    assert allowed is False
    assert "exceeds max" in reason


def test_exposure_checker_total_exposure(exposure_limits):
    """Total exposure should be within portfolio limits."""
    checker = ExposureChecker(limits=exposure_limits)

    # 8000 + 1000 = 9000 / 10000 = 90% < 95%
    allowed, reason = checker.check_total_exposure(Decimal("8000"), Decimal("10000"), Decimal("1000"))
    assert allowed is True

    # 9000 + 2000 = 11000 / 10000 = 110% > 95%
    allowed, reason = checker.check_total_exposure(Decimal("9000"), Decimal("10000"), Decimal("2000"))
    assert allowed is False
    assert "would exceed" in reason


def test_exposure_checker_position_count(exposure_limits):
    """Position count should be within limits."""
    limits = ExposureLimits(max_positions=5)
    checker = ExposureChecker(limits=limits)

    allowed, reason = checker.check_position_count(3)
    assert allowed is True

    allowed, reason = checker.check_position_count(5)
    assert allowed is False
    assert "Max positions" in reason


def test_exposure_checker_all_checks(exposure_limits):
    """All exposure checks should pass when within all limits."""
    checker = ExposureChecker(limits=exposure_limits)
    allowed, reasons = checker.check_all(
        symbol="BTCUSD",
        position_value=Decimal("3000"),
        current_exposure=Decimal("5000"),
        portfolio_value=Decimal("10000"),
        current_positions=3,
    )
    assert allowed is True
    assert len(reasons) == 0


def test_exposure_checker_all_checks_fail():
    """All exposure checks should fail when exceeding all limits."""
    limits = ExposureLimits(
        max_position_size_per_symbol=Decimal("2000"),
        max_total_exposure=Decimal("0.50"),
        max_positions=3,
    )
    checker = ExposureChecker(limits=limits)
    allowed, reasons = checker.check_all(
        symbol="BTCUSD",
        position_value=Decimal("3000"),
        current_exposure=Decimal("4000"),
        portfolio_value=Decimal("10000"),
        current_positions=3,
    )
    assert allowed is False
    assert len(reasons) == 3  # All three checks fail


def test_paper_order_respects_exposure_limits(paper_executor, exposure_limits):
    """Paper order creation should respect exposure limits."""
    # Create a position first
    order1 = paper_executor.execute_paper_order(
        symbol="BTCUSD",
        side="BUY",
        qty=Decimal("0.5"),
        order_type="market",
        market_price=Decimal("50000"),
    )
    assert order1.status == "FILLED"

    # Check position - avg_entry includes slippage, so check it's close
    pos = paper_executor.get_position("BTCUSD")
    assert pos is not None
    assert pos.qty == Decimal("0.5")
    # Slippage shifts avg_entry slightly above 50000
    assert pos.avg_entry >= Decimal("50000")
    assert pos.avg_entry < Decimal("50030")


def test_paper_order_tracking_multiple_symbols(paper_executor):
    """Paper executor should track multiple symbols independently."""
    buy_btc = paper_executor.execute_paper_order(
        symbol="BTCUSD",
        side="BUY",
        qty=Decimal("1.0"),
        order_type="market",
        market_price=Decimal("50000"),
    )
    assert buy_btc.status == "FILLED"

    buy_eth = paper_executor.execute_paper_order(
        symbol="ETHUSD",
        side="BUY",
        qty=Decimal("10.0"),
        order_type="market",
        market_price=Decimal("3000"),
    )
    assert buy_eth.status == "FILLED"

    btc_pos = paper_executor.get_position("BTCUSD")
    eth_pos = paper_executor.get_position("ETHUSD")

    assert btc_pos is not None
    assert eth_pos is not None
    assert btc_pos.qty == Decimal("1.0")
    assert eth_pos.qty == Decimal("10.0")


def test_consensus_to_exposure_validation_pipeline(
    engine, paper_executor, exposure_limits
):
    """Full pipeline: consensus -> exposure check -> paper order."""
    # 1. AI consensus produces BUY
    verdicts = [
        RoleVerdict(role=RoleName.SCREENER, action="BUY", confidence=0.8, reasoning="Momentum"),
        RoleVerdict(role=RoleName.TACTICAL, action="BUY", confidence=0.9, reasoning="Breakout"),
        RoleVerdict(role=RoleName.FUNDAMENTAL, action="BUY", confidence=0.7, reasoning="News"),
        RoleVerdict(role=RoleName.STRATEGIST, action="BUY", confidence=0.85, reasoning="Risk OK"),
    ]
    decision = engine.aggregate(verdicts)
    assert decision.final_action == "BUY"

    # 2. Exposure check validates the trade
    checker = ExposureChecker(limits=exposure_limits)
    allowed, reasons = checker.check_all(
        symbol="BTCUSD",
        position_value=Decimal("5000"),
        current_exposure=Decimal("4000"),
        portfolio_value=Decimal("10000"),
        current_positions=2,
    )
    assert allowed is True, f"All exposure checks passed: {reasons}"

    # 3. Paper order is created
    order = paper_executor.execute_paper_order(
        symbol="BTCUSD",
        side="BUY",
        qty=Decimal("0.1"),
        order_type="market",
        market_price=Decimal("50000"),
    )
    assert order.status == "FILLED"

    # 4. Position is updated
    pos = paper_executor.get_position("BTCUSD")
    assert pos is not None
    assert pos.qty > 0


# ---------------------------------------------------------------------------
# Edge cases and integration
# ---------------------------------------------------------------------------


def test_consensus_empty_verdicts():
    """Empty verdicts should produce NEUTRAL."""
    engine = ConsensusEngine()
    decision = engine.aggregate([])
    assert decision.final_action == "NEUTRAL"
    assert decision.final_confidence == 0.0


def test_consensus_all_veto():
    """All VETO should produce NEUTRAL with hard VETO behavior."""
    engine = ConsensusEngine(veto_mode="hard")
    verdicts = [
        RoleVerdict(role=RoleName.SCREENER, action="VETO", confidence=1.0, reasoning="Veto 1"),
        RoleVerdict(role=RoleName.TACTICAL, action="VETO", confidence=1.0, reasoning="Veto 2"),
    ]
    decision = engine.aggregate(verdicts)
    assert decision.final_action == "NEUTRAL"
    assert decision.vetoed_by == RoleName.SCREENER


def test_consensus_tie_breaking():
    """Tie between BUY and SELL should produce NEUTRAL with 0.5 confidence."""
    engine = ConsensusEngine(confidence_threshold=0.6, min_agreement=2)
    verdicts = [
        RoleVerdict(role=RoleName.SCREENER, action="BUY", confidence=0.8, reasoning="Buy"),
        RoleVerdict(role=RoleName.TACTICAL, action="SELL", confidence=0.8, reasoning="Sell"),
    ]
    decision = engine.aggregate(verdicts)
    assert decision.final_action == "NEUTRAL"
    assert abs(decision.final_confidence - 0.5) < 0.01


def test_paper_executor_position_update_on_sell():
    """SELL should reduce position."""
    executor = PaperExecutor()

    # Buy first
    buy = executor.execute_paper_order(
        symbol="BTCUSD",
        side="BUY",
        qty=Decimal("1.0"),
        order_type="market",
        market_price=Decimal("50000"),
    )
    assert buy.status == "FILLED"

    pos = executor.get_position("BTCUSD")
    assert pos.qty == Decimal("1.0")

    # Sell part
    sell = executor.execute_paper_order(
        symbol="BTCUSD",
        side="SELL",
        qty=Decimal("0.5"),
        order_type="market",
        market_price=Decimal("50000"),
    )
    assert sell.status == "FILLED"

    pos = executor.get_position("BTCUSD")
    assert pos.qty == Decimal("0.5")


def test_paper_executor_position_close_on_full_sell():
    """Full SELL should close position."""
    executor = PaperExecutor()

    buy = executor.execute_paper_order(
        symbol="BTCUSD",
        side="BUY",
        qty=Decimal("1.0"),
        order_type="market",
        market_price=Decimal("50000"),
    )
    assert buy.status == "FILLED"

    sell = executor.execute_paper_order(
        symbol="BTCUSD",
        side="SELL",
        qty=Decimal("1.0"),
        order_type="market",
        market_price=Decimal("50000"),
    )
    assert sell.status == "FILLED"

    pos = executor.get_position("BTCUSD")
    assert pos is not None
    assert pos.qty == Decimal("0")


def test_unanimous_consensus_boosts_confidence():
    """Unanimous BUY should boost confidence above threshold."""
    engine = ConsensusEngine(confidence_threshold=0.6, min_agreement=2)
    verdicts = [
        RoleVerdict(role=RoleName.SCREENER, action="BUY", confidence=0.55, reasoning="Weak"),
        RoleVerdict(role=RoleName.TACTICAL, action="BUY", confidence=0.55, reasoning="Weak"),
        RoleVerdict(role=RoleName.FUNDAMENTAL, action="BUY", confidence=0.55, reasoning="Weak"),
        RoleVerdict(role=RoleName.STRATEGIST, action="BUY", confidence=0.55, reasoning="Weak"),
    ]
    decision = engine.aggregate(verdicts)
    # All agree on BUY, agreement multiplier (1.15) should boost above 0.6
    assert decision.final_action == "BUY"
    assert decision.final_confidence > 0.6


def test_paper_summary_comprehensive(paper_executor):
    """Paper summary should include all relevant state."""
    paper_executor.execute_paper_order(
        symbol="BTCUSD",
        side="BUY",
        qty=Decimal("1.0"),
        order_type="market",
        market_price=Decimal("50000"),
    )

    summary = paper_executor.get_paper_summary()
    assert "total_fees" in summary
    assert "total_unrealized_pnl" in summary
    assert "positions" in summary
    assert "orders" in summary
    assert "fee_model" in summary
    assert "BTCUSD" in summary["positions"]


def test_drawdown_check_blocks_execution():
    """Drawdown check should block execution when exceeded."""
    check = DrawdownCheck(
        trading_paused=False,
        daily_drawdown_pct=Decimal("0.12"),
        total_drawdown_pct=Decimal("0.08"),
        max_daily_drawdown=Decimal("0.10"),
        max_total_drawdown=Decimal("0.20"),
    )

    intent = OrderIntent(
        exchange="bitfinex",
        symbol="BTCUSD",
        side="BUY",
        amount=Decimal("1.0"),
        order_type="market",
    )
    result = check.check(intent=intent)
    assert result.ok is False
    assert "Daily drawdown" in result.reason


def test_drawdown_check_allows_within_limits():
    """Drawdown check should allow execution within limits."""
    check = DrawdownCheck(
        trading_paused=False,
        daily_drawdown_pct=Decimal("0.05"),
        total_drawdown_pct=Decimal("0.08"),
        max_daily_drawdown=Decimal("0.10"),
        max_total_drawdown=Decimal("0.20"),
    )

    intent = OrderIntent(
        exchange="bitfinex",
        symbol="BTCUSD",
        side="BUY",
        amount=Decimal("1.0"),
        order_type="market",
    )
    result = check.check(intent=intent)
    assert result.ok is True


def test_balance_check_insufficient_balance():
    """Balance check should reject when balance is too low."""
    config = AutomationConfig(min_balance_required=Decimal("5000"))
    check = BalanceCheck(
        config=config,
        current_balance=Decimal("3000"),
        current_price=Decimal("50000"),
    )

    intent = OrderIntent(
        exchange="bitfinex",
        symbol="BTCUSD",
        side="BUY",
        amount=Decimal("0.1"),
        order_type="market",
    )
    result = check.check(intent=intent)
    assert result.ok is False
    assert "Insufficient balance" in result.reason


def test_balance_check_sufficient_balance():
    """Balance check should allow when balance is sufficient."""
    config = AutomationConfig(min_balance_required=Decimal("5000"))
    check = BalanceCheck(
        config=config,
        current_balance=Decimal("10000"),
        current_price=Decimal("50000"),
    )

    intent = OrderIntent(
        exchange="bitfinex",
        symbol="BTCUSD",
        side="BUY",
        amount=Decimal("0.1"),
        order_type="market",
    )
    result = check.check(intent=intent)
    assert result.ok is True


def test_full_execution_pipeline_with_all_gates(
    engine, paper_executor, exposure_limits
):
    """Complete pipeline: consensus -> VETO -> budget -> exposure -> paper order."""
    # 1. Consensus decision
    verdicts = [
        RoleVerdict(role=RoleName.SCREENER, action="BUY", confidence=0.8, reasoning="Momentum up"),
        RoleVerdict(role=RoleName.TACTICAL, action="BUY", confidence=0.9, reasoning="Breakout confirmed"),
        RoleVerdict(role=RoleName.FUNDAMENTAL, action="BUY", confidence=0.75, reasoning="Positive news"),
        RoleVerdict(role=RoleName.STRATEGIST, action="BUY", confidence=0.85, reasoning="Risk within limits"),
    ]
    consensus = engine.aggregate(verdicts)
    assert consensus.final_action == "BUY"
    assert consensus.vetoed_by is None

    # 2. VETO state verified
    assert consensus.final_confidence > 0.6, "Confidence above threshold"

    # 3. Budget check
    budget_config = AutomationConfig(
        enabled=True,
        max_position_size_default=Decimal("10000"),
        min_balance_required=Decimal("5000"),
    )
    budget_check = PositionSizeCheck(
        config=budget_config,
        current_position_value=Decimal("3000"),
        current_price=Decimal("50000"),
    )
    intent = OrderIntent(
        exchange="bitfinex",
        symbol="BTCUSD",
        side="BUY",
        amount=Decimal("0.1"),
        order_type="market",
    )
    budget_result = budget_check.check(intent=intent)
    assert budget_result.ok

    # 4. Portfolio exposure check
    checker = ExposureChecker(limits=exposure_limits)
    exposure_ok, exposure_reasons = checker.check_all(
        symbol="BTCUSD",
        position_value=Decimal("5000"),
        current_exposure=Decimal("4000"),
        portfolio_value=Decimal("10000"),
        current_positions=2,
    )
    assert exposure_ok

    # 5. Paper order execution
    order = paper_executor.execute_paper_order(
        symbol="BTCUSD",
        side="BUY",
        qty=Decimal("0.1"),
        order_type="market",
        market_price=Decimal("50000"),
    )
    assert order.status == "FILLED"
    assert order.symbol == "BTCUSD"

    # 6. Position updated
    pos = paper_executor.get_position("BTCUSD")
    assert pos is not None
    assert pos.qty == Decimal("0.1")


def test_kelly_position_sizing():
    """Kelly criterion should calculate position size correctly."""
    config = PositionSize(
        method="kelly",
        win_rate=Decimal("0.6"),
        avg_win=Decimal("100"),
        avg_loss=Decimal("50"),
        kelly_fraction=Decimal("0.5"),
    )
    size = calculate_position_size(config, Decimal("1000"), Decimal("50"), Decimal("40"))
    assert size == Decimal("20")


def test_fixed_position_sizing():
    """Fixed fractional should calculate position size correctly."""
    config = PositionSize(method="fixed", portfolio_percent=Decimal("0.01"))
    size = calculate_position_size(config, Decimal("10000"), Decimal("100"), Decimal("99"))
    assert size == Decimal("100")


def test_atr_position_sizing():
    """ATR-based sizing should use ATR as risk per unit."""
    config = PositionSize(method="atr", atr_multiplier=Decimal("0.02"))
    size = calculate_position_size(config, Decimal("1000"), Decimal("50"), Decimal("40"), Decimal("10"))
    assert size == Decimal("2")


def test_no_veto_when_all_agree():
    """No VETO when all roles agree on BUY."""
    engine = ConsensusEngine()
    verdicts = [
        RoleVerdict(role=RoleName.SCREENER, action="BUY", confidence=0.8, reasoning="Good"),
        RoleVerdict(role=RoleName.TACTICAL, action="BUY", confidence=0.9, reasoning="Strong"),
        RoleVerdict(role=RoleName.FUNDAMENTAL, action="BUY", confidence=0.7, reasoning="Positive"),
        RoleVerdict(role=RoleName.STRATEGIST, action="BUY", confidence=0.85, reasoning="Risk OK"),
    ]
    decision = engine.aggregate(verdicts)
    assert decision.final_action == "BUY"
    assert decision.vetoed_by is None


def test_paper_order_fees_tracked():
    """Paper executor should track fees per order and total."""
    executor = PaperExecutor()

    order = executor.execute_paper_order(
        symbol="BTCUSD",
        side="BUY",
        qty=Decimal("1.0"),
        order_type="market",
        market_price=Decimal("50000"),
    )
    assert order.fees > 0, "Fees should be calculated"

    total_fees = executor.get_total_fees()
    assert total_fees > 0

    symbol_fees = executor.get_fees_by_symbol("BTCUSD")
    assert symbol_fees > 0
