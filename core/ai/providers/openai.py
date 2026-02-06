"""OpenAI provider adapter (o3-mini, o3, GPT-4.1)."""

from __future__ import annotations

import json
import logging
import os

import httpx

from core.ai.providers.base import LLMProvider
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
        parsed = None
        try:
            parsed = json.loads(raw_text)
        except (json.JSONDecodeError, TypeError):
            pass

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
