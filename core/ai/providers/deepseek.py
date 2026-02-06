"""DeepSeek provider adapter (R1 reasoning + V3.2 chat)."""

from __future__ import annotations

import json
import logging
import os

import httpx

from core.ai.providers.base import LLMProvider
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

        # Acquire rate limit token before making request
        rate_limiter = await self._get_rate_limiter()
        await rate_limiter.acquire()

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

        # Try to parse JSON from the response
        parsed = None
        try:
            parsed = json.loads(raw_text)
        except (json.JSONDecodeError, TypeError):
            pass

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

    async def complete_stream(
        self,
        request: AIRequest,
        *,
        system_prompt: str,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ):
        """Stream chat-completion response from DeepSeek.
        
        Yields text chunks as they arrive from the API.
        """
        model = model or request.override_model or self.config.default_model
        temperature = temperature or request.override_temperature or self.config.temperature
        max_tokens = max_tokens or self.config.max_tokens

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": request.user_prompt},
        ]

        # Acquire rate limit token
        rate_limiter = await self._get_rate_limiter()
        await rate_limiter.acquire()

        try:
            client = await self._get_client()
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
        except Exception as e:
            logger.error("DeepSeek streaming failed: %s", e)
            # Fall back to non-streaming
            async for chunk in super().complete_stream(
                request,
                system_prompt=system_prompt,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
            ):
                yield chunk
