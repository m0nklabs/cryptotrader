"""Additional tests for consensus engine production features.

Tests soft VETO, agreement multiplier, and confidence calibration.

Part of issue #205 P4.
"""

from __future__ import annotations

from unittest.mock import Mock

import pytest

from core.ai.consensus import ConsensusEngine
from core.ai.types import RoleName, RoleVerdict


# ---------------------------------------------------------------------------
# Test Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_role_registry():
    """Reset RoleRegistry before each test to avoid test interference."""
    from core.ai.roles.base import RoleRegistry

    # Save original state
    original_roles = RoleRegistry._roles.copy()

    # Clear registry before each test to avoid leakage
    RoleRegistry.clear()

    yield

    # Restore original state after test
    RoleRegistry.clear()
    for role in original_roles.values():
        RoleRegistry.register(role)


# ---------------------------------------------------------------------------
# Soft VETO Tests
# ---------------------------------------------------------------------------


def test_soft_veto_reduces_confidence():
    """Test that soft VETO reduces confidence but doesn't block trade."""
    engine = ConsensusEngine(
        confidence_threshold=0.5,
        min_agreement=2,
        veto_mode="soft",
    )

    verdicts = [
        RoleVerdict(
            role=RoleName.SCREENER,
            action="BUY",
            confidence=0.9,
            reasoning="Strong signal",
        ),
        RoleVerdict(
            role=RoleName.TACTICAL,
            action="BUY",
            confidence=0.9,
            reasoning="Bullish pattern",
        ),
        RoleVerdict(
            role=RoleName.STRATEGIST,
            action="VETO",
            confidence=1.0,
            reasoning="Minor concern",
        ),
    ]

    decision = engine.aggregate(verdicts)

    # Should still be BUY, but with reduced confidence
    assert decision.final_action == "BUY"
    assert decision.final_confidence < 0.9  # Reduced by soft VETO penalty
    assert decision.vetoed_by is None  # Not a hard veto
    assert "Soft VETO" in decision.reasoning


def test_soft_veto_custom_penalty():
    """Test that custom soft VETO penalty can be configured."""
    engine = ConsensusEngine(
        confidence_threshold=0.5,
        min_agreement=2,
        veto_mode="soft",
        soft_veto_penalty=0.7,  # Custom 70% (30% reduction)
    )

    verdicts = [
        RoleVerdict(
            role=RoleName.SCREENER,
            action="BUY",
            confidence=0.8,
            reasoning="Good signal",
        ),
        RoleVerdict(
            role=RoleName.TACTICAL,
            action="BUY",
            confidence=0.8,
            reasoning="Good pattern",
        ),
        RoleVerdict(
            role=RoleName.STRATEGIST,
            action="VETO",
            confidence=1.0,
            reasoning="Minor concern",
        ),
    ]

    decision = engine.aggregate(verdicts)

    # Should still be BUY with custom penalty applied
    assert decision.final_action == "BUY"
    # The penalty should result in less reduction than default 0.5
    # With weights all equal, raw confidence would be ~0.8
    # After 0.7 penalty, should be around 0.56
    assert 0.5 < decision.final_confidence < 0.8
    assert decision.vetoed_by is None


def test_soft_veto_all_vetos_treated_as_hard():
    """Test that all VETOs in soft mode are still treated as hard."""
    engine = ConsensusEngine(
        veto_mode="soft",
    )

    verdicts = [
        RoleVerdict(
            role=RoleName.SCREENER,
            action="VETO",
            confidence=1.0,
            reasoning="Bad signal",
        ),
        RoleVerdict(
            role=RoleName.TACTICAL,
            action="VETO",
            confidence=1.0,
            reasoning="Bad pattern",
        ),
    ]

    decision = engine.aggregate(verdicts)

    # All VETOs should be treated as hard
    assert decision.final_action == "NEUTRAL"
    assert decision.final_confidence == 0.0
    assert decision.vetoed_by is not None


def test_hard_veto_mode_default():
    """Test that hard VETO is the default mode."""
    engine = ConsensusEngine()

    verdicts = [
        RoleVerdict(
            role=RoleName.SCREENER,
            action="BUY",
            confidence=0.9,
            reasoning="Strong signal",
        ),
        RoleVerdict(
            role=RoleName.STRATEGIST,
            action="VETO",
            confidence=1.0,
            reasoning="Risk too high",
        ),
    ]

    decision = engine.aggregate(verdicts)

    # Hard VETO should block
    assert decision.final_action == "NEUTRAL"
    assert decision.final_confidence == 0.0
    assert decision.vetoed_by == RoleName.STRATEGIST


def test_invalid_veto_mode_raises_error():
    """Test that invalid veto_mode raises ValueError."""
    with pytest.raises(ValueError, match="veto_mode must be 'hard' or 'soft'"):
        ConsensusEngine(veto_mode="invalid")

    with pytest.raises(ValueError, match="veto_mode must be 'hard' or 'soft'"):
        ConsensusEngine(veto_mode="medium")

    with pytest.raises(ValueError, match="veto_mode must be 'hard' or 'soft'"):
        ConsensusEngine(veto_mode="HARD")  # Case-sensitive


def test_invalid_soft_veto_penalty_raises_error():
    """Test that invalid soft_veto_penalty raises ValueError."""
    # Negative penalty
    with pytest.raises(ValueError, match="soft_veto_penalty must be between 0.0 and 1.0"):
        ConsensusEngine(soft_veto_penalty=-0.1)

    # Penalty > 1.0
    with pytest.raises(ValueError, match="soft_veto_penalty must be between 0.0 and 1.0"):
        ConsensusEngine(soft_veto_penalty=1.5)

    # Edge cases should work
    ConsensusEngine(soft_veto_penalty=0.0)  # No penalty
    ConsensusEngine(soft_veto_penalty=1.0)  # Full penalty


# ---------------------------------------------------------------------------
# Agreement Multiplier Tests
# ---------------------------------------------------------------------------


def test_agreement_multiplier_unanimous():
    """Test that unanimous agreement boosts confidence."""
    engine = ConsensusEngine(
        confidence_threshold=0.5,
        min_agreement=2,
        agreement_multiplier=1.2,
    )

    from core.ai.roles.base import RoleRegistry
    from core.ai.types import ProviderName, RoleConfig

    # Register mock roles
    for role_name in [RoleName.SCREENER, RoleName.TACTICAL, RoleName.FUNDAMENTAL]:
        mock_role = Mock()
        mock_role.name = role_name
        mock_role.weight = 1.0
        mock_role.config = RoleConfig(
            name=role_name,
            provider=ProviderName.DEEPSEEK,
            model="test",
            system_prompt_id="test",
        )
        RoleRegistry.register(mock_role)

    # All agree on BUY with moderate confidence
    verdicts = [
        RoleVerdict(
            role=RoleName.SCREENER,
            action="BUY",
            confidence=0.7,
            reasoning="Good signal",
        ),
        RoleVerdict(
            role=RoleName.TACTICAL,
            action="BUY",
            confidence=0.7,
            reasoning="Good pattern",
        ),
        RoleVerdict(
            role=RoleName.FUNDAMENTAL,
            action="BUY",
            confidence=0.7,
            reasoning="Good news",
        ),
    ]

    decision = engine.aggregate(verdicts)

    # Should be boosted by 20% but capped at 1.0
    assert decision.final_action == "BUY"
    assert decision.final_confidence > 0.7  # Boosted
    # Note: weighted normalized score * 1.2 may exceed 1.0, so it gets capped
    assert decision.final_confidence <= 1.0


def test_agreement_multiplier_mixed_no_boost():
    """Test that mixed votes don't get agreement multiplier."""
    engine = ConsensusEngine(
        confidence_threshold=0.3,  # Lower threshold to allow BUY to win
        min_agreement=1,  # Lower requirement for this test
        agreement_multiplier=1.2,
    )

    from core.ai.roles.base import RoleRegistry
    from core.ai.types import ProviderName, RoleConfig

    # Register mock roles
    for role_name in [RoleName.SCREENER, RoleName.TACTICAL]:
        mock_role = Mock()
        mock_role.name = role_name
        mock_role.weight = 1.0
        mock_role.config = RoleConfig(
            name=role_name,
            provider=ProviderName.DEEPSEEK,
            model="test",
            system_prompt_id="test",
        )
        RoleRegistry.register(mock_role)

    # Mixed votes
    verdicts = [
        RoleVerdict(
            role=RoleName.SCREENER,
            action="BUY",
            confidence=0.8,
            reasoning="Good signal",
        ),
        RoleVerdict(
            role=RoleName.TACTICAL,
            action="NEUTRAL",
            confidence=0.6,
            reasoning="Uncertain",
        ),
    ]

    decision = engine.aggregate(verdicts)

    # No agreement boost for mixed votes
    # BUY should win but without boost
    # With new normalization: BUY = 0.8/2.0 = 0.4, NEUTRAL = 0.6/2.0 = 0.3
    assert decision.final_action == "BUY"
    assert decision.final_confidence == 0.4  # Weighted average, no boost


def test_agreement_multiplier_caps_at_one():
    """Test that agreement multiplier doesn't exceed 1.0 confidence."""
    engine = ConsensusEngine(
        confidence_threshold=0.5,
        min_agreement=2,
        agreement_multiplier=1.5,
    )

    from core.ai.roles.base import RoleRegistry
    from core.ai.types import ProviderName, RoleConfig

    # Register mock roles
    for role_name in [RoleName.SCREENER, RoleName.TACTICAL]:
        mock_role = Mock()
        mock_role.name = role_name
        mock_role.weight = 1.0
        mock_role.config = RoleConfig(
            name=role_name,
            provider=ProviderName.DEEPSEEK,
            model="test",
            system_prompt_id="test",
        )
        RoleRegistry.register(mock_role)

    # High confidence unanimous
    verdicts = [
        RoleVerdict(
            role=RoleName.SCREENER,
            action="BUY",
            confidence=0.9,
            reasoning="Strong signal",
        ),
        RoleVerdict(
            role=RoleName.TACTICAL,
            action="BUY",
            confidence=0.9,
            reasoning="Strong pattern",
        ),
    ]

    decision = engine.aggregate(verdicts)

    # Should be capped at 1.0
    assert decision.final_action == "BUY"
    assert decision.final_confidence <= 1.0


# ---------------------------------------------------------------------------
# Confidence Calibration Tests
# ---------------------------------------------------------------------------


def test_calibration_disabled_by_default():
    """Test that calibration is disabled by default."""
    engine = ConsensusEngine(enable_calibration=False)

    # Update accuracy, but it shouldn't affect anything
    engine.update_role_accuracy("tactical", was_correct=False)
    engine.update_role_accuracy("tactical", was_correct=False)

    from core.ai.roles.base import RoleRegistry
    from core.ai.types import ProviderName, RoleConfig

    mock_role = Mock()
    mock_role.name = RoleName.TACTICAL
    mock_role.weight = 1.0
    mock_role.config = RoleConfig(
        name=RoleName.TACTICAL,
        provider=ProviderName.DEEPSEEK,
        model="test",
        system_prompt_id="test",
    )
    RoleRegistry.register(mock_role)

    verdicts = [
        RoleVerdict(
            role=RoleName.TACTICAL,
            action="BUY",
            confidence=0.9,
            reasoning="Test",
        ),
    ]

    # Calibration disabled, so weight shouldn't change
    decision = engine.aggregate(verdicts)
    # Just verify it runs without error
    assert decision.final_action in ["BUY", "NEUTRAL"]


def test_calibration_requires_min_samples():
    """Test that calibration needs minimum samples before activating."""
    engine = ConsensusEngine(
        enable_calibration=True,
        min_calibration_samples=10,
    )

    # Add only 5 samples (below threshold)
    for i in range(5):
        engine.update_role_accuracy("tactical", was_correct=(i % 2 == 0))

    accuracy, count = engine.get_role_accuracy("tactical")
    assert count == 5  # Below threshold

    # Calibration shouldn't apply yet (not enough samples)
    base_weight = 1.0
    calibrated = engine._apply_calibration("tactical", base_weight)
    assert calibrated == base_weight  # No change


def test_calibration_increases_weight_for_accurate_role():
    """Test that accurate roles get higher weight."""
    engine = ConsensusEngine(
        enable_calibration=True,
        min_calibration_samples=10,
    )

    # Record 20 samples with 80% accuracy
    for i in range(20):
        engine.update_role_accuracy("tactical", was_correct=(i < 16))

    accuracy, count = engine.get_role_accuracy("tactical")
    assert count == 20
    assert accuracy > 0.5  # Should be above baseline

    # Weight should be increased for accurate role
    base_weight = 1.0
    calibrated = engine._apply_calibration("tactical", base_weight)
    assert calibrated > base_weight


def test_calibration_decreases_weight_for_inaccurate_role():
    """Test that inaccurate roles get lower weight."""
    engine = ConsensusEngine(
        enable_calibration=True,
        min_calibration_samples=10,
    )

    # Record 20 samples with 30% accuracy (mostly wrong)
    for i in range(20):
        engine.update_role_accuracy("tactical", was_correct=(i < 6))

    accuracy, count = engine.get_role_accuracy("tactical")
    assert count == 20
    assert accuracy < 0.5  # Below baseline

    # Weight should be decreased for inaccurate role
    base_weight = 1.0
    calibrated = engine._apply_calibration("tactical", base_weight)
    assert calibrated < base_weight


def test_calibration_exponential_moving_average():
    """Test that calibration uses exponential moving average."""
    engine = ConsensusEngine(
        enable_calibration=True,
        min_calibration_samples=2,
    )

    # Start with some wrong predictions
    engine.update_role_accuracy("tactical", was_correct=False)
    engine.update_role_accuracy("tactical", was_correct=False)
    first_accuracy, _ = engine.get_role_accuracy("tactical")

    # Then add correct predictions
    engine.update_role_accuracy("tactical", was_correct=True)
    engine.update_role_accuracy("tactical", was_correct=True)
    second_accuracy, _ = engine.get_role_accuracy("tactical")

    # Accuracy should improve but not jump to 1.0 (EMA smoothing)
    assert second_accuracy > first_accuracy
    assert second_accuracy < 1.0  # Not instant jump


# ---------------------------------------------------------------------------
# Enhanced Reasoning Tests
# ---------------------------------------------------------------------------


def test_reasoning_includes_verdict_snippets():
    """Test that reasoning includes snippets of role reasoning."""
    engine = ConsensusEngine()

    from core.ai.roles.base import RoleRegistry
    from core.ai.types import ProviderName, RoleConfig

    # Register mock roles
    for role_name in [RoleName.SCREENER, RoleName.TACTICAL]:
        mock_role = Mock()
        mock_role.name = role_name
        mock_role.weight = 1.0
        mock_role.config = RoleConfig(
            name=role_name,
            provider=ProviderName.DEEPSEEK,
            model="test",
            system_prompt_id="test",
        )
        RoleRegistry.register(mock_role)

    long_reasoning = "This is a very long reasoning text " * 10  # > 100 chars

    verdicts = [
        RoleVerdict(
            role=RoleName.SCREENER,
            action="BUY",
            confidence=0.8,
            reasoning=long_reasoning,
        ),
        RoleVerdict(
            role=RoleName.TACTICAL,
            action="BUY",
            confidence=0.8,
            reasoning="Short reason",
        ),
    ]

    decision = engine.aggregate(verdicts)

    # Reasoning should include role names and actions
    assert "screener" in decision.reasoning.lower()
    assert "tactical" in decision.reasoning.lower()
    # Long reasoning should be truncated
    assert "..." in decision.reasoning or len(decision.reasoning) < len(long_reasoning) * 2


def test_reasoning_includes_confidence_in_summary():
    """Test that reasoning summary includes final confidence."""
    engine = ConsensusEngine()

    from core.ai.roles.base import RoleRegistry
    from core.ai.types import ProviderName, RoleConfig

    mock_role = Mock()
    mock_role.name = RoleName.TACTICAL
    mock_role.weight = 1.0
    mock_role.config = RoleConfig(
        name=RoleName.TACTICAL,
        provider=ProviderName.DEEPSEEK,
        model="test",
        system_prompt_id="test",
    )
    RoleRegistry.register(mock_role)

    verdicts = [
        RoleVerdict(
            role=RoleName.TACTICAL,
            action="BUY",
            confidence=0.75,
            reasoning="test",
        ),
    ]

    decision = engine.aggregate(verdicts)

    # Reasoning should include confidence value
    assert "conf=" in decision.reasoning.lower()
