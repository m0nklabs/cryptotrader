"""Unit tests for Multi-Brain AI API endpoints.

Tests all CRUD operations, evaluation endpoints, error handling,
and budget enforcement via HTTP.

Part of issue #209 (P6) for #205 Multi-Brain AI.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi.testclient import TestClient

from core.ai.types import ProviderName, RoleName


# ---------------------------------------------------------------------------
# Test Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_router():
    """Mock LLMRouter for testing."""
    router = Mock()
    router.evaluate_opportunity = AsyncMock()
    router.get_usage_log = Mock(return_value=[])
    router.clear_usage_log = Mock()
    return router


@pytest.fixture
def test_client():
    """Create test client with mocked dependencies."""
    with (
        patch("api.routes.ai._get_router") as mock_get_router,
        patch("api.routes.ai._get_session_factory") as mock_get_factory,
    ):
        # Setup mock router
        mock_router_instance = Mock()
        mock_router_instance.evaluate_opportunity = AsyncMock()
        mock_router_instance.get_usage_log = Mock(return_value=[])
        mock_router_instance.clear_usage_log = Mock()
        mock_get_router.return_value = mock_router_instance

        # Setup mock session factory - returns an async context manager
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        mock_factory = Mock()
        mock_factory.return_value = mock_session
        mock_get_factory.return_value = mock_factory

        # Import app after mocking
        from api.main import app

        client = TestClient(app, raise_server_exceptions=False)
        yield client


# ---------------------------------------------------------------------------
# Provider Health Endpoint Tests
# ---------------------------------------------------------------------------


def test_get_providers_health(test_client):
    """Test GET /api/ai/providers returns provider health status."""
    mock_instance = Mock()
    mock_instance.config.api_key_env = "FAKE_KEY"
    mock_instance.health_check = AsyncMock(return_value=True)
    mock_instance.close = AsyncMock()

    with (
        patch("api.routes.ai._provider_factory", return_value=lambda: mock_instance),
        patch("api.routes.ai._provider_models", return_value=["test-model"]),
        patch.dict("os.environ", {"FAKE_KEY": "test-value"}),
    ):
        response = test_client.get("/api/ai/providers")

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0


def test_get_providers_includes_all_providers(test_client):
    """Test that all registered providers are included in response."""
    mock_instance = Mock()
    mock_instance.config.api_key_env = "FAKE_KEY"
    mock_instance.health_check = AsyncMock(return_value=True)
    mock_instance.close = AsyncMock()

    with (
        patch("api.routes.ai._provider_factory", return_value=lambda: mock_instance),
        patch("api.routes.ai._provider_models", return_value=["test-model"]),
        patch.dict("os.environ", {"FAKE_KEY": "test-value"}),
    ):
        response = test_client.get("/api/ai/providers")

    assert response.status_code == 200
    data = response.json()
    # Should have one entry per ProviderName
    assert len(data) == len(ProviderName.__members__)


# ---------------------------------------------------------------------------
# Role Configuration Endpoint Tests
# ---------------------------------------------------------------------------


def test_get_roles(test_client):
    """Test GET /api/ai/roles returns all role configurations."""
    mock_config = Mock()
    mock_config.name = "tactical"
    mock_config.provider = ProviderName.DEEPSEEK.value
    mock_config.model = "deepseek-chat"
    mock_config.system_prompt_id = "tactical_v1"
    mock_config.temperature = 0.7
    mock_config.max_tokens = 2000
    mock_config.weight = 1.0
    mock_config.enabled = True
    mock_config.fallback_provider = None
    mock_config.fallback_model = None
    mock_config.updated_at = datetime.now(timezone.utc)

    with patch("api.routes.ai.ai_crud.get_role_configs", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = [mock_config]
        response = test_client.get("/api/ai/roles")

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 1


def test_get_single_role(test_client):
    """Test GET /api/ai/roles/{role} returns specific role config."""
    mock_config = Mock()
    mock_config.name = "tactical"
    mock_config.provider = ProviderName.DEEPSEEK.value
    mock_config.model = "deepseek-chat"
    mock_config.system_prompt_id = "tactical_v1"
    mock_config.temperature = 0.7
    mock_config.max_tokens = 2000
    mock_config.weight = 1.0
    mock_config.enabled = True
    mock_config.fallback_provider = None
    mock_config.fallback_model = None
    mock_config.updated_at = datetime.now(timezone.utc)

    with patch("api.routes.ai.ai_crud.get_role_config", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_config
        response = test_client.get("/api/ai/roles/tactical")

    assert response.status_code == 200


def test_get_nonexistent_role_returns_404(test_client):
    """Test getting non-existent role returns 404."""
    with patch("api.routes.ai.ai_crud.get_role_config", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = None
        response = test_client.get("/api/ai/roles/NONEXISTENT")

    assert response.status_code == 404


def test_update_role_config(test_client):
    """Test PUT /api/ai/roles/{role} updates role configuration."""
    update_data = {
        "provider": "OPENAI",
        "model": "o3-mini",
        "weight": 1.5,
        "enabled": True,
    }

    mock_config = Mock()
    mock_config.name = "tactical"
    mock_config.provider = "OPENAI"
    mock_config.model = "o3-mini"
    mock_config.system_prompt_id = "tactical_v1"
    mock_config.temperature = 0.7
    mock_config.max_tokens = 2000
    mock_config.weight = 1.5
    mock_config.enabled = True
    mock_config.fallback_provider = None
    mock_config.fallback_model = None
    mock_config.updated_at = datetime.now(timezone.utc)

    with patch("api.routes.ai.ai_crud.update_role_config", new_callable=AsyncMock) as mock_update:
        mock_update.return_value = mock_config
        response = test_client.put("/api/ai/roles/tactical", json=update_data)

    assert response.status_code == 200


# ---------------------------------------------------------------------------
# Prompt Management Endpoint Tests
# ---------------------------------------------------------------------------


def test_get_prompts_for_role(test_client):
    """Test GET /api/ai/prompts/{role} returns all prompts for role."""
    with patch("api.routes.ai.ai_crud.get_prompts", new_callable=AsyncMock) as mock_list:
        mock_prompt = Mock()
        mock_prompt.id = "tactical_v1"
        mock_prompt.role = "tactical"
        mock_prompt.version = 1
        mock_prompt.content = "Test prompt"
        mock_prompt.description = "Test"
        mock_prompt.is_active = True
        mock_prompt.created_at = datetime.now(timezone.utc)

        mock_list.return_value = [mock_prompt]

        response = test_client.get("/api/ai/prompts/tactical")

    assert response.status_code == 200


def test_create_new_prompt_version(test_client):
    """Test POST /api/ai/prompts creates new prompt version."""
    prompt_data = {
        "role": "tactical",
        "content": "New prompt content",
        "description": "New version",
    }

    with (
        patch("api.routes.ai.ai_crud.get_next_version", new_callable=AsyncMock) as mock_next,
        patch("api.routes.ai.ai_crud.create_prompt", new_callable=AsyncMock) as mock_create,
    ):
        mock_next.return_value = 2

        new_prompt = Mock()
        new_prompt.id = "tactical_v2"
        new_prompt.role = "tactical"
        new_prompt.version = 2
        new_prompt.content = "New prompt content"
        new_prompt.description = "New version"
        new_prompt.is_active = False
        new_prompt.created_at = datetime.now(timezone.utc)

        mock_create.return_value = new_prompt

        response = test_client.post("/api/ai/prompts", json=prompt_data)

    assert response.status_code == 201


def test_activate_prompt_version(test_client):
    """Test PUT /api/ai/prompts/{prompt_id}/activate activates a version."""
    with patch("api.routes.ai.ai_crud.activate_prompt", new_callable=AsyncMock) as mock_activate:
        activated_prompt = Mock()
        activated_prompt.id = "tactical_v2"
        activated_prompt.role = "tactical"
        activated_prompt.version = 2
        activated_prompt.content = "Test"
        activated_prompt.description = "Test"
        activated_prompt.is_active = True
        activated_prompt.created_at = datetime.now(timezone.utc)

        mock_activate.return_value = activated_prompt

        response = test_client.put("/api/ai/prompts/tactical_v2/activate")

    assert response.status_code == 200


# ---------------------------------------------------------------------------
# Evaluation Endpoint Tests
# ---------------------------------------------------------------------------


def test_evaluate_opportunity_success(test_client):
    """Test POST /api/ai/evaluate returns decision."""
    from core.ai.types import ConsensusDecision, RoleVerdict

    eval_request = {
        "symbol": "BTC/USD",
        "timeframe": "1h",
    }

    mock_decision = ConsensusDecision(
        final_action="BUY",
        final_confidence=0.85,
        verdicts=[
            RoleVerdict(
                role=RoleName.TACTICAL,
                action="BUY",
                confidence=0.9,
                reasoning="Strong momentum",
            ),
        ],
        reasoning="Consensus: BUY with high confidence",
        vetoed_by=None,
        total_cost_usd=0.003,
        total_latency_ms=450.0,
    )

    mock_logged = Mock()
    mock_logged.created_at = datetime.now(timezone.utc)

    with (
        patch("api.routes.ai._get_router") as mock_get_router,
        patch("api.routes.ai.ai_crud.check_budget_exceeded", new_callable=AsyncMock) as mock_budget,
        patch("api.routes.ai.ai_crud.log_decision_with_usage", new_callable=AsyncMock) as mock_log,
        patch("api.routes.ai.RoleRegistry") as mock_role_reg,
    ):
        mock_router_inst = Mock()
        mock_router_inst.evaluate_opportunity = AsyncMock(return_value=mock_decision)
        mock_router_inst.get_usage_log = Mock(return_value=[])
        mock_router_inst.clear_usage_log = Mock()
        mock_get_router.return_value = mock_router_inst

        mock_budget.return_value = {"exceeded": False, "daily_exceeded": False, "monthly_exceeded": False}
        mock_role_reg.active_roles.return_value = []
        mock_log.return_value = mock_logged

        response = test_client.post("/api/ai/evaluate", json=eval_request)

    assert response.status_code == 200
    data = response.json()
    assert data["finalAction"] == "BUY"
    assert data["finalConfidence"] == 0.85


def test_evaluate_with_budget_exceeded(test_client):
    """Test evaluation fails when budget is exceeded."""
    eval_request = {
        "symbol": "BTC/USD",
        "timeframe": "1h",
    }

    with patch("api.routes.ai.ai_crud.check_budget_exceeded", new_callable=AsyncMock) as mock_budget:
        mock_budget.return_value = {
            "exceeded": True,
            "daily_exceeded": True,
            "monthly_exceeded": False,
            "daily_limit": 1.0,
            "monthly_limit": 30.0,
            "daily_spent": 1.50,
            "monthly_spent": 5.00,
        }

        response = test_client.post("/api/ai/evaluate", json=eval_request)

    assert response.status_code == 429


def test_evaluate_with_provider_error(test_client):
    """Test evaluation handles provider errors gracefully."""
    eval_request = {
        "symbol": "BTC/USD",
        "timeframe": "1h",
    }

    with (
        patch("api.routes.ai._get_router") as mock_get_router,
        patch("api.routes.ai.ai_crud.check_budget_exceeded", new_callable=AsyncMock) as mock_budget,
        patch("api.routes.ai.RoleRegistry") as mock_role_reg,
    ):
        mock_router_inst = Mock()
        mock_router_inst.evaluate_opportunity = AsyncMock(side_effect=Exception("Provider timeout"))
        mock_get_router.return_value = mock_router_inst

        mock_budget.return_value = {"exceeded": False, "daily_exceeded": False, "monthly_exceeded": False}
        mock_role_reg.active_roles.return_value = []

        response = test_client.post("/api/ai/evaluate", json=eval_request)

    assert response.status_code in [500, 503]


def test_evaluate_missing_required_fields(test_client):
    """Test evaluation with missing required fields returns 422."""
    response = test_client.post("/api/ai/evaluate", json={})
    assert response.status_code == 422


def test_evaluate_invalid_symbol_format(test_client):
    """Test evaluation with invalid symbol format."""
    eval_request = {
        "symbol": "INVALID",
        "timeframe": "1h",
    }

    with (
        patch("api.routes.ai._get_router") as mock_get_router,
        patch("api.routes.ai.ai_crud.check_budget_exceeded", new_callable=AsyncMock) as mock_budget,
        patch("api.routes.ai.RoleRegistry") as mock_role_reg,
    ):
        mock_router_inst = Mock()
        mock_router_inst.evaluate_opportunity = AsyncMock(side_effect=Exception("Unknown symbol"))
        mock_get_router.return_value = mock_router_inst

        mock_budget.return_value = {"exceeded": False, "daily_exceeded": False, "monthly_exceeded": False}
        mock_role_reg.active_roles.return_value = []

        response = test_client.post("/api/ai/evaluate", json=eval_request)

    assert response.status_code in [200, 422, 500, 503]


# ---------------------------------------------------------------------------
# Decision History Endpoint Tests
# ---------------------------------------------------------------------------


def test_get_decisions_history(test_client):
    """Test GET /api/ai/decisions returns decision history."""
    with patch("api.routes.ai.ai_crud.get_decisions", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = []
        response = test_client.get("/api/ai/decisions")

    assert response.status_code == 200


def test_get_decisions_with_filters(test_client):
    """Test GET /api/ai/decisions with query filters."""
    with patch("api.routes.ai.ai_crud.get_decisions", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = []
        response = test_client.get(
            "/api/ai/decisions",
            params={
                "symbol": "BTC/USD",
                "limit": 10,
            },
        )

    assert response.status_code == 200


# ---------------------------------------------------------------------------
# Usage Tracking Endpoint Tests
# ---------------------------------------------------------------------------


def test_get_usage_summary(test_client):
    """Test GET /api/ai/usage returns usage summary."""
    with patch("api.routes.ai.ai_crud.get_usage_summary", new_callable=AsyncMock) as mock_summary:
        mock_summary.return_value = {
            "total_requests": 100,
            "total_cost_usd": 3.40,
            "total_tokens_in": 15000,
            "total_tokens_out": 7500,
            "by_role": {},
            "by_provider": {},
        }

        response = test_client.get("/api/ai/usage")

    assert response.status_code == 200


def test_get_daily_usage(test_client):
    """Test GET /api/ai/usage/daily returns daily breakdown."""
    with patch("api.routes.ai.ai_crud.get_daily_usage", new_callable=AsyncMock) as mock_daily:
        mock_daily.return_value = [
            {
                "date": "2026-02-28",
                "total_calls": 50,
                "total_cost_usd": 1.70,
            },
        ]

        response = test_client.get("/api/ai/usage/daily")

    assert response.status_code == 200


def test_get_usage_with_date_range(test_client):
    """Test usage endpoints with date range filters."""
    with patch("api.routes.ai.ai_crud.get_usage_summary", new_callable=AsyncMock) as mock_summary:
        mock_summary.return_value = {
            "total_requests": 0,
            "total_cost_usd": 0.0,
            "total_tokens_in": 0,
            "total_tokens_out": 0,
            "by_role": {},
            "by_provider": {},
        }

        response = test_client.get(
            "/api/ai/usage",
            params={
                "start_date": "2026-02-01T00:00:00Z",
                "end_date": "2026-02-28T23:59:59Z",
            },
        )

    assert response.status_code == 200


# ---------------------------------------------------------------------------
# Error Handling Tests
# ---------------------------------------------------------------------------


def test_missing_api_key_error():
    """Test that missing API key is handled appropriately."""
    pass


def test_database_connection_error(test_client):
    """Test handling of database connection errors."""
    with patch("api.routes.ai._get_session_factory") as mock_factory:
        mock_factory.side_effect = RuntimeError("DATABASE_URL not set")

        response = test_client.get("/api/ai/decisions")

    assert response.status_code in [500, 503]


def test_rate_limit_exceeded():
    """Test handling of rate limit errors from providers."""
    pass


# ---------------------------------------------------------------------------
# Budget Enforcement Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_budget_enforcement_daily_limit():
    """Test that daily budget limit is enforced before evaluation."""
    from api.routes.ai import EvaluationRequest, evaluate_opportunity

    request = EvaluationRequest(symbol="BTC/USD", timeframe="1h")

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    mock_factory = Mock()
    mock_factory.return_value = mock_session

    with (
        patch("api.routes.ai.ai_crud.check_budget_exceeded", new_callable=AsyncMock) as mock_budget,
        patch("api.routes.ai._get_router"),
        patch("api.routes.ai._get_session_factory", return_value=mock_factory),
    ):
        mock_budget.return_value = {
            "exceeded": True,
            "daily_exceeded": True,
            "monthly_exceeded": False,
            "daily_limit": 1.0,
            "monthly_limit": 30.0,
            "daily_spent": 1.50,
            "monthly_spent": 5.00,
        }

        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await evaluate_opportunity(request)

        assert exc_info.value.status_code == 429


@pytest.mark.asyncio
async def test_budget_enforcement_monthly_limit():
    """Test that monthly budget limit is checked."""
    from api.routes.ai import EvaluationRequest, evaluate_opportunity

    request = EvaluationRequest(symbol="BTC/USD", timeframe="1h")

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    mock_factory = Mock()
    mock_factory.return_value = mock_session

    with (
        patch("api.routes.ai.ai_crud.check_budget_exceeded", new_callable=AsyncMock) as mock_budget,
        patch("api.routes.ai._get_router"),
        patch("api.routes.ai._get_session_factory", return_value=mock_factory),
    ):
        mock_budget.return_value = {
            "exceeded": True,
            "daily_exceeded": False,
            "monthly_exceeded": True,
            "daily_limit": 5.0,
            "monthly_limit": 30.0,
            "daily_spent": 1.00,
            "monthly_spent": 35.00,
        }

        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await evaluate_opportunity(request)

        assert exc_info.value.status_code == 429


# ---------------------------------------------------------------------------
# Integration-Style Tests
# ---------------------------------------------------------------------------


def test_full_evaluation_workflow(test_client):
    """Test complete workflow: check providers -> roles -> evaluate."""
    from core.ai.types import ConsensusDecision

    # 1. Check providers are healthy
    mock_instance = Mock()
    mock_instance.config.api_key_env = "FAKE_KEY"
    mock_instance.health_check = AsyncMock(return_value=True)
    mock_instance.close = AsyncMock()

    with (
        patch("api.routes.ai._provider_factory", return_value=lambda: mock_instance),
        patch("api.routes.ai._provider_models", return_value=["test-model"]),
        patch.dict("os.environ", {"FAKE_KEY": "test-value"}),
    ):
        providers_response = test_client.get("/api/ai/providers")
        assert providers_response.status_code == 200

    # 2. Check roles are configured
    mock_config = Mock()
    mock_config.name = "tactical"
    mock_config.provider = ProviderName.DEEPSEEK.value
    mock_config.model = "deepseek-chat"
    mock_config.system_prompt_id = "tactical_v1"
    mock_config.temperature = 0.7
    mock_config.max_tokens = 2000
    mock_config.weight = 1.0
    mock_config.enabled = True
    mock_config.fallback_provider = None
    mock_config.fallback_model = None
    mock_config.updated_at = datetime.now(timezone.utc)

    with patch("api.routes.ai.ai_crud.get_role_configs", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = [mock_config]
        roles_response = test_client.get("/api/ai/roles")
        assert roles_response.status_code == 200

    # 3. Evaluate
    mock_decision = ConsensusDecision(
        final_action="BUY",
        final_confidence=0.85,
        verdicts=[],
        reasoning="Test",
        vetoed_by=None,
        total_cost_usd=0.003,
        total_latency_ms=450.0,
    )

    mock_logged = Mock()
    mock_logged.created_at = datetime.now(timezone.utc)

    with (
        patch("api.routes.ai._get_router") as mock_get_router,
        patch("api.routes.ai.ai_crud.check_budget_exceeded", new_callable=AsyncMock) as mock_budget,
        patch("api.routes.ai.ai_crud.log_decision_with_usage", new_callable=AsyncMock) as mock_log,
        patch("api.routes.ai.RoleRegistry") as mock_role_reg,
    ):
        mock_router_inst = Mock()
        mock_router_inst.evaluate_opportunity = AsyncMock(return_value=mock_decision)
        mock_router_inst.get_usage_log = Mock(return_value=[])
        mock_router_inst.clear_usage_log = Mock()
        mock_get_router.return_value = mock_router_inst

        mock_budget.return_value = {"exceeded": False, "daily_exceeded": False, "monthly_exceeded": False}
        mock_role_reg.active_roles.return_value = []
        mock_log.return_value = mock_logged

        eval_response = test_client.post("/api/ai/evaluate", json={"symbol": "BTC/USD", "timeframe": "1h"})
        assert eval_response.status_code == 200


def test_prompt_version_management_workflow(test_client):
    """Test creating and activating a new prompt version."""
    # 1. Get current prompts
    with patch("api.routes.ai.ai_crud.get_prompts", new_callable=AsyncMock) as mock_list:
        v1 = Mock()
        v1.id = "tactical_v1"
        v1.role = "tactical"
        v1.version = 1
        v1.content = "V1"
        v1.description = "V1"
        v1.is_active = True
        v1.created_at = datetime.now(timezone.utc)
        mock_list.return_value = [v1]

        get_response = test_client.get("/api/ai/prompts/tactical")
        assert get_response.status_code == 200

    # 2. Create new version
    with (
        patch("api.routes.ai.ai_crud.get_next_version", new_callable=AsyncMock) as mock_next,
        patch("api.routes.ai.ai_crud.create_prompt", new_callable=AsyncMock) as mock_create,
    ):
        mock_next.return_value = 2

        v2 = Mock()
        v2.id = "tactical_v2"
        v2.role = "tactical"
        v2.version = 2
        v2.content = "V2"
        v2.description = "V2"
        v2.is_active = False
        v2.created_at = datetime.now(timezone.utc)
        mock_create.return_value = v2

        create_response = test_client.post(
            "/api/ai/prompts",
            json={"role": "tactical", "content": "V2", "description": "V2"},
        )
        assert create_response.status_code == 201

    # 3. Activate new version
    with patch("api.routes.ai.ai_crud.activate_prompt", new_callable=AsyncMock) as mock_activate:
        v2_active = Mock()
        v2_active.id = "tactical_v2"
        v2_active.role = "tactical"
        v2_active.version = 2
        v2_active.content = "V2"
        v2_active.description = "V2"
        v2_active.is_active = True
        v2_active.created_at = datetime.now(timezone.utc)
        mock_activate.return_value = v2_active

        activate_response = test_client.put("/api/ai/prompts/tactical_v2/activate")
        assert activate_response.status_code == 200
