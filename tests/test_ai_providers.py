"""Unit tests for LLM provider adapters.

Tests rate limiting, retry logic, error handling, and response parsing
with mocked HTTP responses.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from core.ai.providers.base import (
    PermanentError,
    TokenBucket,
    TransientError,
    classify_http_error,
    validate_json_response,
)
from core.ai.providers.deepseek import DeepSeekProvider
from core.ai.providers.ollama import OllamaProvider
from core.ai.providers.openai import OpenAIProvider
from core.ai.providers.xai import XAIProvider
from core.ai.types import AIRequest, ProviderName, RoleName


# ---------------------------------------------------------------------------
# Test Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def clear_token_bucket_instances():
    """Clear TokenBucket singleton instances before each test to prevent interference."""
    TokenBucket._instances.clear()
    TokenBucket._lock = None
    yield
    TokenBucket._instances.clear()
    TokenBucket._lock = None


# ---------------------------------------------------------------------------
# Error Classification Tests
# ---------------------------------------------------------------------------


def test_classify_http_error_transient():
    """Test that transient errors are classified correctly."""
    # 429 Rate Limited
    error = classify_http_error(429, "Rate limited")
    assert isinstance(error, TransientError)
    assert error.is_transient
    assert error.status_code == 429

    # 503 Service Unavailable
    error = classify_http_error(503, "Service down")
    assert isinstance(error, TransientError)
    assert error.is_transient


def test_classify_http_error_permanent():
    """Test that permanent errors are classified correctly."""
    # 401 Unauthorized
    error = classify_http_error(401, "Bad API key")
    assert isinstance(error, PermanentError)
    assert not error.is_transient
    assert error.status_code == 401

    # 400 Bad Request
    error = classify_http_error(400, "Invalid request")
    assert isinstance(error, PermanentError)


def test_classify_http_error_5xx_default_transient():
    """Test that unknown 5xx errors default to transient."""
    error = classify_http_error(500, "Internal server error")
    assert isinstance(error, TransientError)
    assert error.is_transient


# ---------------------------------------------------------------------------
# Response Validation Tests
# ---------------------------------------------------------------------------


def test_validate_json_response_valid():
    """Test validation of valid JSON response."""
    raw = '{"action": "BUY", "confidence": 0.8}'
    parsed = validate_json_response(raw)
    assert parsed is not None
    assert parsed["action"] == "BUY"
    assert parsed["confidence"] == 0.8


def test_validate_json_response_with_required_keys():
    """Test validation with required keys."""
    raw = '{"action": "BUY", "confidence": 0.8}'
    parsed = validate_json_response(raw, required_keys=["action", "confidence"])
    assert parsed is not None

    # Missing required key
    parsed = validate_json_response(raw, required_keys=["action", "missing"])
    assert parsed is None


def test_validate_json_response_invalid():
    """Test validation of invalid JSON."""
    parsed = validate_json_response("not json")
    assert parsed is None

    parsed = validate_json_response("")
    assert parsed is None


# ---------------------------------------------------------------------------
# Rate Limiting Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_token_bucket_acquire():
    """Test basic token acquisition."""
    bucket = TokenBucket(rate_per_minute=60, provider=ProviderName.DEEPSEEK)

    # Should acquire immediately
    await bucket.acquire(1)
    assert bucket.tokens < 60  # Tokens consumed


@pytest.mark.asyncio
async def test_token_bucket_refill():
    """Test token refill over time."""
    bucket = TokenBucket(rate_per_minute=60, provider=ProviderName.OPENAI)

    # Consume all tokens
    initial = bucket.tokens
    await bucket.acquire(initial)
    assert bucket.tokens < 1

    # Wait long enough to ensure at least one token is refilled
    await asyncio.sleep(2.1)  # Wait >2 seconds for refill at 1 token/second
    await bucket.acquire(1)  # Should succeed after refill


@pytest.mark.asyncio
async def test_token_bucket_singleton():
    """Test that TokenBucket uses singleton pattern per provider."""
    bucket1 = await TokenBucket.get_instance(ProviderName.DEEPSEEK, 60)
    bucket2 = await TokenBucket.get_instance(ProviderName.DEEPSEEK, 60)

    assert bucket1 is bucket2  # Same instance

    # Different provider = different instance
    bucket3 = await TokenBucket.get_instance(ProviderName.OPENAI, 60)
    assert bucket3 is not bucket1


# ---------------------------------------------------------------------------
# DeepSeek Provider Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deepseek_complete_success():
    """Test successful DeepSeek completion."""
    provider = DeepSeekProvider()

    # Mock HTTP response
    mock_response = {
        "choices": [{"message": {"content": '{"action": "BUY", "confidence": 0.85}'}}],
        "usage": {"prompt_tokens": 100, "completion_tokens": 50},
    }

    with patch.object(provider, "_make_request", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = mock_response

        request = AIRequest(
            role=RoleName.SCREENER,
            user_prompt="Analyze BTC",
        )

        response = await provider.complete(
            request,
            system_prompt="You are a trader",
        )

        assert response.role == RoleName.SCREENER
        assert response.provider == ProviderName.DEEPSEEK
        assert response.tokens_in == 100
        assert response.tokens_out == 50
        assert response.cost_usd > 0
        assert response.parsed is not None
        assert response.parsed["action"] == "BUY"
        assert response.error is None


@pytest.mark.asyncio
async def test_deepseek_complete_rate_limiting():
    """Test that rate limiting is applied."""
    provider = DeepSeekProvider()

    # Reset rate limiter to low capacity for test
    bucket = await TokenBucket.get_instance(ProviderName.DEEPSEEK, 2)
    bucket.tokens = 1  # Only 1 token available

    mock_response = {
        "choices": [{"message": {"content": "test"}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5},
    }

    with patch.object(provider, "_make_request", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = mock_response

        request = AIRequest(role=RoleName.SCREENER, user_prompt="Test")

        # First request should succeed
        await provider.complete(request, system_prompt="test")

        # Second request should wait (rate limited)
        # We can't easily test the wait, but we can verify it doesn't fail
        await provider.complete(request, system_prompt="test")


@pytest.mark.asyncio
async def test_deepseek_complete_transient_error_retry():
    """Test retry on transient errors."""
    provider = DeepSeekProvider()

    # Test that _make_request retries internally
    call_count = 0

    # Mock the actual HTTP client request, not _make_request
    # This way the retry decorator is still applied
    with patch("httpx.AsyncClient.request", new_callable=AsyncMock) as mock_http:
        # First 2 calls fail with 503, third succeeds
        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                response = MagicMock()
                response.status_code = 503
                response.text = "Service Unavailable"
                raise httpx.HTTPStatusError("Service Unavailable", request=MagicMock(), response=response)

            # Success on third call
            response = MagicMock()
            response.json.return_value = {
                "choices": [{"message": {"content": "success"}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            }
            response.raise_for_status = MagicMock()
            return response

        mock_http.side_effect = side_effect

        request = AIRequest(role=RoleName.SCREENER, user_prompt="Test")
        response = await provider.complete(request, system_prompt="test")

        # Should have retried (3 attempts total)
        assert call_count == 3
        assert response.error is None
        assert "success" in response.raw_text


@pytest.mark.asyncio
async def test_deepseek_complete_permanent_error_no_retry():
    """Test no retry on permanent errors."""
    provider = DeepSeekProvider()

    call_count = 0

    async def mock_request(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        raise PermanentError("Invalid API key", status_code=401)

    with patch.object(provider, "_make_request", side_effect=mock_request):
        request = AIRequest(role=RoleName.SCREENER, user_prompt="Test")
        response = await provider.complete(request, system_prompt="test")

        assert call_count == 1  # No retries for permanent error
        assert response.error is not None
        assert "Invalid API key" in response.error


@pytest.mark.asyncio
async def test_deepseek_health_check():
    """Test DeepSeek health check."""
    provider = DeepSeekProvider()

    # Mock successful health check
    with patch.object(provider, "_make_request", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = {"data": [{"id": "deepseek-chat"}]}

        result = await provider.health_check()
        assert result is True

    # Mock failed health check
    with patch.object(provider, "_make_request", side_effect=Exception("Network error")):
        result = await provider.health_check()
        assert result is False


# ---------------------------------------------------------------------------
# OpenAI Provider Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_openai_complete_success():
    """Test successful OpenAI completion."""
    provider = OpenAIProvider()

    mock_response = {
        "choices": [{"message": {"content": "Analysis complete"}}],
        "usage": {"prompt_tokens": 150, "completion_tokens": 75},
    }

    with patch.object(provider, "_make_request", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = mock_response

        request = AIRequest(role=RoleName.STRATEGIST, user_prompt="Review risk")
        response = await provider.complete(request, system_prompt="You are a strategist")

        assert response.role == RoleName.STRATEGIST
        assert response.provider == ProviderName.OPENAI
        assert response.model == "o3-mini"
        assert response.cost_usd > 0


@pytest.mark.asyncio
async def test_openai_cost_calculation():
    """Test cost calculation for OpenAI."""
    provider = OpenAIProvider()

    mock_response = {
        "choices": [{"message": {"content": "test"}}],
        "usage": {"prompt_tokens": 1000, "completion_tokens": 1000},
    }

    with patch.object(provider, "_make_request", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = mock_response

        request = AIRequest(role=RoleName.STRATEGIST, user_prompt="Test")
        response = await provider.complete(request, system_prompt="test")

        # o3-mini: $1.10 input, $4.40 output per 1M tokens
        expected_cost = (1000 * 1.10 + 1000 * 4.40) / 1_000_000
        assert abs(response.cost_usd - expected_cost) < 0.0001


# ---------------------------------------------------------------------------
# xAI Provider Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_xai_complete_success():
    """Test successful xAI completion."""
    provider = XAIProvider()

    mock_response = {
        "choices": [{"message": {"content": "News analysis"}}],
        "usage": {"prompt_tokens": 200, "completion_tokens": 100},
    }

    with patch.object(provider, "_make_request", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = mock_response

        request = AIRequest(role=RoleName.FUNDAMENTAL, user_prompt="Analyze news")
        response = await provider.complete(request, system_prompt="You analyze news")

        assert response.provider == ProviderName.XAI
        assert response.model == "grok-4"


# ---------------------------------------------------------------------------
# Ollama Provider Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ollama_complete_success():
    """Test successful Ollama completion."""
    provider = OllamaProvider()

    mock_response = {
        "message": {"content": "Local analysis"},
        "prompt_eval_count": 80,
        "eval_count": 40,
    }

    with patch.object(provider, "_make_request", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = mock_response

        request = AIRequest(role=RoleName.TACTICAL, user_prompt="Analyze chart")
        response = await provider.complete(request, system_prompt="You are tactical")

        assert response.provider == ProviderName.OLLAMA
        assert response.cost_usd == 0.0  # Local = free
        assert response.tokens_in == 80
        assert response.tokens_out == 40


@pytest.mark.asyncio
async def test_ollama_health_check():
    """Test Ollama health check."""
    provider = OllamaProvider()

    # Mock successful health check
    with patch.object(provider, "_make_request", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = {"models": [{"name": "llama3.2"}]}

        result = await provider.health_check()
        assert result is True


# ---------------------------------------------------------------------------
# Integration Tests (with mocked httpx client)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_provider_close():
    """Test provider connection cleanup."""
    provider = DeepSeekProvider()

    # Initialize client
    await provider._get_client()
    assert provider._client is not None

    # Close
    await provider.close()
    assert provider._client is None


@pytest.mark.asyncio
async def test_multiple_providers_different_rate_limits():
    """Test that different providers have independent rate limits."""
    # Create fresh providers to avoid interference from other tests
    deepseek = DeepSeekProvider()
    openai = OpenAIProvider()

    # Get rate limiters
    ds_limiter = await deepseek._get_rate_limiter()
    oa_limiter = await openai._get_rate_limiter()

    # Should be different instances
    assert ds_limiter is not oa_limiter
    assert ds_limiter.provider == ProviderName.DEEPSEEK
    assert oa_limiter.provider == ProviderName.OPENAI

    # Consume DeepSeek tokens
    initial_ds = ds_limiter.tokens
    await ds_limiter.acquire(10)
    assert ds_limiter.tokens < initial_ds

    # OpenAI should be unaffected (approximately at capacity, accounting for time drift)
    assert oa_limiter.tokens >= oa_limiter.capacity - 1


# ---------------------------------------------------------------------------
# Streaming Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deepseek_streaming_success():
    """Test successful streaming with SSE format parsing."""
    provider = DeepSeekProvider()

    # Mock streaming response with SSE format
    mock_lines = [
        "data: " + '{"choices": [{"delta": {"content": "Hello"}}]}',
        "data: " + '{"choices": [{"delta": {"content": " world"}}]}',
        "data: " + '{"choices": [{"delta": {"content": "!"}}]}',
        "data: [DONE]",
    ]

    async def mock_aiter_lines():
        for line in mock_lines:
            yield line

    with patch("httpx.AsyncClient.stream") as mock_stream:
        # Create async context manager mock
        mock_response = MagicMock()
        mock_response.aiter_lines = mock_aiter_lines
        mock_response.raise_for_status = MagicMock()

        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_response)
        mock_cm.__aexit__ = AsyncMock(return_value=None)
        mock_stream.return_value = mock_cm

        request = AIRequest(role=RoleName.TACTICAL, user_prompt="Test streaming")

        chunks = []
        async for chunk in provider.complete_stream(request, system_prompt="test"):
            chunks.append(chunk)

        # Should have 3 content chunks
        assert len(chunks) == 3
        assert chunks == ["Hello", " world", "!"]


@pytest.mark.asyncio
async def test_deepseek_streaming_json_decode_error_resilience():
    """Test streaming handles JSON decode errors gracefully."""
    provider = DeepSeekProvider()

    # Mock streaming response with invalid JSON in one line
    mock_lines = [
        "data: " + '{"choices": [{"delta": {"content": "Hello"}}]}',
        "data: invalid json",  # This should be skipped
        "data: " + '{"choices": [{"delta": {"content": " world"}}]}',
        "data: [DONE]",
    ]

    async def mock_aiter_lines():
        for line in mock_lines:
            yield line

    with patch("httpx.AsyncClient.stream") as mock_stream:
        mock_response = MagicMock()
        mock_response.aiter_lines = mock_aiter_lines
        mock_response.raise_for_status = MagicMock()

        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_response)
        mock_cm.__aexit__ = AsyncMock(return_value=None)
        mock_stream.return_value = mock_cm

        request = AIRequest(role=RoleName.TACTICAL, user_prompt="Test streaming")

        chunks = []
        async for chunk in provider.complete_stream(request, system_prompt="test"):
            chunks.append(chunk)

        # Should skip invalid JSON and get 2 valid chunks
        assert len(chunks) == 2
        assert chunks == ["Hello", " world"]


@pytest.mark.asyncio
async def test_deepseek_streaming_done_marker_handling():
    """Test streaming properly handles [DONE] marker."""
    provider = DeepSeekProvider()

    # Mock streaming response with [DONE] marker
    mock_lines = [
        "data: " + '{"choices": [{"delta": {"content": "Test"}}]}',
        "data: [DONE]",
        "data: " + '{"choices": [{"delta": {"content": "Should not appear"}}]}',
    ]

    async def mock_aiter_lines():
        for line in mock_lines:
            yield line

    with patch("httpx.AsyncClient.stream") as mock_stream:
        mock_response = MagicMock()
        mock_response.aiter_lines = mock_aiter_lines
        mock_response.raise_for_status = MagicMock()

        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_response)
        mock_cm.__aexit__ = AsyncMock(return_value=None)
        mock_stream.return_value = mock_cm

        request = AIRequest(role=RoleName.TACTICAL, user_prompt="Test streaming")

        chunks = []
        async for chunk in provider.complete_stream(request, system_prompt="test"):
            chunks.append(chunk)

        # Should stop at [DONE] marker
        assert len(chunks) == 1
        assert chunks == ["Test"]


@pytest.mark.asyncio
async def test_deepseek_streaming_fallback_on_error():
    """Test streaming falls back to non-streaming on error."""
    provider = DeepSeekProvider()

    # Mock streaming to fail
    with patch("httpx.AsyncClient.stream") as mock_stream:
        mock_stream.side_effect = Exception("Streaming error")

        # Mock non-streaming fallback
        with patch.object(provider, "complete", new_callable=AsyncMock) as mock_complete:
            mock_complete.return_value.raw_text = "Fallback response"

            request = AIRequest(role=RoleName.TACTICAL, user_prompt="Test fallback")

            chunks = []
            async for chunk in provider.complete_stream(request, system_prompt="test"):
                chunks.append(chunk)

            # Should fall back to non-streaming and return single chunk
            assert len(chunks) == 1
            assert "Fallback response" in chunks[0]
            # Verify fallback was called
            mock_complete.assert_called_once()
