"""Unit tests for the LLM Router with circuit breaker, timeouts, and partial evaluation.

Tests router resilience features: circuit breaker, timeouts, partial evaluation.

Part of issue #205 P4.
"""

from __future__ import annotations

import asyncio
from unittest.mock import Mock, patch

import pytest

from core.ai.consensus import ConsensusEngine
from core.ai.router import CircuitBreaker, CircuitState, LLMRouter
from core.ai.types import (
    AIResponse,
    ProviderName,
    RoleName,
    RoleVerdict,
)


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


@pytest.fixture
def router():
    """Default router with standard configuration."""
    return LLMRouter(
        consensus_engine=ConsensusEngine(),
        min_roles_required=2,
        enable_circuit_breaker=True,
    )


# ---------------------------------------------------------------------------
# Circuit Breaker Tests
# ---------------------------------------------------------------------------


def test_circuit_breaker_initial_state():
    """Test that circuit breaker starts in CLOSED state."""
    breaker = CircuitBreaker(provider=ProviderName.DEEPSEEK)

    assert breaker.state == CircuitState.CLOSED
    assert breaker.failure_count == 0
    assert breaker.should_allow_request()


def test_circuit_breaker_opens_after_threshold():
    """Test that circuit breaker opens after consecutive failures."""
    breaker = CircuitBreaker(provider=ProviderName.DEEPSEEK)

    # Record 4 failures (below threshold)
    for _ in range(4):
        breaker.record_failure()

    assert breaker.state == CircuitState.CLOSED
    assert breaker.should_allow_request()

    # 5th failure should open circuit
    breaker.record_failure()
    assert breaker.state == CircuitState.OPEN
    assert not breaker.should_allow_request()


def test_circuit_breaker_resets_on_success():
    """Test that successful requests reset failure count."""
    breaker = CircuitBreaker(provider=ProviderName.DEEPSEEK)

    # Record some failures
    breaker.record_failure()
    breaker.record_failure()
    assert breaker.failure_count == 2

    # Success should reset
    breaker.record_success()
    assert breaker.failure_count == 0


def test_circuit_breaker_half_open_to_closed():
    """Test transition from HALF_OPEN to CLOSED after successful test."""
    breaker = CircuitBreaker(provider=ProviderName.DEEPSEEK)

    # Force to HALF_OPEN state
    breaker.state = CircuitState.HALF_OPEN
    breaker.half_open_successes = 0

    # First success should close the circuit (HALF_OPEN_LIMIT = 1)
    breaker.record_success()
    assert breaker.state == CircuitState.CLOSED
    assert breaker.failure_count == 0


def test_circuit_breaker_half_open_to_open():
    """Test that failure in HALF_OPEN state reopens circuit."""
    breaker = CircuitBreaker(provider=ProviderName.DEEPSEEK)

    # Force to HALF_OPEN state
    breaker.state = CircuitState.HALF_OPEN

    # Failure should reopen
    breaker.record_failure()
    assert breaker.state == CircuitState.OPEN


@pytest.mark.asyncio
async def test_router_respects_circuit_breaker(router):
    """Test that router skips roles when circuit is open."""
    from core.ai.roles.base import RoleRegistry
    from core.ai.types import ProviderName, RoleConfig

    # Register mock role
    mock_role = Mock()
    mock_role.name = RoleName.TACTICAL
    mock_role.weight = 1.0
    mock_role.config = RoleConfig(
        name=RoleName.TACTICAL,
        provider=ProviderName.DEEPSEEK,
        model="test",
        system_prompt_id="test",
        enabled=True,
    )

    # Mock evaluate to raise exception
    async def failing_evaluate(*args, **kwargs):
        raise Exception("Provider down")

    mock_role.evaluate = failing_evaluate
    RoleRegistry.register(mock_role)

    # Open the circuit manually
    breaker = router._get_circuit_breaker(ProviderName.DEEPSEEK)
    for _ in range(5):
        breaker.record_failure()

    assert breaker.state == CircuitState.OPEN

    # Evaluation should skip the role
    with patch("core.ai.prompts.registry.PromptRegistry.get_active", return_value=Mock(content="test")):
        decision = await router.evaluate_opportunity(
            symbol="BTC/USD",
            timeframe="1h",
        )

    # Should return NEUTRAL due to insufficient roles
    assert decision.final_action == "NEUTRAL"
    assert "Insufficient roles" in decision.reasoning


# ---------------------------------------------------------------------------
# Timeout Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_router_timeout_slow_role(router):
    """Test that router times out slow roles."""
    from core.ai.roles.base import RoleRegistry
    from core.ai.types import ProviderName, RoleConfig

    # Register mock role that takes too long
    mock_role = Mock()
    mock_role.name = RoleName.TACTICAL
    mock_role.weight = 1.0
    mock_role.config = RoleConfig(
        name=RoleName.TACTICAL,
        provider=ProviderName.DEEPSEEK,
        model="test",
        system_prompt_id="test",
        enabled=True,
    )

    # Mock evaluate to sleep longer than timeout
    async def slow_evaluate(*args, **kwargs):
        await asyncio.sleep(2.0)  # Longer than we'll set timeout
        return (
            AIResponse(
                role=RoleName.TACTICAL,
                provider=ProviderName.DEEPSEEK,
                model="test",
                raw_text="{}",
            ),
            RoleVerdict(
                role=RoleName.TACTICAL,
                action="BUY",
                confidence=0.8,
                reasoning="test",
            ),
        )

    mock_role.evaluate = slow_evaluate
    RoleRegistry.register(mock_role)

    # Set short timeout for testing
    router._role_timeouts[RoleName.TACTICAL] = 0.5

    with patch("core.ai.prompts.registry.PromptRegistry.get_active", return_value=Mock(content="test")):
        decision = await router.evaluate_opportunity(
            symbol="BTC/USD",
            timeframe="1h",
        )

    # Should return NEUTRAL due to insufficient roles (timed out)
    assert decision.final_action == "NEUTRAL"
    assert "Insufficient roles" in decision.reasoning


# ---------------------------------------------------------------------------
# Partial Evaluation Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_router_partial_evaluation_one_role_fails():
    """Test partial evaluation when one role fails."""
    from core.ai.roles.base import RoleRegistry
    from core.ai.types import ProviderName, RoleConfig

    router = LLMRouter(min_roles_required=2)

    # Register 3 mock roles
    for i, role_name in enumerate([RoleName.SCREENER, RoleName.TACTICAL, RoleName.FUNDAMENTAL]):
        mock_role = Mock()
        mock_role.name = role_name
        mock_role.weight = 1.0
        mock_role.config = RoleConfig(
            name=role_name,
            provider=ProviderName.DEEPSEEK,
            model="test",
            system_prompt_id="test",
            enabled=True,
        )

        # First role fails, others succeed
        if i == 0:

            async def failing_evaluate(*args, **kwargs):
                raise Exception("Provider error")

            mock_role.evaluate = failing_evaluate
        else:
            # Use closure to capture role_name properly
            def make_success_eval(rn):
                async def successful_evaluate(*args, **kwargs):
                    return (
                        AIResponse(
                            role=rn,
                            provider=ProviderName.DEEPSEEK,
                            model="test",
                            raw_text="{}",
                        ),
                        RoleVerdict(
                            role=rn,
                            action="BUY",
                            confidence=0.8,
                            reasoning="test",
                        ),
                    )

                return successful_evaluate

            mock_role.evaluate = make_success_eval(role_name)

        RoleRegistry.register(mock_role)

    with patch("core.ai.prompts.registry.PromptRegistry.get_active", return_value=Mock(content="test")):
        decision = await router.evaluate_opportunity(
            symbol="BTC/USD",
            timeframe="1h",
        )

    # Should still get BUY decision from 2 successful roles
    assert decision.final_action == "BUY"
    assert len(decision.verdicts) == 2


@pytest.mark.asyncio
async def test_router_partial_evaluation_insufficient_roles():
    """Test that router returns NEUTRAL when too few roles respond."""
    from core.ai.roles.base import RoleRegistry
    from core.ai.types import ProviderName, RoleConfig

    router = LLMRouter(min_roles_required=2)

    # Register 2 roles, but both fail
    for role_name in [RoleName.SCREENER, RoleName.TACTICAL]:
        mock_role = Mock()
        mock_role.name = role_name
        mock_role.weight = 1.0
        mock_role.config = RoleConfig(
            name=role_name,
            provider=ProviderName.DEEPSEEK,
            model="test",
            system_prompt_id="test",
            enabled=True,
        )

        async def failing_evaluate(*args, **kwargs):
            raise Exception("Provider error")

        mock_role.evaluate = failing_evaluate

        RoleRegistry.register(mock_role)

    with patch("core.ai.prompts.registry.PromptRegistry.get_active", return_value=Mock(content="test")):
        decision = await router.evaluate_opportunity(
            symbol="BTC/USD",
            timeframe="1h",
        )

    # Should return NEUTRAL due to insufficient roles
    assert decision.final_action == "NEUTRAL"
    assert decision.final_confidence == 0.0
    assert "Insufficient roles" in decision.reasoning


# ---------------------------------------------------------------------------
# Router Integration Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_router_get_circuit_breaker_status(router):
    """Test getting circuit breaker status."""
    # Trigger some circuit breakers
    breaker1 = router._get_circuit_breaker(ProviderName.DEEPSEEK)
    breaker1.record_failure()
    breaker1.record_failure()

    breaker2 = router._get_circuit_breaker(ProviderName.OPENAI)
    for _ in range(5):
        breaker2.record_failure()

    status = router.get_circuit_breaker_status()

    assert ProviderName.DEEPSEEK.value in status
    assert status[ProviderName.DEEPSEEK.value]["failure_count"] == 2
    assert status[ProviderName.DEEPSEEK.value]["state"] == CircuitState.CLOSED.value

    assert ProviderName.OPENAI.value in status
    assert status[ProviderName.OPENAI.value]["state"] == CircuitState.OPEN.value


def test_router_reset_circuit_breaker(router):
    """Test manually resetting a circuit breaker."""
    # Open a circuit
    breaker = router._get_circuit_breaker(ProviderName.DEEPSEEK)
    for _ in range(5):
        breaker.record_failure()
    assert breaker.state == CircuitState.OPEN

    # Reset it
    router.reset_circuit_breaker(ProviderName.DEEPSEEK)
    assert breaker.state == CircuitState.CLOSED
    assert breaker.failure_count == 0


@pytest.mark.asyncio
async def test_router_usage_tracking(router):
    """Test that router tracks usage in memory."""
    from core.ai.roles.base import RoleRegistry
    from core.ai.types import ProviderName, RoleConfig

    # Register mock role
    mock_role = Mock()
    mock_role.name = RoleName.TACTICAL
    mock_role.weight = 1.0
    mock_role.config = RoleConfig(
        name=RoleName.TACTICAL,
        provider=ProviderName.DEEPSEEK,
        model="test",
        system_prompt_id="test",
        enabled=True,
    )

    async def successful_evaluate(*args, **kwargs):
        return (
            AIResponse(
                role=RoleName.TACTICAL,
                provider=ProviderName.DEEPSEEK,
                model="test",
                raw_text="{}",
                tokens_in=100,
                tokens_out=50,
                cost_usd=0.001,
                latency_ms=500.0,
            ),
            RoleVerdict(
                role=RoleName.TACTICAL,
                action="BUY",
                confidence=0.8,
                reasoning="test",
            ),
        )

    mock_role.evaluate = successful_evaluate
    RoleRegistry.register(mock_role)

    # Clear usage log
    router.clear_usage_log()

    with patch("core.ai.prompts.registry.PromptRegistry.get_active", return_value=Mock(content="test")):
        await router.evaluate_opportunity(
            symbol="BTC/USD",
            timeframe="1h",
        )

    # Check usage log
    usage_log = router.get_usage_log()
    assert len(usage_log) == 1
    assert usage_log[0].role == RoleName.TACTICAL
    assert usage_log[0].provider == ProviderName.DEEPSEEK
    assert usage_log[0].tokens_in == 100
    assert usage_log[0].tokens_out == 50
    assert usage_log[0].cost_usd == 0.001
    assert usage_log[0].success is True
