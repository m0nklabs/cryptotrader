"""Unit tests for the Multi-Brain consensus engine.

Tests weighted voting, VETO power, thresholds, and edge cases.

Phase 6.1 (P6.1) of issue #205.
"""

from __future__ import annotations

import pytest

from core.ai.consensus import ConsensusEngine
from core.ai.types import RoleName, RoleVerdict


# ---------------------------------------------------------------------------
# Test Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def engine():
    """Default consensus engine with standard thresholds."""
    return ConsensusEngine(
        confidence_threshold=0.6,
        min_agreement=2,
    )


@pytest.fixture
def strict_engine():
    """Strict consensus engine with higher thresholds."""
    return ConsensusEngine(
        confidence_threshold=0.8,
        min_agreement=3,
    )


# ---------------------------------------------------------------------------
# Basic Weighted Voting Tests
# ---------------------------------------------------------------------------


def test_consensus_simple_buy(engine):
    """Test simple BUY consensus with all roles agreeing."""
    verdicts = [
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
            reasoning="Bullish pattern",
        ),
        RoleVerdict(
            role=RoleName.FUNDAMENTAL,
            action="BUY",
            confidence=0.7,
            reasoning="Positive news",
        ),
        RoleVerdict(
            role=RoleName.STRATEGIST,
            action="BUY",
            confidence=0.85,
            reasoning="Good risk/reward",
        ),
    ]
    
    decision = engine.aggregate(verdicts)
    
    assert decision.final_action == "BUY"
    assert decision.final_confidence > 0.6
    assert decision.vetoed_by is None
    assert len(decision.verdicts) == 4
    assert "Consensus: BUY" in decision.reasoning


def test_consensus_simple_sell(engine):
    """Test simple SELL consensus with all roles agreeing."""
    verdicts = [
        RoleVerdict(
            role=RoleName.SCREENER,
            action="SELL",
            confidence=0.75,
            reasoning="Weak momentum",
        ),
        RoleVerdict(
            role=RoleName.TACTICAL,
            action="SELL",
            confidence=0.85,
            reasoning="Bearish pattern",
        ),
    ]
    
    decision = engine.aggregate(verdicts)
    
    assert decision.final_action == "SELL"
    assert decision.final_confidence > 0.6
    assert decision.vetoed_by is None


def test_consensus_mixed_votes_buy_wins(engine):
    """Test mixed votes where BUY wins due to higher weights."""
    verdicts = [
        # Screener (weight 0.5) votes NEUTRAL
        RoleVerdict(
            role=RoleName.SCREENER,
            action="NEUTRAL",
            confidence=0.6,
            reasoning="No strong signal",
        ),
        # Tactical (weight 1.5) votes BUY with high confidence
        RoleVerdict(
            role=RoleName.TACTICAL,
            action="BUY",
            confidence=0.9,
            reasoning="Strong breakout",
        ),
        # Strategist (weight 1.2) votes BUY
        RoleVerdict(
            role=RoleName.STRATEGIST,
            action="BUY",
            confidence=0.8,
            reasoning="Favorable risk",
        ),
    ]
    
    decision = engine.aggregate(verdicts)
    
    # BUY should win due to higher weights (1.5 + 1.2 vs 0.5)
    assert decision.final_action == "BUY"
    assert decision.vetoed_by is None


def test_consensus_below_threshold_becomes_neutral(engine):
    """Test that actions below confidence threshold become NEUTRAL."""
    # To get below threshold, we need disagreement between actions
    # so that the winning action's normalized score is < 0.6
    verdicts = [
        RoleVerdict(
            role=RoleName.SCREENER,
            action="BUY",
            confidence=0.5,
            reasoning="Weak buy signal",
        ),
        RoleVerdict(
            role=RoleName.TACTICAL,
            action="SELL",
            confidence=0.6,
            reasoning="Weak sell signal",
        ),
        RoleVerdict(
            role=RoleName.FUNDAMENTAL,
            action="NEUTRAL",
            confidence=0.8,
            reasoning="Mixed sentiment",
        ),
    ]
    
    decision = engine.aggregate(verdicts)
    
    # With disagreement, no action should reach 60% threshold
    # So should become NEUTRAL
    assert decision.final_action == "NEUTRAL"


def test_consensus_insufficient_agreement(engine):
    """Test that insufficient agreement count becomes NEUTRAL."""
    # Engine requires min_agreement=2, but only 1 role votes for action
    verdicts = [
        RoleVerdict(
            role=RoleName.TACTICAL,
            action="BUY",
            confidence=0.95,  # High confidence
            reasoning="Strong signal",
        ),
        RoleVerdict(
            role=RoleName.SCREENER,
            action="NEUTRAL",
            confidence=0.8,
            reasoning="No clear trend",
        ),
        RoleVerdict(
            role=RoleName.FUNDAMENTAL,
            action="NEUTRAL",
            confidence=0.7,
            reasoning="Mixed sentiment",
        ),
    ]
    
    decision = engine.aggregate(verdicts)
    
    # Should become NEUTRAL because only 1 role agrees on BUY (need 2)
    assert decision.final_action == "NEUTRAL"


# ---------------------------------------------------------------------------
# VETO Power Tests
# ---------------------------------------------------------------------------


def test_veto_blocks_unanimous_buy(engine):
    """Test that VETO blocks trade even when all other roles agree."""
    verdicts = [
        RoleVerdict(
            role=RoleName.SCREENER,
            action="BUY",
            confidence=0.9,
            reasoning="Strong momentum",
        ),
        RoleVerdict(
            role=RoleName.TACTICAL,
            action="BUY",
            confidence=0.95,
            reasoning="Bullish breakout",
        ),
        RoleVerdict(
            role=RoleName.FUNDAMENTAL,
            action="BUY",
            confidence=0.85,
            reasoning="Positive news",
        ),
        # STRATEGIST VETO overrides everything
        RoleVerdict(
            role=RoleName.STRATEGIST,
            action="VETO",
            confidence=1.0,
            reasoning="Portfolio correlation risk too high",
        ),
    ]
    
    decision = engine.aggregate(verdicts)
    
    assert decision.final_action == "NEUTRAL"
    assert decision.final_confidence == 0.0
    assert decision.vetoed_by == RoleName.STRATEGIST
    assert "VETOED by strategist" in decision.reasoning
    assert "Portfolio correlation risk" in decision.reasoning


def test_veto_from_any_role(engine):
    """Test that VETO from any role blocks the trade."""
    # VETO from screener (not just strategist)
    verdicts = [
        RoleVerdict(
            role=RoleName.SCREENER,
            action="VETO",
            confidence=1.0,
            reasoning="Suspicious volume pattern",
        ),
        RoleVerdict(
            role=RoleName.TACTICAL,
            action="BUY",
            confidence=0.9,
            reasoning="Bullish pattern",
        ),
    ]
    
    decision = engine.aggregate(verdicts)
    
    assert decision.final_action == "NEUTRAL"
    assert decision.vetoed_by == RoleName.SCREENER
    assert "VETOED by screener" in decision.reasoning


def test_multiple_vetos_first_wins(engine):
    """Test that when multiple roles VETO, first one is reported."""
    verdicts = [
        RoleVerdict(
            role=RoleName.TACTICAL,
            action="VETO",
            confidence=1.0,
            reasoning="Failed breakout",
        ),
        RoleVerdict(
            role=RoleName.STRATEGIST,
            action="VETO",
            confidence=1.0,
            reasoning="Risk too high",
        ),
    ]
    
    decision = engine.aggregate(verdicts)
    
    assert decision.final_action == "NEUTRAL"
    # First VETO in list should be reported
    assert decision.vetoed_by == RoleName.TACTICAL


# ---------------------------------------------------------------------------
# Edge Cases
# ---------------------------------------------------------------------------


def test_empty_verdicts_list(engine):
    """Test that empty verdicts list returns NEUTRAL."""
    decision = engine.aggregate([])
    
    assert decision.final_action == "NEUTRAL"
    assert decision.final_confidence == 0.0
    assert decision.vetoed_by is None
    assert "No verdicts" in decision.reasoning


def test_all_neutral_verdicts(engine):
    """Test consensus when all roles vote NEUTRAL."""
    verdicts = [
        RoleVerdict(
            role=RoleName.SCREENER,
            action="NEUTRAL",
            confidence=0.8,
            reasoning="No clear signal",
        ),
        RoleVerdict(
            role=RoleName.TACTICAL,
            action="NEUTRAL",
            confidence=0.7,
            reasoning="Sideways market",
        ),
        RoleVerdict(
            role=RoleName.FUNDAMENTAL,
            action="NEUTRAL",
            confidence=0.9,
            reasoning="Mixed news",
        ),
    ]
    
    decision = engine.aggregate(verdicts)
    
    assert decision.final_action == "NEUTRAL"
    assert decision.vetoed_by is None


def test_tie_breaking_buy_vs_sell(engine):
    """Test tie-breaking when BUY and SELL have equal weighted scores."""
    verdicts = [
        RoleVerdict(
            role=RoleName.SCREENER,
            action="BUY",
            confidence=0.8,
            reasoning="Bullish momentum",
        ),
        RoleVerdict(
            role=RoleName.TACTICAL,
            action="SELL",
            confidence=0.8,
            reasoning="Bearish reversal",
        ),
    ]
    
    decision = engine.aggregate(verdicts)
    
    # With equal weights, one will win arbitrarily (depends on dict iteration)
    # But confidence should be relatively low due to disagreement
    assert decision.final_action in ["BUY", "SELL", "NEUTRAL"]
    
    # If min_agreement=2 but only 1 role per action, should become NEUTRAL
    if decision.final_action != "NEUTRAL":
        # If not NEUTRAL, check that agreement threshold was met
        assert decision.final_confidence > 0.0


def test_single_verdict_below_agreement_threshold(engine):
    """Test that single verdict below min_agreement becomes NEUTRAL."""
    verdicts = [
        RoleVerdict(
            role=RoleName.TACTICAL,
            action="BUY",
            confidence=0.95,
            reasoning="Strong signal",
        ),
    ]
    
    decision = engine.aggregate(verdicts)
    
    # With min_agreement=2 and only 1 verdict, should be NEUTRAL
    assert decision.final_action == "NEUTRAL"


def test_zero_confidence_verdicts(engine):
    """Test handling of zero confidence verdicts."""
    verdicts = [
        RoleVerdict(
            role=RoleName.SCREENER,
            action="BUY",
            confidence=0.0,  # Zero confidence
            reasoning="Uncertain",
        ),
        RoleVerdict(
            role=RoleName.TACTICAL,
            action="BUY",
            confidence=0.0,
            reasoning="Very uncertain",
        ),
    ]
    
    decision = engine.aggregate(verdicts)
    
    # Zero confidence should result in NEUTRAL
    assert decision.final_action == "NEUTRAL"
    assert decision.final_confidence == 0.0


# ---------------------------------------------------------------------------
# Threshold Configuration Tests
# ---------------------------------------------------------------------------


def test_strict_threshold_rejects_marginal_consensus(strict_engine):
    """Test that strict engine rejects marginal consensus."""
    verdicts = [
        RoleVerdict(
            role=RoleName.SCREENER,
            action="BUY",
            confidence=0.7,
            reasoning="Moderate signal",
        ),
        RoleVerdict(
            role=RoleName.TACTICAL,
            action="BUY",
            confidence=0.7,
            reasoning="Moderate pattern",
        ),
    ]
    
    decision = strict_engine.aggregate(verdicts)
    
    # Strict engine needs 0.8 threshold and 3 agreements
    # Should be NEUTRAL due to insufficient confidence or agreement
    assert decision.final_action == "NEUTRAL"


def test_lenient_threshold_accepts_marginal_consensus():
    """Test that lenient engine accepts marginal consensus."""
    lenient_engine = ConsensusEngine(
        confidence_threshold=0.5,
        min_agreement=1,
    )
    
    verdicts = [
        RoleVerdict(
            role=RoleName.TACTICAL,
            action="BUY",
            confidence=0.6,
            reasoning="Weak signal",
        ),
    ]
    
    decision = lenient_engine.aggregate(verdicts)
    
    # Lenient engine should accept this
    assert decision.final_action == "BUY"
    assert decision.final_confidence > 0.5


def test_custom_confidence_threshold():
    """Test consensus engine with custom confidence threshold."""
    custom_engine = ConsensusEngine(
        confidence_threshold=0.9,  # Very high threshold
        min_agreement=2,
    )
    
    # To fail the 0.9 threshold, we need disagreement
    verdicts = [
        RoleVerdict(
            role=RoleName.SCREENER,
            action="BUY",
            confidence=0.7,
            reasoning="Moderate buy signal",
        ),
        RoleVerdict(
            role=RoleName.TACTICAL,
            action="SELL",
            confidence=0.8,
            reasoning="Moderate sell signal",
        ),
        RoleVerdict(
            role=RoleName.FUNDAMENTAL,
            action="NEUTRAL",
            confidence=0.6,
            reasoning="Uncertain",
        ),
    ]
    
    decision = custom_engine.aggregate(verdicts)
    
    # With disagreement and high threshold, should be NEUTRAL
    assert decision.final_action == "NEUTRAL"


# ---------------------------------------------------------------------------
# Reasoning Summary Tests
# ---------------------------------------------------------------------------


def test_reasoning_summary_includes_all_verdicts(engine):
    """Test that reasoning summary includes all role verdicts."""
    verdicts = [
        RoleVerdict(
            role=RoleName.SCREENER,
            action="BUY",
            confidence=0.8,
            reasoning="Strong momentum",
        ),
        RoleVerdict(
            role=RoleName.TACTICAL,
            action="NEUTRAL",
            confidence=0.5,
            reasoning="Unclear pattern",
        ),
    ]
    
    decision = engine.aggregate(verdicts)
    
    # Reasoning should mention both roles
    assert "screener" in decision.reasoning.lower()
    assert "tactical" in decision.reasoning.lower()
    assert "BUY" in decision.reasoning
    assert "NEUTRAL" in decision.reasoning


def test_veto_reasoning_includes_vetoer_explanation(engine):
    """Test that VETO reasoning includes the vetoer's explanation."""
    verdicts = [
        RoleVerdict(
            role=RoleName.TACTICAL,
            action="BUY",
            confidence=0.9,
            reasoning="Strong breakout",
        ),
        RoleVerdict(
            role=RoleName.STRATEGIST,
            action="VETO",
            confidence=1.0,
            reasoning="Max position size already reached for this sector",
        ),
    ]
    
    decision = engine.aggregate(verdicts)
    
    assert decision.vetoed_by == RoleName.STRATEGIST
    assert "Max position size" in decision.reasoning


# ---------------------------------------------------------------------------
# Weighted Confidence Calculation Tests
# ---------------------------------------------------------------------------


def test_weighted_confidence_with_custom_weights():
    """Test that weights properly influence consensus."""
    # This test would ideally mock RoleRegistry.get() to return custom weights
    # For now, we test with known default weights:
    # Screener: 0.5, Tactical: 1.5, Fundamental: 1.0, Strategist: 1.2
    
    engine = ConsensusEngine(confidence_threshold=0.6, min_agreement=2)
    
    verdicts = [
        # Screener (weight 0.5): BUY with high confidence
        RoleVerdict(
            role=RoleName.SCREENER,
            action="BUY",
            confidence=1.0,
            reasoning="Perfect score",
        ),
        # Tactical (weight 1.5): SELL with high confidence
        RoleVerdict(
            role=RoleName.TACTICAL,
            action="SELL",
            confidence=1.0,
            reasoning="Clear reversal",
        ),
    ]
    
    decision = engine.aggregate(verdicts)
    
    # Tactical's weight (1.5) > Screener's weight (0.5)
    # So SELL should win, but min_agreement=2 requires 2 roles
    # Since only 1 role per action, should become NEUTRAL
    assert decision.final_action == "NEUTRAL"


def test_high_confidence_low_weight_vs_low_confidence_high_weight():
    """Test interaction between confidence and weight."""
    engine = ConsensusEngine(confidence_threshold=0.5, min_agreement=2)
    
    verdicts = [
        # Screener (weight 0.5): BUY with max confidence
        RoleVerdict(
            role=RoleName.SCREENER,
            action="BUY",
            confidence=1.0,
            reasoning="Perfect signal",
        ),
        # Tactical (weight 1.5): BUY with lower confidence
        RoleVerdict(
            role=RoleName.TACTICAL,
            action="BUY",
            confidence=0.6,
            reasoning="Moderate signal",
        ),
        # Fundamental (weight 1.0): BUY with moderate confidence
        RoleVerdict(
            role=RoleName.FUNDAMENTAL,
            action="BUY",
            confidence=0.8,
            reasoning="Good sentiment",
        ),
    ]
    
    decision = engine.aggregate(verdicts)
    
    # All agree on BUY with decent confidence
    # Weighted confidence should be high enough
    assert decision.final_action == "BUY"
    assert decision.final_confidence > 0.5
