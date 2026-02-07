"""OpenRouter provider adapter (OpenAI-compatible gateway).

OpenRouter exposes an OpenAI-compatible API and can route requests to multiple
upstream models (OpenAI, Anthropic, etc.). We treat it as a distinct provider
so role configs can explicitly choose it.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import random

import httpx

from core.ai.providers.base import LLMProvider, validate_json_response
from core.ai.types import AIRequest, AIResponse, ProviderConfig, ProviderName

logger = logging.getLogger(__name__)


OPENROUTER_CONFIG = ProviderConfig(
    name=ProviderName.OPENROUTER,
    api_key_env="OPENROUTER_API_KEY",
    # Using base_url + "/v1/..." keeps it consistent with other providers.
    base_url="https://openrouter.ai/api",
    # OpenRouter model naming is namespaced (e.g. openai/o3-mini)
    default_model="openai/o3-mini",
    max_tokens=4096,
    temperature=0.0,
    timeout_seconds=90,
    rate_limit_rpm=60,
)


# Pricing per 1M tokens (USD) — best-effort mapping for OpenAI models via OpenRouter.
OPENROUTER_PRICING: dict[str, dict[str, float]] = {
    "openai/o3-mini": {"input": 1.10, "output": 4.40},
    "openai/o3": {"input": 2.00, "output": 8.00},
    "openai/gpt-4.1": {"input": 2.00, "output": 8.00},
}


class OpenRouterProvider(LLMProvider):
    """OpenRouter API adapter.

    Notes:
        - Do not read secrets from ~/.secrets in code; rely on env vars.
        - OpenRouter recommends sending HTTP-Referer and X-Title. We include
          them when present as env vars.
    """

    def __init__(self, config: ProviderConfig | None = None) -> None:
        super().__init__(config or OPENROUTER_CONFIG)

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            api_key = os.environ.get(self.config.api_key_env, "")

            headers: dict[str, str] = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }

            # Optional but recommended by OpenRouter
            referer = os.environ.get("OPENROUTER_HTTP_REFERER", "").strip()
            if referer:
                headers["HTTP-Referer"] = referer
            title = os.environ.get("OPENROUTER_X_TITLE", "").strip()
            if title:
                headers["X-Title"] = title

            self._client = httpx.AsyncClient(
                base_url=self.config.base_url,
                headers=headers,
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
        """Send an OpenAI-compatible chat-completion request via OpenRouter."""

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
            logger.error("OpenRouter request failed: %s", exc)
            return self._make_error_response(request, str(exc), latency)

        latency = self._elapsed_ms(start)
        choice = data["choices"][0]
        usage = data.get("usage", {})
        tokens_in = usage.get("prompt_tokens", 0)
        tokens_out = usage.get("completion_tokens", 0)

        pricing = OPENROUTER_PRICING.get(model, {"input": 0.0, "output": 0.0})
        cost = (tokens_in * pricing["input"] + tokens_out * pricing["output"]) / 1_000_000

        raw_text = choice["message"]["content"]
        parsed = validate_json_response(raw_text)

        return AIResponse(
            role=request.role,
            provider=ProviderName.OPENROUTER,
            model=model,
            raw_text=raw_text,
            parsed=parsed,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            latency_ms=latency,
            cost_usd=cost,
        )

    async def health_check(self) -> bool:
        """Check if OpenRouter API is reachable."""
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
                pass
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
        """Stream chat-completion response from OpenRouter with retry logic."""
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

                delay = min(base_delay * (2**attempt), max_delay)
                delay *= 0.5 + random.random()

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
