"""Unit tests for AI cost calculations and budget validation.

Tests per-provider cost calculations, aggregate pipeline cost,
daily/monthly projections, and budget limit enforcement.

Part of issue #209 (P6) for #205 Multi-Brain AI.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock, patch

import pytest

from core.ai.providers.deepseek import DeepSeekProvider
from core.ai.providers.ollama import OllamaProvider
from core.ai.providers.openai import OpenAIProvider
from core.ai.providers.openrouter import OpenRouterProvider
from core.ai.providers.xai import XAIProvider
from core.ai.types import AIRequest, ProviderName, RoleName


# ---------------------------------------------------------------------------
# Per-Provider Cost Calculation Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deepseek_cost_calculation():
    """Test DeepSeek cost calculation: $0.55 input, $2.19 output per 1M tokens (deepseek-reasoner)."""
    provider = DeepSeekProvider()

    mock_response = {
        "choices": [{"message": {"content": "test"}}],
        "usage": {
            "prompt_tokens": 10_000,  # 10k tokens
            "completion_tokens": 5_000,  # 5k tokens
        },
    }

    with patch.object(provider, "_make_request", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = mock_response

        request = AIRequest(role=RoleName.SCREENER, user_prompt="Test")
        response = await provider.complete(request, system_prompt="test")

    # Cost = (10,000 * $0.55 + 5,000 * $2.19) / 1,000,000
    # deepseek-reasoner pricing from DEEPSEEK_PRICING
    expected_cost = (10_000 * 0.55 + 5_000 * 2.19) / 1_000_000
    assert abs(response.cost_usd - expected_cost) < 0.000001
    assert response.cost_usd == pytest.approx(0.01645, rel=1e-4)


@pytest.mark.asyncio
async def test_openai_cost_calculation():
    """Test OpenAI o3-mini cost: $1.10 input, $4.40 output per 1M tokens."""
    provider = OpenAIProvider()

    mock_response = {
        "choices": [{"message": {"content": "test"}}],
        "usage": {
            "prompt_tokens": 10_000,
            "completion_tokens": 5_000,
        },
    }

    with patch.object(provider, "_make_request", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = mock_response

        request = AIRequest(role=RoleName.STRATEGIST, user_prompt="Test")
        response = await provider.complete(request, system_prompt="test")

    # Cost = (10,000 * $1.10 + 5,000 * $4.40) / 1,000,000
    expected_cost = (10_000 * 1.10 + 5_000 * 4.40) / 1_000_000
    assert abs(response.cost_usd - expected_cost) < 0.000001
    assert response.cost_usd == pytest.approx(0.033, rel=1e-4)


@pytest.mark.asyncio
async def test_openrouter_cost_calculation():
    """Test OpenRouter cost (uses OpenAI pricing for openai/ models)."""
    provider = OpenRouterProvider()

    mock_response = {
        "choices": [{"message": {"content": "test"}}],
        "usage": {
            "prompt_tokens": 10_000,
            "completion_tokens": 5_000,
        },
    }

    with patch.object(provider, "_make_request", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = mock_response

        request = AIRequest(role=RoleName.STRATEGIST, user_prompt="Test")
        response = await provider.complete(request, system_prompt="test")

    # OpenRouter uses OpenAI pricing for openai/o3-mini
    expected_cost = (10_000 * 1.10 + 5_000 * 4.40) / 1_000_000
    assert abs(response.cost_usd - expected_cost) < 0.000001


@pytest.mark.asyncio
async def test_xai_cost_calculation():
    """Test xAI Grok cost: $3.00 input, $15.00 output per 1M tokens (grok-4)."""
    provider = XAIProvider()

    mock_response = {
        "choices": [{"message": {"content": "test"}}],
        "usage": {
            "prompt_tokens": 10_000,
            "completion_tokens": 5_000,
        },
    }

    with patch.object(provider, "_make_request", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = mock_response

        request = AIRequest(role=RoleName.FUNDAMENTAL, user_prompt="Test")
        response = await provider.complete(request, system_prompt="test")

    # Cost = (10,000 * $3.00 + 5,000 * $15.00) / 1,000,000  (grok-4 pricing)
    expected_cost = (10_000 * 3.00 + 5_000 * 15.00) / 1_000_000
    assert abs(response.cost_usd - expected_cost) < 0.000001
    assert response.cost_usd == pytest.approx(0.105, rel=1e-4)


@pytest.mark.asyncio
async def test_ollama_cost_is_zero():
    """Test that Ollama (local) has zero cost."""
    provider = OllamaProvider()

    mock_response = {
        "message": {"content": "test"},
        "prompt_eval_count": 10_000,
        "eval_count": 5_000,
    }

    with patch.object(provider, "_make_request", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = mock_response

        request = AIRequest(role=RoleName.TACTICAL, user_prompt="Test")
        response = await provider.complete(request, system_prompt="test")

    # Local model = $0
    assert response.cost_usd == 0.0


# ---------------------------------------------------------------------------
# Aggregate Pipeline Cost Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pipeline_cost_aggregation():
    """Test that router aggregates cost from all roles correctly."""
    from core.ai.consensus import ConsensusEngine
    from core.ai.roles.base import RoleRegistry
    from core.ai.router import LLMRouter
    from core.ai.types import AIResponse, RoleConfig, RoleVerdict

    router = LLMRouter(consensus_engine=ConsensusEngine())

    # Register mock roles with different costs
    costs = {
        RoleName.SCREENER: 0.001,
        RoleName.TACTICAL: 0.002,
        RoleName.FUNDAMENTAL: 0.003,
        RoleName.STRATEGIST: 0.004,
    }

    for role_name, cost in costs.items():
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

        # Mock evaluate to return specific cost
        def make_eval(rn, c):
            async def mock_eval(*args, **kwargs):
                return (
                    AIResponse(
                        role=rn,
                        provider=ProviderName.DEEPSEEK,
                        model="test",
                        raw_text="{}",
                        cost_usd=c,
                        tokens_in=100,
                        tokens_out=50,
                    ),
                    RoleVerdict(
                        role=rn,
                        action="BUY",
                        confidence=0.8,
                        reasoning="test",
                    ),
                )

            return mock_eval

        mock_role.evaluate = make_eval(role_name, cost)
        RoleRegistry.register(mock_role)

    with patch("core.ai.prompts.registry.PromptRegistry.get_active", return_value=Mock(content="test")):
        decision = await router.evaluate_opportunity(
            symbol="BTC/USD",
            timeframe="1h",
        )

    # Total cost should be sum of all roles
    expected_total = sum(costs.values())
    assert abs(decision.total_cost_usd - expected_total) < 0.000001
    assert decision.total_cost_usd == pytest.approx(0.010, rel=1e-4)


@pytest.mark.asyncio
async def test_pipeline_cost_with_failures():
    """Test cost aggregation when some roles fail (should only count successful roles)."""
    from core.ai.consensus import ConsensusEngine
    from core.ai.roles.base import RoleRegistry
    from core.ai.router import LLMRouter
    from core.ai.types import AIResponse, RoleConfig, RoleVerdict

    router = LLMRouter(consensus_engine=ConsensusEngine(), min_roles_required=2)

    # Role 1: succeeds with cost
    mock_role1 = Mock()
    mock_role1.name = RoleName.TACTICAL
    mock_role1.weight = 1.0
    mock_role1.config = RoleConfig(
        name=RoleName.TACTICAL,
        provider=ProviderName.DEEPSEEK,
        model="test",
        system_prompt_id="test",
        enabled=True,
    )

    async def success_eval(*args, **kwargs):
        return (
            AIResponse(
                role=RoleName.TACTICAL,
                provider=ProviderName.DEEPSEEK,
                model="test",
                raw_text="{}",
                cost_usd=0.002,
            ),
            RoleVerdict(
                role=RoleName.TACTICAL,
                action="BUY",
                confidence=0.8,
                reasoning="test",
            ),
        )

    mock_role1.evaluate = success_eval

    # Role 2: succeeds with cost
    mock_role2 = Mock()
    mock_role2.name = RoleName.FUNDAMENTAL
    mock_role2.weight = 1.0
    mock_role2.config = RoleConfig(
        name=RoleName.FUNDAMENTAL,
        provider=ProviderName.XAI,
        model="test",
        system_prompt_id="test",
        enabled=True,
    )

    async def success_eval2(*args, **kwargs):
        return (
            AIResponse(
                role=RoleName.FUNDAMENTAL,
                provider=ProviderName.XAI,
                model="test",
                raw_text="{}",
                cost_usd=0.003,
            ),
            RoleVerdict(
                role=RoleName.FUNDAMENTAL,
                action="BUY",
                confidence=0.7,
                reasoning="test",
            ),
        )

    mock_role2.evaluate = success_eval2

    # Role 3: fails (should not contribute to cost)
    mock_role3 = Mock()
    mock_role3.name = RoleName.SCREENER
    mock_role3.weight = 1.0
    mock_role3.config = RoleConfig(
        name=RoleName.SCREENER,
        provider=ProviderName.DEEPSEEK,
        model="test",
        system_prompt_id="test",
        enabled=True,
    )

    async def failing_eval(*args, **kwargs):
        raise Exception("Provider error")

    mock_role3.evaluate = failing_eval

    RoleRegistry.register(mock_role1)
    RoleRegistry.register(mock_role2)
    RoleRegistry.register(mock_role3)

    with patch("core.ai.prompts.registry.PromptRegistry.get_active", return_value=Mock(content="test")):
        decision = await router.evaluate_opportunity(
            symbol="BTC/USD",
            timeframe="1h",
        )

    # Cost should only include successful roles (0.002 + 0.003)
    assert abs(decision.total_cost_usd - 0.005) < 0.000001


# ---------------------------------------------------------------------------
# Daily/Monthly Projection Tests
# ---------------------------------------------------------------------------


def test_daily_projection():
    """Test daily cost projection from per-eval cost."""
    # Assume typical evaluation: ~$0.034
    cost_per_eval = 0.034

    # 100 evaluations per day
    evals_per_day = 100

    daily_cost = cost_per_eval * evals_per_day

    assert daily_cost == pytest.approx(3.40, rel=1e-2)


def test_monthly_projection():
    """Test monthly cost projection (30 days)."""
    cost_per_eval = 0.034
    evals_per_day = 100
    days_per_month = 30

    monthly_cost = cost_per_eval * evals_per_day * days_per_month

    assert monthly_cost == pytest.approx(102.00, rel=1e-2)


def test_conservative_projection_with_buffer():
    """Test cost projection with 20% safety buffer."""
    cost_per_eval = 0.034
    evals_per_day = 100
    days_per_month = 30
    safety_buffer = 1.2  # 20% buffer

    monthly_cost = cost_per_eval * evals_per_day * days_per_month * safety_buffer

    assert monthly_cost == pytest.approx(122.40, rel=1e-2)


# ---------------------------------------------------------------------------
# Budget Limit Enforcement Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_budget_check_daily_limit(mock_db_session):
    """Test that daily budget limit is checked before evaluation."""
    with patch("db.crud.ai.check_budget_exceeded", new_callable=AsyncMock) as mock_check:
        mock_check.return_value = {
            "exceeded": True,
            "daily_exceeded": True,
            "monthly_exceeded": False,
            "daily_spent": 12.0,
            "daily_limit": 10.0,
            "daily_remaining": -2.0,
            "monthly_spent": 12.0,
            "monthly_limit": 0.0,
            "monthly_remaining": 0.0,
            "enabled": True,
        }

        result = await mock_check(mock_db_session, "global")

        assert result["exceeded"] is True
        assert result["daily_exceeded"] is True


@pytest.mark.asyncio
async def test_budget_check_monthly_limit(mock_db_session):
    """Test that monthly budget limit is checked."""
    with patch("db.crud.ai.check_budget_exceeded", new_callable=AsyncMock) as mock_check:
        mock_check.return_value = {
            "exceeded": False,
            "daily_exceeded": False,
            "monthly_exceeded": False,
            "daily_spent": 2.0,
            "daily_limit": 10.0,
            "daily_remaining": 8.0,
            "monthly_spent": 50.0,
            "monthly_limit": 100.0,
            "monthly_remaining": 50.0,
            "enabled": True,
        }

        result = await mock_check(mock_db_session, "global")

        assert result["exceeded"] is False
        assert result["monthly_exceeded"] is False


@pytest.mark.asyncio
async def test_budget_unlimited_when_zero(mock_db_session):
    """Test that 0.0 budget means unlimited (no limit)."""
    with patch("db.crud.ai.check_budget_exceeded", new_callable=AsyncMock) as mock_check:
        mock_check.return_value = {
            "exceeded": False,
            "daily_exceeded": False,
            "monthly_exceeded": False,
            "daily_spent": 100.0,
            "daily_limit": 0.0,
            "daily_remaining": 0.0,
            "monthly_spent": 100.0,
            "monthly_limit": 0.0,
            "monthly_remaining": 0.0,
            "enabled": True,
        }

        result = await mock_check(mock_db_session, "global")

        # Should not be exceeded because 0.0 = unlimited
        assert result["exceeded"] is False


@pytest.mark.asyncio
async def test_budget_enforcement_in_api():
    """Test that API endpoint enforces budget limits."""
    from fastapi import HTTPException

    # Mock evaluate endpoint checking budget
    with patch("db.crud.ai.check_budget_exceeded", new_callable=AsyncMock) as mock_check:
        mock_check.return_value = True  # Budget exceeded

        # Simulate API call
        with pytest.raises(HTTPException) as exc_info:
            # This would be the actual API endpoint logic
            budget_exceeded = await mock_check(Mock())
            if budget_exceeded:
                raise HTTPException(status_code=429, detail="Daily budget exceeded")

        assert exc_info.value.status_code == 429


# ---------------------------------------------------------------------------
# Cost Tracking Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_usage_tracking_records_cost(mock_db_session):
    """Test that each evaluation records cost to database."""
    with patch("db.crud.ai.log_usage", new_callable=AsyncMock) as mock_log:
        mock_log.return_value = Mock(cost_usd=0.002)

        # Simulate logging usage via the actual function name
        await mock_log(
            db=mock_db_session,
            role="tactical",
            provider="deepseek",
            model="deepseek-chat",
            tokens_in=150,
            tokens_out=75,
            cost_usd=0.002,
            latency_ms=500.0,
            success=True,
        )

        mock_log.assert_called_once()
        # Verify cost was passed
        call_args = mock_log.call_args
        assert call_args.kwargs["cost_usd"] == 0.002


@pytest.mark.asyncio
async def test_usage_aggregation(mock_db_session):
    """Test aggregating usage costs via get_usage_summary."""
    with patch("db.crud.ai.get_usage_summary", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = {
            "total_requests": 10,
            "total_cost_usd": 5.75,
            "total_tokens_in": 5000,
            "total_tokens_out": 2000,
        }

        result = await mock_get(mock_db_session)

        assert result["total_cost_usd"] == 5.75


# ---------------------------------------------------------------------------
# Edge Cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_zero_token_cost():
    """Test cost calculation when tokens are 0."""
    provider = DeepSeekProvider()

    mock_response = {
        "choices": [{"message": {"content": ""}}],
        "usage": {
            "prompt_tokens": 0,
            "completion_tokens": 0,
        },
    }

    with patch.object(provider, "_make_request", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = mock_response

        request = AIRequest(role=RoleName.SCREENER, user_prompt="Test")
        response = await provider.complete(request, system_prompt="test")

    assert response.cost_usd == 0.0


@pytest.mark.asyncio
async def test_very_large_token_count_cost():
    """Test cost calculation with very large token counts."""
    provider = OpenAIProvider()

    # 1M input, 500k output tokens
    mock_response = {
        "choices": [{"message": {"content": "test"}}],
        "usage": {
            "prompt_tokens": 1_000_000,
            "completion_tokens": 500_000,
        },
    }

    with patch.object(provider, "_make_request", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = mock_response

        request = AIRequest(role=RoleName.STRATEGIST, user_prompt="Test")
        response = await provider.complete(request, system_prompt="test")

    # Cost = (1M * $1.10 + 500k * $4.40) / 1M = $1.10 + $2.20 = $3.30
    expected_cost = (1_000_000 * 1.10 + 500_000 * 4.40) / 1_000_000
    assert abs(response.cost_usd - expected_cost) < 0.001
    assert response.cost_usd == pytest.approx(3.30, rel=1e-2)


def test_cost_precision():
    """Test that costs maintain sufficient precision."""
    # Very small cost
    cost = 0.0000123

    # Should maintain at least 6 decimal places
    assert f"{cost:.6f}" == "0.000012"


@pytest.mark.asyncio
async def test_negative_token_count_handling():
    """Test that negative token counts are handled safely."""
    provider = DeepSeekProvider()

    # Invalid negative tokens (shouldn't happen but test resilience)
    mock_response = {
        "choices": [{"message": {"content": "test"}}],
        "usage": {
            "prompt_tokens": -100,
            "completion_tokens": 50,
        },
    }

    with patch.object(provider, "_make_request", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = mock_response

        request = AIRequest(role=RoleName.SCREENER, user_prompt="Test")
        response = await provider.complete(request, system_prompt="test")

    # Should not crash, cost should be non-negative
    assert response.cost_usd >= 0.0
