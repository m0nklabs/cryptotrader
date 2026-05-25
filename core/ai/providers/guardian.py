"""Guardian provider — local llama_cpp_guardian proxy adapter.

Uses the OpenAI-compatible /v1/chat/completions endpoint on the Guardian
proxy (default port 11434). Bearer token from GUARDIAN_API_KEY env var.

This is the correct provider for all local multi-agent work.
DO NOT call port 11440 (raw llama-server) directly — always go through Guardian.
"""

from __future__ import annotations

import logging
import os

import httpx

from core.ai.providers.base import LLMProvider, validate_json_response
from core.ai.types import AIRequest, AIResponse, ProviderConfig, ProviderName

logger = logging.getLogger(__name__)

GUARDIAN_CONFIG = ProviderConfig(
    name=ProviderName.GUARDIAN,
    api_key_env="GUARDIAN_API_KEY",
    base_url=os.environ.get("GUARDIAN_HOST", "http://localhost:11434"),
    default_model=os.environ.get("GUARDIAN_DEFAULT_MODEL", "GLM-4.7-Flash"),
    max_tokens=8192,
    temperature=0.0,
    timeout_seconds=300,  # dossier generation can take a while
    rate_limit_rpm=999,
)


class GuardianProvider(LLMProvider):
    """llama_cpp_guardian proxy — OpenAI-compatible local LLM backend.

    Routes to the Guardian on port 11434 which manages model switching,
    auth, and request queuing transparently.

    Features:
    - Bearer token auth via GUARDIAN_API_KEY env var
    - Auto model-switch: just set ``model`` to a Guardian model name
    - Cost is always $0 (local inference)
    - Compatible with all OpenAI-compat consumers
    """

    def __init__(self, config: ProviderConfig | None = None) -> None:
        super().__init__(config or GUARDIAN_CONFIG)

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            headers: dict[str, str] = {"Content-Type": "application/json"}
            api_key = os.environ.get(self.config.api_key_env, "") if self.config.api_key_env else ""
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"
            self._client = httpx.AsyncClient(
                base_url=self.config.base_url,
                timeout=httpx.Timeout(self.config.timeout_seconds),
                headers=headers,
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
        """Send a chat/completions request to the Guardian proxy."""
        if model is None:
            model = request.override_model or self.config.default_model
        if temperature is None:
            temperature = (
                request.override_temperature if request.override_temperature is not None else self.config.temperature
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
                    "stream": False,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                },
            )
        except Exception as exc:
            latency = self._elapsed_ms(start)
            logger.error("Guardian request failed: %s", exc)
            return self._make_error_response(request, str(exc), latency)

        latency = self._elapsed_ms(start)

        # OpenAI-compat response format
        choices = data.get("choices", [])
        raw_text = choices[0]["message"]["content"] if choices else ""

        usage = data.get("usage", {})
        tokens_in = usage.get("prompt_tokens", 0)
        tokens_out = usage.get("completion_tokens", 0)

        parsed = validate_json_response(raw_text)

        logger.debug(
            "Guardian: model=%s tokens_in=%d tokens_out=%d latency=%.0fms",
            model,
            tokens_in,
            tokens_out,
            latency,
        )

        return AIResponse(
            role=request.role,
            provider=ProviderName.GUARDIAN,
            model=model,
            raw_text=raw_text,
            parsed=parsed,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            latency_ms=latency,
            cost_usd=0.0,
        )

    async def health_check(self) -> bool:
        """Check if the Guardian proxy is reachable.

        Short-circuits when GUARDIAN_API_KEY is absent.
        """
        api_key = os.environ.get(self.config.api_key_env, "")
        if not api_key:
            logger.debug(
                "GuardianProvider.health_check: short-circuit — " "GUARDIAN_API_KEY not set",
            )
            return False
        try:
            client = await self._get_client()
            await self._make_request(client, "GET", "/health")
            return True
        except Exception:
            return False
