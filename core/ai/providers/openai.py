"""OpenAI provider adapter (o3-mini, o3, GPT-4.1)."""

from __future__ import annotations

import asyncio
import json
import logging
import os

import httpx

from core.ai.providers.base import LLMProvider, calculate_backoff_delay, validate_json_response
from core.ai.types import AIRequest, AIResponse, ProviderConfig, ProviderName

logger = logging.getLogger(__name__)

OPENAI_CONFIG = ProviderConfig(
    name=ProviderName.OPENAI,
    api_key_env="OPENAI_API_KEY",
    base_url="https://api.openai.com",
    default_model="o3-mini",
    max_tokens=4096,
    temperature=0.0,
    timeout_seconds=90,
    rate_limit_rpm=60,
)

# Pricing per 1M tokens (USD) — from research doc 02
OPENAI_PRICING: dict[str, dict[str, float]] = {
    "o3-mini": {"input": 1.10, "output": 4.40},
    "o3": {"input": 2.00, "output": 8.00},
    "gpt-4.1": {"input": 2.00, "output": 8.00},
}


class OpenAIProvider(LLMProvider):
    """OpenAI API adapter (reasoning models o3/o3-mini, GPT-4.1).

    Uses the standard chat completions endpoint.
    """

    def __init__(self, config: ProviderConfig | None = None) -> None:
        super().__init__(config or OPENAI_CONFIG)

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
        """Send a chat-completion request to OpenAI."""
        if model is None:
            model = request.override_model if request.override_model is not None else self.config.default_model
        if temperature is None:
            temperature = (
                request.override_temperature
                if request.override_temperature is not None
                else self.config.temperature
            )
        if max_tokens is None:
            max_tokens = self.config.max_tokens

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
            logger.error("OpenAI request failed: %s", exc)
            return self._make_error_response(request, str(exc), latency)

        latency = self._elapsed_ms(start)
        choice = data["choices"][0]
        usage = data.get("usage", {})
        tokens_in = usage.get("prompt_tokens", 0)
        tokens_out = usage.get("completion_tokens", 0)

        pricing = OPENAI_PRICING.get(model, {"input": 0.0, "output": 0.0})
        cost = (tokens_in * pricing["input"] + tokens_out * pricing["output"]) / 1_000_000

        raw_text = choice["message"]["content"]
        parsed = validate_json_response(raw_text)

        return AIResponse(
            role=request.role,
            provider=ProviderName.OPENAI,
            model=model,
            raw_text=raw_text,
            parsed=parsed,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            latency_ms=latency,
            cost_usd=cost,
        )

    async def health_check(self) -> bool:
        """Check if OpenAI API is reachable."""
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
        """Single streaming attempt with error classification and rate limiting."""
        from core.ai.providers.base import TransientError, classify_http_error

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
                response.raise_for_status()

                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data_str = line[6:]
                    if data_str.strip() == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue
                    delta = chunk.get("choices", [{}])[0].get("delta", {})
                    content = delta.get("content", "")
                    if content:
                        yield content
        except httpx.HTTPStatusError as e:
            status_code = e.response.status_code if e.response is not None else None
            message = str(e)
            try:
                if e.response is not None:
                    body_text = e.response.text or ""
                    if body_text:
                        message = f"{message} | body: {body_text[:512]}"
            except Exception:
                logger.debug("Failed to read OpenAI error response body", exc_info=True)
            if status_code is None:
                raise TransientError(f"HTTP error without status code: {message}") from e
            error = classify_http_error(status_code, message)
            raise error from e
        except (httpx.TimeoutException, httpx.NetworkError, httpx.ConnectError) as e:
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
        """Stream chat-completion response from OpenAI with retry logic."""
        from core.ai.providers.base import PermanentError, TransientError

        if model is None:
            model = request.override_model if request.override_model is not None else self.config.default_model
        if temperature is None:
            temperature = (
                request.override_temperature
                if request.override_temperature is not None
                else self.config.temperature
            )
        if max_tokens is None:
            max_tokens = self.config.max_tokens

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
                return
            except TransientError as e:
                if attempt >= max_retries:
                    logger.error(
                        "Max retries (%d) exceeded for streaming: %s",
                        max_retries,
                        e,
                    )
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
                logger.error("Unexpected error in streaming: %s", e)
                raise
