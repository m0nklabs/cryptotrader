"""Smoke/E2E tests for AI API endpoints.

Contract tests to ensure API changes don't silently break the frontend.
Tests validate status codes and response schemas without calling real providers.

Part of issue #205 - Multi-Brain AI implementation.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi.testclient import TestClient

from core.ai.types import ConsensusDecision, ProviderName, RoleName, RoleVerdict

# Budget status that allows evaluation (not exceeded)
_BUDGET_OK = {
    "exceeded": False,
    "daily_exceeded": False,
    "monthly_exceeded": False,
    "daily_limit": 10.0,
    "monthly_limit": 100.0,
    "daily_spent": 0.0,
    "monthly_spent": 0.0,
}


@pytest.fixture(autouse=True)
def _mock_budget_check():
    """Auto-mock budget check so evaluate tests don't need a real DB."""
    with patch(
        "api.routes.ai.ai_crud.check_budget_exceeded",
        new_callable=AsyncMock,
        return_value=_BUDGET_OK,
    ):
        yield


@pytest.fixture
def client():
    """Create a test client for AI API endpoints."""
    from api.main import app

    # Disable raise_server_exceptions so we can test error responses
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def mock_ai_router():
    """Mock LLMRouter that returns deterministic responses without calling real providers."""
    router = Mock()

    # Create a mock evaluate_opportunity method that returns a deterministic ConsensusDecision
    async def mock_evaluate(symbol, timeframe, **kwargs):
        """Return a mock ConsensusDecision with realistic structure."""
        return ConsensusDecision(
            final_action="BUY",
            final_confidence=0.75,
            reasoning="Mock evaluation: Technical indicators show bullish trend",
            verdicts=[
                RoleVerdict(
                    role=RoleName.SCREENER,
                    action="BUY",
                    confidence=0.8,
                    reasoning="Mock screener: Strong momentum signals",
                    metrics={"rsi": 65, "macd": "bullish"},
                ),
                RoleVerdict(
                    role=RoleName.TACTICAL,
                    action="BUY",
                    confidence=0.7,
                    reasoning="Mock tactical: Entry point confirmed",
                    metrics={"support": 40000, "resistance": 45000},
                ),
            ],
            vetoed_by=None,
            total_cost_usd=0.034,
            total_latency_ms=250.5,
        )

    router.evaluate_opportunity = AsyncMock(side_effect=mock_evaluate)

    # Mock usage log
    router.get_usage_log.return_value = [
        Mock(
            role=RoleName.SCREENER,
            provider=ProviderName.DEEPSEEK,
            model="deepseek-chat",
            tokens_in=1500,
            tokens_out=300,
            cost_usd=0.017,
            latency_ms=120.0,
            symbol="BTCUSD",
            success=True,
        ),
        Mock(
            role=RoleName.TACTICAL,
            provider=ProviderName.OPENAI,
            model="gpt-4o-mini",
            tokens_in=1600,
            tokens_out=320,
            cost_usd=0.017,
            latency_ms=130.5,
            symbol="BTCUSD",
            success=True,
        ),
    ]
    router.clear_usage_log.return_value = None

    return router


@pytest.fixture
def ai_crud_mocks():
    """Mock database session factory and AI CRUD functions.

    Returns:
        tuple: (mock_session_factory, mock_log_decision, mock_usage_summary)
    """
    # Create async context manager mock
    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)

    # Mock decision logging
    async def mock_log_decision(**kwargs):
        """Return a mock logged decision."""
        return Mock(
            symbol=kwargs.get("symbol", "BTCUSD"),
            timeframe=kwargs.get("timeframe", "1h"),
            final_action=kwargs.get("final_action", "BUY"),
            final_confidence=kwargs.get("final_confidence", 0.75),
            created_at=datetime.now(timezone.utc),
        )

    # Mock usage summary
    async def mock_usage_summary(db, start_date, end_date):
        """Return a mock usage summary."""
        return {
            "total_requests": 42,
            "total_cost_usd": 1.25,
            "total_tokens_in": 50000,
            "total_tokens_out": 10000,
            "by_role": {
                "screener": {
                    "cost_usd": 0.5,
                    "requests": 20,
                    "avg_latency_ms": 120.0,
                },
                "tactical": {
                    "cost_usd": 0.75,
                    "requests": 22,
                    "avg_latency_ms": 130.0,
                },
            },
            "by_provider": {
                "deepseek": {
                    "cost_usd": 0.6,
                    "requests": 25,
                },
                "openai": {
                    "cost_usd": 0.65,
                    "requests": 17,
                },
            },
        }

    # Create mock session factory
    def mock_session_factory():
        """Return the mock session."""
        return session

    return mock_session_factory, mock_log_decision, mock_usage_summary


# =============================================================================
# POST /api/ai/evaluate - Happy Path
# =============================================================================


def test_evaluate_happy_path_returns_200(client, mock_ai_router, ai_crud_mocks):
    """Test POST /api/ai/evaluate returns 200 with valid request."""
    mock_session_factory, mock_log_decision, _ = ai_crud_mocks

    with patch("api.routes.ai._get_router", return_value=mock_ai_router):
        with patch("api.routes.ai._get_session_factory", return_value=mock_session_factory):
            with patch("api.routes.ai.ai_crud.log_decision_with_usage", side_effect=mock_log_decision):
                response = client.post(
                    "/api/ai/evaluate",
                    json={
                        "symbol": "BTCUSD",
                        "timeframe": "1h",
                    },
                )

    assert response.status_code == 200, f"Expected 200 but got {response.status_code}: {response.text}"


def test_evaluate_response_schema(client, mock_ai_router, ai_crud_mocks):
    """Test POST /api/ai/evaluate returns correct response schema."""
    mock_session_factory, mock_log_decision, _ = ai_crud_mocks

    with patch("api.routes.ai._get_router", return_value=mock_ai_router):
        with patch("api.routes.ai._get_session_factory", return_value=mock_session_factory):
            with patch("api.routes.ai.ai_crud.log_decision_with_usage", side_effect=mock_log_decision):
                response = client.post(
                    "/api/ai/evaluate",
                    json={
                        "symbol": "BTCUSD",
                        "timeframe": "1h",
                    },
                )

    assert response.status_code == 200
    data = response.json()

    # Validate top-level schema
    assert "symbol" in data, "Response missing 'symbol'"
    assert "timeframe" in data, "Response missing 'timeframe'"
    assert "finalAction" in data, "Response missing 'finalAction'"
    assert "finalConfidence" in data, "Response missing 'finalConfidence'"
    assert "reasoning" in data, "Response missing 'reasoning'"
    assert "verdicts" in data, "Response missing 'verdicts'"
    assert "vetoedBy" in data, "Response missing 'vetoedBy' (optional field, may be null)"
    assert "totalCostUsd" in data, "Response missing 'totalCostUsd'"
    assert "totalLatencyMs" in data, "Response missing 'totalLatencyMs'"
    assert "createdAt" in data, "Response missing 'createdAt'"

    # Validate data types
    assert data["symbol"] == "BTCUSD"
    assert data["timeframe"] == "1h"
    assert data["finalAction"] in ["BUY", "SELL", "HOLD", "NEUTRAL"]
    assert isinstance(data["finalConfidence"], (int, float))
    assert 0.0 <= data["finalConfidence"] <= 1.0
    assert isinstance(data["reasoning"], str)
    assert isinstance(data["verdicts"], list)
    assert len(data["verdicts"]) > 0
    assert isinstance(data["totalCostUsd"], (int, float))
    assert isinstance(data["totalLatencyMs"], (int, float))

    # Validate verdict structure
    verdict = data["verdicts"][0]
    assert "role" in verdict
    assert "action" in verdict
    assert "confidence" in verdict
    assert "reasoning" in verdict


def test_evaluate_with_roles_filter(client, mock_ai_router, ai_crud_mocks):
    """Test POST /api/ai/evaluate accepts roles filter."""
    mock_session_factory, mock_log_decision, _ = ai_crud_mocks

    with patch("api.routes.ai._get_router", return_value=mock_ai_router):
        with patch("api.routes.ai._get_session_factory", return_value=mock_session_factory):
            with patch("api.routes.ai.ai_crud.log_decision_with_usage", side_effect=mock_log_decision):
                response = client.post(
                    "/api/ai/evaluate",
                    json={
                        "symbol": "ETHUSDT",
                        "timeframe": "4h",
                        "roles": ["screener", "tactical"],
                    },
                )

    assert response.status_code == 200
    data = response.json()
    assert data["symbol"] == "ETHUSDT"
    assert data["timeframe"] == "4h"

    # Verify router was called with correct roles
    mock_ai_router.evaluate_opportunity.assert_called_once()
    call_kwargs = mock_ai_router.evaluate_opportunity.call_args.kwargs
    assert call_kwargs["symbol"] == "ETHUSDT"
    assert call_kwargs["timeframe"] == "4h"
    assert call_kwargs["roles"] == [RoleName.SCREENER, RoleName.TACTICAL]


def test_evaluate_with_context_data(client, mock_ai_router, ai_crud_mocks):
    """Test POST /api/ai/evaluate accepts optional context data."""
    mock_session_factory, mock_log_decision, _ = ai_crud_mocks

    request_payload = {
        "symbol": "BTCUSD",
        "timeframe": "1h",
        "candles": [{"open": 40000, "close": 40500, "high": 40600, "low": 39900}],
        "indicators": {"rsi": 65, "macd": "bullish"},
        "portfolio": {"btc_balance": 0.5, "usd_balance": 10000},
        "risk_limits": {"max_position_size": 5000},
    }

    with patch("api.routes.ai._get_router", return_value=mock_ai_router):
        with patch("api.routes.ai._get_session_factory", return_value=mock_session_factory):
            with patch("api.routes.ai.ai_crud.log_decision_with_usage", side_effect=mock_log_decision):
                response = client.post("/api/ai/evaluate", json=request_payload)

    assert response.status_code == 200

    # Verify router received all context data
    call_kwargs = mock_ai_router.evaluate_opportunity.call_args.kwargs
    assert call_kwargs["candles"] == request_payload["candles"]
    assert call_kwargs["indicators"] == request_payload["indicators"]
    assert call_kwargs["portfolio"] == request_payload["portfolio"]
    assert call_kwargs["risk_limits"] == request_payload["risk_limits"]


# =============================================================================
# POST /api/ai/evaluate - Error Cases
# =============================================================================


def test_evaluate_missing_symbol_returns_422(client):
    """Test POST /api/ai/evaluate returns 422 when symbol is missing."""
    response = client.post(
        "/api/ai/evaluate",
        json={
            "timeframe": "1h",
        },
    )

    assert response.status_code == 422, f"Expected 422 but got {response.status_code}: {response.text}"


def test_evaluate_invalid_role_returns_400(client, mock_ai_router, ai_crud_mocks):
    """Test POST /api/ai/evaluate returns 400 for invalid role names."""
    mock_session_factory, _, _ = ai_crud_mocks

    with patch("api.routes.ai._get_router", return_value=mock_ai_router):
        with patch("api.routes.ai._get_session_factory", return_value=mock_session_factory):
            response = client.post(
                "/api/ai/evaluate",
                json={
                    "symbol": "BTCUSD",
                    "timeframe": "1h",
                    "roles": ["screener", "invalid_role", "tactical"],
                },
            )

    assert response.status_code == 400, f"Expected 400 but got {response.status_code}: {response.text}"
    data = response.json()
    assert "detail" in data
    assert "invalid" in data["detail"].lower() or "role" in data["detail"].lower()


def test_evaluate_handles_router_failure_gracefully(client, ai_crud_mocks):
    """Test POST /api/ai/evaluate handles router failures gracefully.

    When the router raises an exception, FastAPI's default error handler
    will catch it and return a 500 Internal Server Error.
    """
    mock_session_factory, _, _ = ai_crud_mocks

    mock_router = Mock()
    mock_router.evaluate_opportunity = AsyncMock(side_effect=Exception("Provider timeout"))

    with patch("api.routes.ai._get_router", return_value=mock_router):
        with patch("api.routes.ai._get_session_factory", return_value=mock_session_factory):
            response = client.post(
                "/api/ai/evaluate",
                json={
                    "symbol": "BTCUSD",
                    "timeframe": "1h",
                },
            )

    # FastAPI will catch the exception and return 500
    # (The endpoint itself doesn't have specific error handling for router failures)
    assert response.status_code == 500, f"Expected 500 but got {response.status_code}: {response.text}"


# =============================================================================
# GET /api/ai/usage - Happy Path
# =============================================================================


def test_usage_summary_returns_200(client, ai_crud_mocks):
    """Test GET /api/ai/usage returns 200 with valid response."""
    mock_session_factory, _, mock_usage_summary = ai_crud_mocks

    with patch("api.routes.ai._get_session_factory", return_value=mock_session_factory):
        with patch("api.routes.ai.ai_crud.get_usage_summary", side_effect=mock_usage_summary):
            response = client.get("/api/ai/usage")

    assert response.status_code == 200, f"Expected 200 but got {response.status_code}: {response.text}"


def test_usage_summary_response_schema(client, ai_crud_mocks):
    """Test GET /api/ai/usage returns correct response schema."""
    mock_session_factory, _, mock_usage_summary = ai_crud_mocks

    with patch("api.routes.ai._get_session_factory", return_value=mock_session_factory):
        with patch("api.routes.ai.ai_crud.get_usage_summary", side_effect=mock_usage_summary):
            response = client.get("/api/ai/usage")

    assert response.status_code == 200
    data = response.json()

    # Validate top-level schema
    assert "totalRequests" in data, "Response missing 'totalRequests'"
    assert "totalCostUsd" in data, "Response missing 'totalCostUsd'"
    assert "totalTokensIn" in data, "Response missing 'totalTokensIn'"
    assert "totalTokensOut" in data, "Response missing 'totalTokensOut'"
    assert "byRole" in data, "Response missing 'byRole'"
    assert "byProvider" in data, "Response missing 'byProvider'"

    # Validate data types
    assert isinstance(data["totalRequests"], int)
    assert isinstance(data["totalCostUsd"], (int, float))
    assert isinstance(data["totalTokensIn"], int)
    assert isinstance(data["totalTokensOut"], int)
    assert isinstance(data["byRole"], dict)
    assert isinstance(data["byProvider"], dict)

    # Validate byRole structure (includes avgLatencyMs)
    if data["byRole"]:
        first_role = list(data["byRole"].values())[0]
        assert "cost" in first_role
        assert "requests" in first_role
        assert "avgLatencyMs" in first_role
        assert isinstance(first_role["cost"], (int, float))
        assert isinstance(first_role["requests"], int)
        assert isinstance(first_role["avgLatencyMs"], (int, float))

    # Validate byProvider structure (no avgLatencyMs in provider stats)
    if data["byProvider"]:
        first_provider = list(data["byProvider"].values())[0]
        assert "cost" in first_provider
        assert "requests" in first_provider
        assert isinstance(first_provider["cost"], (int, float))
        assert isinstance(first_provider["requests"], int)


def test_usage_summary_with_date_range(client, ai_crud_mocks):
    """Test GET /api/ai/usage accepts date range parameters."""
    mock_session_factory, _, mock_usage_summary = ai_crud_mocks

    with patch("api.routes.ai._get_session_factory", return_value=mock_session_factory):
        with patch("api.routes.ai.ai_crud.get_usage_summary", side_effect=mock_usage_summary) as mock_summary:
            response = client.get(
                "/api/ai/usage",
                params={
                    "start_date": "2026-01-01T00:00:00Z",
                    "end_date": "2026-02-01T00:00:00Z",
                },
            )

    assert response.status_code == 200

    # Verify the CRUD function was called with parsed datetime objects
    mock_summary.assert_called_once()
    call_kwargs = mock_summary.call_args.kwargs
    assert "start_date" in call_kwargs
    assert "end_date" in call_kwargs
    assert isinstance(call_kwargs["start_date"], datetime)
    assert isinstance(call_kwargs["end_date"], datetime)


def test_usage_summary_defaults_to_30_days(client, ai_crud_mocks):
    """Test GET /api/ai/usage defaults to 30-day range when no params provided."""
    mock_session_factory, _, mock_usage_summary = ai_crud_mocks

    with patch("api.routes.ai._get_session_factory", return_value=mock_session_factory):
        with patch("api.routes.ai.ai_crud.get_usage_summary", side_effect=mock_usage_summary) as mock_summary:
            response = client.get("/api/ai/usage")

    assert response.status_code == 200

    # Verify default date range was applied
    mock_summary.assert_called_once()
    call_kwargs = mock_summary.call_args.kwargs
    assert "start_date" in call_kwargs
    assert "end_date" in call_kwargs

    # Verify it's approximately 30 days (use total_seconds for robustness in CI)
    time_range = call_kwargs["end_date"] - call_kwargs["start_date"]
    days = time_range.total_seconds() / 86400
    assert 28 <= days <= 32, f"Expected ~30 day range but got {days:.1f} days"


# =============================================================================
# Determinism and No External Network Calls
# =============================================================================


def test_evaluate_does_not_call_real_providers(client, mock_ai_router, ai_crud_mocks):
    """Test that /api/ai/evaluate does not make real provider API calls."""
    mock_session_factory, mock_log_decision, _ = ai_crud_mocks

    # Use mocks and verify no real HTTP clients are created
    with patch("api.routes.ai._get_router", return_value=mock_ai_router):
        with patch("api.routes.ai._get_session_factory", return_value=mock_session_factory):
            with patch("api.routes.ai.ai_crud.log_decision_with_usage", side_effect=mock_log_decision):
                # This should complete quickly without network calls
                response = client.post(
                    "/api/ai/evaluate",
                    json={
                        "symbol": "BTCUSD",
                        "timeframe": "1h",
                    },
                )

    assert response.status_code == 200

    # Verify mock was called (not real provider)
    mock_ai_router.evaluate_opportunity.assert_called_once()


def test_multiple_evaluate_calls_are_deterministic(client, mock_ai_router, ai_crud_mocks):
    """Test that repeated calls to /api/ai/evaluate return consistent results."""
    mock_session_factory, mock_log_decision, _ = ai_crud_mocks

    with patch("api.routes.ai._get_router", return_value=mock_ai_router):
        with patch("api.routes.ai._get_session_factory", return_value=mock_session_factory):
            with patch("api.routes.ai.ai_crud.log_decision_with_usage", side_effect=mock_log_decision):
                # Make two identical requests
                response1 = client.post(
                    "/api/ai/evaluate",
                    json={"symbol": "BTCUSD", "timeframe": "1h"},
                )
                response2 = client.post(
                    "/api/ai/evaluate",
                    json={"symbol": "BTCUSD", "timeframe": "1h"},
                )

    assert response1.status_code == 200
    assert response2.status_code == 200

    data1 = response1.json()
    data2 = response2.json()

    # Key fields should be consistent (excluding timestamps)
    assert data1["symbol"] == data2["symbol"]
    assert data1["timeframe"] == data2["timeframe"]
    assert data1["finalAction"] == data2["finalAction"]
    assert data1["finalConfidence"] == data2["finalConfidence"]
    assert len(data1["verdicts"]) == len(data2["verdicts"])

    # Verify the router was invoked for each request (no caching/skipping)
    assert mock_ai_router.evaluate_opportunity.call_count == 2


# =============================================================================
# Authentication Tests
# =============================================================================


def test_evaluate_requires_api_key_when_configured(client):
    """Test POST /api/ai/evaluate returns 401 when AI_API_KEY is set but not provided."""
    import os

    with patch.dict(os.environ, {"AI_API_KEY": "test-secret-key"}):
        response = client.post(
            "/api/ai/evaluate",
            json={"symbol": "BTCUSD", "timeframe": "1h"},
        )

    assert response.status_code == 401, f"Expected 401 but got {response.status_code}: {response.text}"
    data = response.json()
    assert "detail" in data
    assert "api key" in data["detail"].lower() or "invalid" in data["detail"].lower()


def test_evaluate_accepts_valid_api_key(client, mock_ai_router, ai_crud_mocks):
    """Test POST /api/ai/evaluate returns 200 when valid API key is provided."""
    import os

    mock_session_factory, mock_log_decision, _ = ai_crud_mocks

    with patch.dict(os.environ, {"AI_API_KEY": "test-secret-key"}):
        with patch("api.routes.ai._get_router", return_value=mock_ai_router):
            with patch("api.routes.ai._get_session_factory", return_value=mock_session_factory):
                with patch("api.routes.ai.ai_crud.log_decision_with_usage", side_effect=mock_log_decision):
                    response = client.post(
                        "/api/ai/evaluate",
                        json={"symbol": "BTCUSD", "timeframe": "1h"},
                        headers={"X-API-Key": "test-secret-key"},
                    )

    assert response.status_code == 200, f"Expected 200 but got {response.status_code}: {response.text}"


def test_usage_requires_api_key_when_configured(client):
    """Test GET /api/ai/usage returns 401 when AI_API_KEY is set but not provided."""
    import os

    with patch.dict(os.environ, {"AI_API_KEY": "test-secret-key"}):
        response = client.get("/api/ai/usage")

    assert response.status_code == 401, f"Expected 401 but got {response.status_code}: {response.text}"
    data = response.json()
    assert "detail" in data
    assert "api key" in data["detail"].lower() or "invalid" in data["detail"].lower()
