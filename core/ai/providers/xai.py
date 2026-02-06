"""xAI (Grok) provider adapter."""

from __future__ import annotations

import json
import logging
import os

import httpx

from core.ai.providers.base import LLMProvider
from core.ai.types import AIRequest, AIResponse, ProviderConfig, ProviderName

logger = logging.getLogger(__name__)

XAI_CONFIG = ProviderConfig(
    name=ProviderName.XAI,
    api_key_env="XAI_API_KEY",
    base_url="https://api.x.ai",
    default_model="grok-4",
    max_tokens=4096,
    temperature=0.0,
    timeout_seconds=90,
    rate_limit_rpm=60,
)

# Pricing per 1M tokens (USD) — from research doc 02
XAI_PRICING: dict[str, dict[str, float]] = {
    "grok-4": {"input": 3.00, "output": 15.00},
    "grok-3-mini": {"input": 0.30, "output": 0.50},
}


class XAIProvider(LLMProvider):
    """xAI (Grok) API adapter.

    Grok has real-time web search and X/Twitter integration — ideal for
    the Fundamental/News agent role.
    Uses the OpenAI-compatible endpoint.
    """

    def __init__(self, config: ProviderConfig | None = None) -> None:
        super().__init__(config or XAI_CONFIG)

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
        """Send a chat-completion request to xAI."""
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
            logger.error("xAI request failed: %s", exc)
            return self._make_error_response(request, str(exc), latency)

        latency = self._elapsed_ms(start)
        choice = data["choices"][0]
        usage = data.get("usage", {})
        tokens_in = usage.get("prompt_tokens", 0)
        tokens_out = usage.get("completion_tokens", 0)

        pricing = XAI_PRICING.get(model, {"input": 0.0, "output": 0.0})
        cost = (tokens_in * pricing["input"] + tokens_out * pricing["output"]) / 1_000_000

        raw_text = choice["message"]["content"]
        parsed = None
        try:
            parsed = json.loads(raw_text)
        except (json.JSONDecodeError, TypeError):
            pass

        return AIResponse(
            role=request.role,
            provider=ProviderName.XAI,
            model=model,
            raw_text=raw_text,
            parsed=parsed,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            latency_ms=latency,
            cost_usd=cost,
        )

    async def health_check(self) -> bool:
        """Check if xAI API is reachable."""
        try:
            client = await self._get_client()
            data = await self._make_request(client, "GET", "/v1/models")
            return True
        except Exception:
            return False
