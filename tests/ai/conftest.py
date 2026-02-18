"""Shared test fixtures for Multi-Brain AI tests.

Provides reusable mocks, fixtures, and helpers for AI module testing.

Part of issue #209 (P6) for #205 Multi-Brain AI.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock

import pytest

from core.ai.types import (
    AIResponse,
    ProviderName,
    RoleName,
    RoleVerdict,
    SystemPrompt,
)


# ---------------------------------------------------------------------------
# Role Registry Management
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_role_registry():
    """Reset RoleRegistry before each test to avoid test interference.
    
    This fixture automatically runs before every test to ensure clean state.
    """
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


@pytest.fixture(autouse=True)
def clear_token_bucket_instances():
    """Clear TokenBucket singleton instances before each test.
    
    Prevents rate limiter state leakage between tests.
    """
    from core.ai.providers.base import TokenBucket

    TokenBucket._instances.clear()
    TokenBucket._lock = None
    yield
    TokenBucket._instances.clear()
    TokenBucket._lock = None


# ---------------------------------------------------------------------------
# Mock Provider Responses
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_deepseek_response():
    """Canned DeepSeek API response for testing.
    
    Returns a typical successful response with valid JSON content.
    """
    return {
        "choices": [
            {
                "message": {
                    "content": '{"action": "BUY", "confidence": 0.85, "reasoning": "Strong momentum"}'
                }
            }
        ],
        "usage": {
            "prompt_tokens": 150,
            "completion_tokens": 75,
        },
    }


@pytest.fixture
def mock_openai_response():
    """Canned OpenAI API response for testing."""
    return {
        "choices": [
            {
                "message": {
                    "content": '{"action": "NEUTRAL", "confidence": 0.6, "reasoning": "Mixed signals"}'
                }
            }
        ],
        "usage": {
            "prompt_tokens": 200,
            "completion_tokens": 100,
        },
    }


@pytest.fixture
def mock_xai_response():
    """Canned xAI (Grok) API response for testing."""
    return {
        "choices": [
            {
                "message": {
                    "content": '{"action": "SELL", "confidence": 0.75, "reasoning": "Negative sentiment"}'
                }
            }
        ],
        "usage": {
            "prompt_tokens": 180,
            "completion_tokens": 90,
        },
    }


@pytest.fixture
def mock_ollama_response():
    """Canned Ollama API response for testing."""
    return {
        "message": {"content": '{"action": "BUY", "confidence": 0.7, "reasoning": "Local analysis"}'},
        "prompt_eval_count": 120,
        "eval_count": 60,
    }


# ---------------------------------------------------------------------------
# Mock Consensus Verdicts
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_consensus_verdicts():
    """Set of RoleVerdicts for consensus testing.
    
    Provides a typical scenario with mixed signals but BUY majority.
    """
    return [
        RoleVerdict(
            role=RoleName.SCREENER,
            action="BUY",
            confidence=0.8,
            reasoning="Strong volume and momentum",
        ),
        RoleVerdict(
            role=RoleName.TACTICAL,
            action="BUY",
            confidence=0.9,
            reasoning="Bullish breakout pattern confirmed",
        ),
        RoleVerdict(
            role=RoleName.FUNDAMENTAL,
            action="NEUTRAL",
            confidence=0.6,
            reasoning="Mixed news sentiment",
        ),
        RoleVerdict(
            role=RoleName.STRATEGIST,
            action="BUY",
            confidence=0.85,
            reasoning="Favorable risk/reward ratio",
        ),
    ]


@pytest.fixture
def mock_veto_verdict():
    """VETO verdict from Strategist for testing VETO logic."""
    return RoleVerdict(
        role=RoleName.STRATEGIST,
        action="VETO",
        confidence=1.0,
        reasoning="Maximum position size already reached for this sector",
    )


# ---------------------------------------------------------------------------
# Mock AI Responses
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_ai_response():
    """Mock AIResponse for testing.
    
    Represents a successful provider response with typical metrics.
    """
    return AIResponse(
        role=RoleName.TACTICAL,
        provider=ProviderName.DEEPSEEK,
        model="deepseek-chat",
        raw_text='{"action": "BUY", "confidence": 0.85}',
        parsed={"action": "BUY", "confidence": 0.85},
        tokens_in=150,
        tokens_out=75,
        cost_usd=0.002,
        latency_ms=500.0,
        error=None,
    )


# ---------------------------------------------------------------------------
# Mock System Prompts
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_system_prompt():
    """Mock SystemPrompt for testing.
    
    Provides a typical active prompt for the TACTICAL role.
    """
    return SystemPrompt(
        id="tactical_v1",
        role=RoleName.TACTICAL,
        version=1,
        content="You are a quantitative technical analyst...",
        description="Tactical agent v1 prompt",
        is_active=True,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


@pytest.fixture
def mock_inactive_prompt():
    """Mock inactive SystemPrompt for version testing."""
    return SystemPrompt(
        id="tactical_v2",
        role=RoleName.TACTICAL,
        version=2,
        content="Updated tactical prompt...",
        description="Tactical agent v2 prompt (testing)",
        is_active=False,
        created_at=datetime(2026, 2, 1, tzinfo=timezone.utc),
    )


# ---------------------------------------------------------------------------
# Mock Database Session
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_db_session():
    """Mock async database session.
    
    Use this for tests that need to mock database operations.
    """
    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    return session


# ---------------------------------------------------------------------------
# Mock HTTP Client
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_http_client():
    """Mock httpx.AsyncClient for provider testing.
    
    Returns a mock client that can be configured per test.
    """
    client = AsyncMock()
    
    # Mock response
    mock_response = Mock()
    mock_response.json = Mock()
    mock_response.raise_for_status = Mock()
    
    client.request = AsyncMock(return_value=mock_response)
    client.get = AsyncMock(return_value=mock_response)
    client.post = AsyncMock(return_value=mock_response)
    
    return client


# ---------------------------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------------------------


def make_mock_role(role_name: RoleName, weight: float = 1.0):
    """Factory function to create a mock role.
    
    Args:
        role_name: The role name
        weight: Role weight for consensus (default 1.0)
        
    Returns:
        Mock role object with standard configuration
    """
    from core.ai.types import ProviderName, RoleConfig

    mock_role = Mock()
    mock_role.name = role_name
    mock_role.weight = weight
    mock_role.config = RoleConfig(
        name=role_name,
        provider=ProviderName.DEEPSEEK,
        model="test-model",
        system_prompt_id="test-prompt",
        weight=weight,
        enabled=True,
    )
    return mock_role


def make_mock_evaluate(role_name: RoleName, action: str = "BUY", confidence: float = 0.8):
    """Factory function to create a mock evaluate function.
    
    Args:
        role_name: The role name
        action: The action to return (BUY/SELL/NEUTRAL/VETO)
        confidence: The confidence score (0.0-1.0)
        
    Returns:
        Async function that returns (AIResponse, RoleVerdict)
    """
    async def mock_eval(*args, **kwargs):
        return (
            AIResponse(
                role=role_name,
                provider=ProviderName.DEEPSEEK,
                model="test-model",
                raw_text="{}",
            ),
            RoleVerdict(
                role=role_name,
                action=action,
                confidence=confidence,
                reasoning=f"Test {action} from {role_name.value}",
            ),
        )
    
    return mock_eval
