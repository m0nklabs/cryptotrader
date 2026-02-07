"""DeepSeek provider adapter (R1 reasoning + V3.2 chat)."""

from __future__ import annotations

import json
import logging
import os

import httpx

from core.ai.providers.base import (
    LLMProvider,
    TransientError,
    calculate_backoff_delay,
    validate_json_response,
)
from core.ai.types import AIRequest, AIResponse, ProviderConfig, ProviderName

logger = logging.getLogger(__name__)

# Default configs for the two DeepSeek models we use
DEEPSEEK_R1_CONFIG = ProviderConfig(
    name=ProviderName.DEEPSEEK,
    api_key_env="DEEPSEEK_API_KEY",
    base_url="https://api.deepseek.com",
    default_model="deepseek-reasoner",  # R1
    max_tokens=8192,
    temperature=0.0,
    timeout_seconds=120,  # R1 thinks longer
    rate_limit_rpm=60,
)

DEEPSEEK_V3_CONFIG = ProviderConfig(
    name=ProviderName.DEEPSEEK,
    api_key_env="DEEPSEEK_API_KEY",
    base_url="https://api.deepseek.com",
    default_model="deepseek-chat",  # V3.2
    max_tokens=4096,
    temperature=0.0,
    timeout_seconds=60,
    rate_limit_rpm=60,
)

# Pricing per 1M tokens (USD) — updated from research doc 02
DEEPSEEK_PRICING: dict[str, dict[str, float]] = {
    "deepseek-reasoner": {"input": 0.55, "output": 2.19},
    "deepseek-chat": {"input": 0.27, "output": 1.10},
}


class DeepSeekProvider(LLMProvider):
    """DeepSeek API adapter supporting both R1 and V3.2 models.

    Uses the OpenAI-compatible chat completions endpoint.
    """

    def __init__(self, config: ProviderConfig | None = None) -> None:
        super().__init__(config or DEEPSEEK_R1_CONFIG)

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            api_key = os.environ.get(self.config.api_key_env, "")
            self._client = httpx.AsyncClient(
                base_url=self.config.base_url,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                timeout=httpx.Timeout(self.config.timeout_seconds),
            )
        return self._client

    async def complete(
        self,
        request: AIRequest,
        *,
        system_prompt: str,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AIResponse:
        """Send a chat-completion request to DeepSeek."""
        model = model or request.override_model or self.config.default_model
        temperature = temperature or request.override_temperature or self.config.temperature
        max_tokens = max_tokens or self.config.max_tokens

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": request.user_prompt},
        ]

        start = self._start_timer()
        try:
            client = await self._get_client()
            data = await self._make_request(
                client,
                "POST",
                "/v1/chat/completions",
                json={
                    "model": model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                },
            )
        except Exception as exc:
            latency = self._elapsed_ms(start)
            logger.error("DeepSeek request failed: %s", exc)
            return self._make_error_response(request, str(exc), latency)

        latency = self._elapsed_ms(start)
        choice = data["choices"][0]
        usage = data.get("usage", {})
        tokens_in = usage.get("prompt_tokens", 0)
        tokens_out = usage.get("completion_tokens", 0)

        # Calculate cost
        pricing = DEEPSEEK_PRICING.get(model, {"input": 0.0, "output": 0.0})
        cost = (tokens_in * pricing["input"] + tokens_out * pricing["output"]) / 1_000_000

        raw_text = choice["message"]["content"]

        parsed = validate_json_response(raw_text)

        return AIResponse(
            role=request.role,
            provider=ProviderName.DEEPSEEK,
            model=model,
            raw_text=raw_text,
            parsed=parsed,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            latency_ms=latency,
            cost_usd=cost,
        )

    async def health_check(self) -> bool:
        """Check if DeepSeek API is reachable."""
        try:
            client = await self._get_client()
            await self._make_request(client, "GET", "/v1/models")
            return True
        except Exception:
            return False

    async def _attempt_streaming(
        self,
        client: httpx.AsyncClient,
        model: str,
        messages: list[dict],
        temperature: float,
        max_tokens: int,
    ):
        """Single streaming attempt with error classification and rate limiting.

        This method is called by the retry logic in complete_stream.
        Rate limiting happens per attempt (including retries).

        Args:
            client: HTTP client to use
            model: Model name
            messages: Chat messages
            temperature: Temperature setting
            max_tokens: Max tokens setting

        Yields:
            str: Text chunks as they arrive

        Raises:
            TransientError: For retry-able errors (429, 503, network issues)
            PermanentError: For non-retry-able errors (401, 400, etc.)
        """
        from core.ai.providers.base import classify_http_error

        # Acquire rate limit token for each streaming attempt (including retries)
        rate_limiter = await self._get_rate_limiter()
        await rate_limiter.acquire()

        try:
            async with client.stream(
                "POST",
                "/v1/chat/completions",
                json={
                    "model": model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "stream": True,
                },
            ) as response:
                # Raise for HTTP errors (will be caught and classified below)
                response.raise_for_status()

                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data_str = line[6:]  # Remove "data: " prefix
                        if data_str.strip() == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data_str)
                            delta = chunk.get("choices", [{}])[0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                yield content
                        except json.JSONDecodeError:
                            continue
        except httpx.HTTPStatusError as e:
            # Classify HTTP errors, including a truncated response body for debugging
            status_code = e.response.status_code if e.response is not None else None
            message = str(e)
            try:
                if e.response is not None:
                    body_text = e.response.text or ""
                    if body_text:
                        # Truncate body to avoid huge logs but keep it useful
                        preview = body_text[:512]
                        message = f"{message} | body: {preview}"
            except Exception:
                # If reading the body fails for any reason, fall back to the base message
                logger.debug("Failed to read DeepSeek error response body", exc_info=True)
            if status_code is None:
                raise TransientError(f"HTTP error without status code: {message}") from e
            error = classify_http_error(status_code, message)
            raise error from e
        except (httpx.TimeoutException, httpx.NetworkError, httpx.ConnectError) as e:
            # Network errors are transient
            from core.ai.providers.base import TransientError

            raise TransientError(f"Network error: {e}", status_code=None) from e

    async def complete_stream(
        self,
        request: AIRequest,
        *,
        system_prompt: str,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ):
        """Stream chat-completion response from DeepSeek with retry logic.

        Implements the same retry and error classification as non-streaming requests.
        Transient errors (429, 503, network issues) are retried with exponential backoff.
        Permanent errors (401, 400, etc.) fail fast.

        Args:
            request: The AI request (role, user prompt, context).
            system_prompt: The system prompt to prepend.
            model: Override the provider's default model.
            temperature: Override the default temperature.
            max_tokens: Override the default max tokens.

        Yields:
            str: Text chunks as they arrive from the API.
        """
        import asyncio

        from core.ai.providers.base import PermanentError, TransientError

        model = model or request.override_model or self.config.default_model
        temperature = temperature or request.override_temperature or self.config.temperature
        max_tokens = max_tokens or self.config.max_tokens

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": request.user_prompt},
        ]

        client = await self._get_client()
        max_retries = 3
        base_delay = 1.0
        max_delay = 10.0

        for attempt in range(max_retries + 1):
            try:
                async for chunk in self._attempt_streaming(client, model, messages, temperature, max_tokens):
                    yield chunk
                return  # Success, exit retry loop
            except TransientError as e:
                if attempt >= max_retries:
                    logger.error(
                        "Max retries (%d) exceeded for streaming: %s",
                        max_retries,
                        e,
                    )
                    # Fall back to non-streaming as last resort
                    logger.info("Falling back to non-streaming mode")
                    async for chunk in super().complete_stream(
                        request,
                        system_prompt=system_prompt,
                        model=model,
                        temperature=temperature,
                        max_tokens=max_tokens,
                    ):
                        yield chunk
                    return

                # Calculate delay with exponential backoff and jitter
                delay = calculate_backoff_delay(attempt, base_delay, max_delay)

                logger.warning(
                    "Transient error in streaming (attempt %d/%d): %s. Retrying in %.2fs",
                    attempt + 1,
                    max_retries + 1,
                    e,
                    delay,
                )
                await asyncio.sleep(delay)
            except PermanentError as e:
                logger.error("Permanent error in streaming: %s. Not retrying.", e)
                raise
            except Exception as e:
                # Unexpected errors - fail fast
                logger.error("Unexpected error in streaming: %s", e)
                raise
