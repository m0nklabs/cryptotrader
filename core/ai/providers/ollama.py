"""Ollama provider adapter — local inference.

Migrated from core.signals.analysis.OllamaClient to fit the
Multi-Brain provider interface.
"""

from __future__ import annotations

import json
import logging

import httpx

from core.ai.providers.base import LLMProvider
from core.ai.types import AIRequest, AIResponse, ProviderConfig, ProviderName

logger = logging.getLogger(__name__)

OLLAMA_CONFIG = ProviderConfig(
    name=ProviderName.OLLAMA,
    api_key_env="",  # no auth for local Ollama
    base_url="http://localhost:11434",
    default_model="llama3.2",
    max_tokens=4096,
    temperature=0.0,
    timeout_seconds=120,
    rate_limit_rpm=999,  # local = no rate limit
)


class OllamaProvider(LLMProvider):
    """Ollama local-inference adapter.

    Wraps the Ollama REST API (``/api/chat``).
    No API key required — runs locally.
    Cost is always $0.
    """

    def __init__(self, config: ProviderConfig | None = None) -> None:
        super().__init__(config or OLLAMA_CONFIG)

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.config.base_url,
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
        """Send a chat request to local Ollama instance."""
        model = model or request.override_model or self.config.default_model
        temperature = temperature or request.override_temperature or self.config.temperature

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": request.user_prompt},
        ]

        # Acquire rate limit token (though local Ollama has no real limit)
        rate_limiter = await self._get_rate_limiter()
        await rate_limiter.acquire()

        start = self._start_timer()
        try:
            client = await self._get_client()
            data = await self._make_request(
                client,
                "POST",
                "/api/chat",
                json={
                    "model": model,
                    "messages": messages,
                    "stream": False,
                    "options": {
                        "temperature": temperature,
                    },
                },
            )
        except Exception as exc:
            latency = self._elapsed_ms(start)
            logger.error("Ollama request failed: %s", exc)
            return self._make_error_response(request, str(exc), latency)

        latency = self._elapsed_ms(start)
        raw_text = data.get("message", {}).get("content", "")

        # Ollama provides eval_count / prompt_eval_count
        tokens_in = data.get("prompt_eval_count", 0)
        tokens_out = data.get("eval_count", 0)

        parsed = None
        try:
            parsed = json.loads(raw_text)
        except (json.JSONDecodeError, TypeError):
            pass

        return AIResponse(
            role=request.role,
            provider=ProviderName.OLLAMA,
            model=model,
            raw_text=raw_text,
            parsed=parsed,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            latency_ms=latency,
            cost_usd=0.0,  # local = free
        )

    async def health_check(self) -> bool:
        """Check if Ollama is running locally."""
        try:
            client = await self._get_client()
            data = await self._make_request(client, "GET", "/api/tags")
            return True
        except Exception:
            return False
