"""Tests for AI budget API endpoints.

Tests budget enforcement in evaluation endpoints.
Uses mocked router to test HTTP 429 responses and error payloads.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from api.main import app


@pytest.fixture
def mock_router():
    """Mock LLMRouter for testing."""
    with patch("api.routes.ai._get_router") as mock:
        from unittest.mock import Mock

        router = AsyncMock()
        router.evaluate_opportunity = AsyncMock()
        router.get_usage_log = Mock(return_value=[])  # Regular method, not async
        router.clear_usage_log = Mock()  # Regular method, not async
        mock.return_value = router
        yield router


@pytest.fixture
def mock_db_factory():
    """Mock database session factory."""
    with patch("api.routes.ai._get_session_factory") as mock:
        db_session = AsyncMock()
        db_session.__aenter__ = AsyncMock(return_value=db_session)
        db_session.__aexit__ = AsyncMock(return_value=False)

        # Factory should be a regular callable that returns the async context manager
        def factory():
            return db_session

        mock.return_value = factory
        yield db_session


@pytest.fixture
def client(mock_router, mock_db_factory):
    """Create test client for FastAPI app with mocked dependencies."""
    return TestClient(app)


# =============================================================================
# Budget Enforcement Tests - /api/ai/evaluate
# =============================================================================



def test_evaluate_endpoint_rejects_on_daily_budget_exceeded(client, mock_router, mock_db_factory):
    """Test that /api/ai/evaluate returns 429 when daily budget is exceeded."""
    from db.crud import ai as ai_crud

    # Mock budget check to return exceeded
    with patch.object(ai_crud, "check_budget_exceeded", new_callable=AsyncMock) as mock_check:
        mock_check.return_value = {
            "exceeded": True,
            "daily_exceeded": True,
            "monthly_exceeded": False,
            "daily_spent": 10.50,
            "daily_limit": 10.0,
            "daily_remaining": -0.50,
            "monthly_spent": 50.0,
            "monthly_limit": 100.0,
            "monthly_remaining": 50.0,
            "enabled": True,
        }

        response = client.post(
            "/api/ai/evaluate",
            json={
                "symbol": "BTCUSDT",
                "timeframe": "1h",
            },
        )

        assert response.status_code == 429
        data = response.json()
        assert "error" in data["detail"]
        assert data["detail"]["error"] == "Budget exceeded"
        assert "Daily budget limit" in data["detail"]["message"]
        assert "$10.00" in data["detail"]["message"]



def test_evaluate_endpoint_rejects_on_monthly_budget_exceeded(client, mock_router, mock_db_factory):
    """Test that /api/ai/evaluate returns 429 when monthly budget is exceeded."""
    from db.crud import ai as ai_crud

    # Mock budget check to return exceeded
    with patch.object(ai_crud, "check_budget_exceeded", new_callable=AsyncMock) as mock_check:
        mock_check.return_value = {
            "exceeded": True,
            "daily_exceeded": False,
            "monthly_exceeded": True,
            "daily_spent": 5.0,
            "daily_limit": 10.0,
            "daily_remaining": 5.0,
            "monthly_spent": 101.0,
            "monthly_limit": 100.0,
            "monthly_remaining": -1.0,
            "enabled": True,
        }

        response = client.post(
            "/api/ai/evaluate",
            json={
                "symbol": "BTCUSDT",
                "timeframe": "1h",
            },
        )

        assert response.status_code == 429
        data = response.json()
        assert "error" in data["detail"]
        assert data["detail"]["error"] == "Budget exceeded"
        assert "Monthly budget limit" in data["detail"]["message"]
        assert "$100.00" in data["detail"]["message"]



def test_evaluate_endpoint_rejects_on_role_budget_exceeded(client, mock_router, mock_db_factory):
    """Test that /api/ai/evaluate returns 429 when role-specific budget is exceeded."""
    from db.crud import ai as ai_crud

    # Mock global budget OK, role budget exceeded
    async def mock_check_impl(db, scope, roles=None):
        if scope == "global":
            return {
                "exceeded": False,
                "daily_exceeded": False,
                "monthly_exceeded": False,
                "daily_spent": 5.0,
                "daily_limit": 100.0,
                "daily_remaining": 95.0,
                "monthly_spent": 50.0,
                "monthly_limit": 500.0,
                "monthly_remaining": 450.0,
                "enabled": True,
            }
        elif scope == "tactical":
            return {
                "exceeded": True,
                "daily_exceeded": True,
                "monthly_exceeded": False,
                "daily_spent": 5.50,
                "daily_limit": 5.0,
                "daily_remaining": -0.50,
                "monthly_spent": 20.0,
                "monthly_limit": 50.0,
                "monthly_remaining": 30.0,
                "enabled": True,
            }
        return {"exceeded": False, "enabled": False}

    with patch.object(ai_crud, "check_budget_exceeded", new_callable=AsyncMock) as mock_check:
        mock_check.side_effect = mock_check_impl

        response = client.post(
            "/api/ai/evaluate",
            json={
                "symbol": "BTCUSDT",
                "timeframe": "1h",
                "roles": ["tactical"],
            },
        )

        assert response.status_code == 429
        data = response.json()
        assert data["detail"]["error"] == "Budget exceeded"
        assert data["detail"]["role"] == "tactical"
        assert "tactical" in data["detail"]["message"]



def test_evaluate_endpoint_proceeds_when_budget_ok(client, mock_router, mock_db_factory):
    """Test that /api/ai/evaluate proceeds normally when budget is not exceeded."""
    from core.ai.types import ConsensusDecision, RoleName, RoleVerdict
    from db.crud import ai as ai_crud

    # Mock budget check to return not exceeded
    with patch.object(ai_crud, "check_budget_exceeded", new_callable=AsyncMock) as mock_check:
        mock_check.return_value = {
            "exceeded": False,
            "daily_exceeded": False,
            "monthly_exceeded": False,
            "daily_spent": 5.0,
            "daily_limit": 10.0,
            "daily_remaining": 5.0,
            "monthly_spent": 50.0,
            "monthly_limit": 100.0,
            "monthly_remaining": 50.0,
            "enabled": True,
        }

        # Mock decision logging
        with patch.object(ai_crud, "log_decision_with_usage", new_callable=AsyncMock) as mock_log:
            mock_decision = AsyncMock()
            mock_decision.created_at = datetime.now(timezone.utc)
            mock_log.return_value = mock_decision

            # Mock router evaluation
            mock_router.evaluate_opportunity.return_value = ConsensusDecision(
                final_action="BUY",
                final_confidence=0.75,
                reasoning="Test reasoning",
                verdicts=[
                    RoleVerdict(
                        role=RoleName.TACTICAL,
                        action="BUY",
                        confidence=0.75,
                        reasoning="Tactical test",
                        metrics={},
                    )
                ],
                vetoed_by=None,
                total_cost_usd=0.01,
                total_latency_ms=500.0,
            )

            response = client.post(
                "/api/ai/evaluate",
                json={
                    "symbol": "BTCUSDT",
                    "timeframe": "1h",
                },
            )

            # Should succeed
            assert response.status_code == 200
            data = response.json()
            assert data["finalAction"] == "BUY"


# =============================================================================
# Budget Enforcement Tests - /api/ai/evaluate/single
# =============================================================================



def test_evaluate_single_rejects_on_budget_exceeded(client, mock_router, mock_db_factory):
    """Test that /api/ai/evaluate/single returns 429 when budget is exceeded."""
    from db.crud import ai as ai_crud

    # Mock budget check to return exceeded
    with patch.object(ai_crud, "check_budget_exceeded", new_callable=AsyncMock) as mock_check:
        mock_check.return_value = {
            "exceeded": True,
            "daily_exceeded": True,
            "monthly_exceeded": False,
            "daily_spent": 10.50,
            "daily_limit": 10.0,
            "daily_remaining": -0.50,
            "monthly_spent": 50.0,
            "monthly_limit": 100.0,
            "monthly_remaining": 50.0,
            "enabled": True,
        }

        response = client.post(
            "/api/ai/evaluate/single",
            json={
                "symbol": "BTCUSDT",
                "timeframe": "1h",
                "roles": ["tactical"],
            },
        )

        assert response.status_code == 429
        data = response.json()
        assert data["detail"]["error"] == "Budget exceeded"



def test_evaluate_single_proceeds_when_budget_ok(client, mock_router, mock_db_factory):
    """Test that /api/ai/evaluate/single proceeds normally when budget is OK."""
    from core.ai.types import ConsensusDecision, RoleName, RoleVerdict
    from db.crud import ai as ai_crud

    # Mock budget check to return not exceeded
    with patch.object(ai_crud, "check_budget_exceeded", new_callable=AsyncMock) as mock_check:
        mock_check.return_value = {
            "exceeded": False,
            "daily_exceeded": False,
            "monthly_exceeded": False,
            "daily_spent": 2.0,
            "daily_limit": 10.0,
            "daily_remaining": 8.0,
            "monthly_spent": 20.0,
            "monthly_limit": 100.0,
            "monthly_remaining": 80.0,
            "enabled": True,
        }

        # Mock router evaluation
        mock_router.evaluate_opportunity.return_value = ConsensusDecision(
            final_action="BUY",
            final_confidence=0.80,
            reasoning="Single role test",
            verdicts=[
                RoleVerdict(
                    role=RoleName.TACTICAL,
                    action="BUY",
                    confidence=0.80,
                    reasoning="Tactical analysis",
                    metrics={},
                )
            ],
            vetoed_by=None,
            total_cost_usd=0.01,
            total_latency_ms=300.0,
        )

        response = client.post(
            "/api/ai/evaluate/single",
            json={
                "symbol": "BTCUSDT",
                "timeframe": "1h",
                "roles": ["tactical"],
            },
        )

        # Should succeed
        assert response.status_code == 200
        data = response.json()
        assert data["verdict"]["action"] == "BUY"
