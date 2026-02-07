"""Ollama provider adapter — local inference.

Migrated from core.signals.analysis.OllamaClient to fit the
Multi-Brain provider interface.
"""

from __future__ import annotations

import asyncio
import json
import logging

import httpx

from core.ai.providers.base import LLMProvider, calculate_backoff_delay, validate_json_response
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

        parsed = validate_json_response(raw_text)

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
            await self._make_request(client, "GET", "/api/tags")
            return True
        except Exception:
            return False

    async def _attempt_streaming(
        self,
        client: httpx.AsyncClient,
        model: str,
        messages: list[dict],
        temperature: float,
    ):
        """Single streaming attempt with error classification and rate limiting."""
        from core.ai.providers.base import TransientError, classify_http_error

        rate_limiter = await self._get_rate_limiter()
        await rate_limiter.acquire()

        try:
            async with client.stream(
                "POST",
                "/api/chat",
                json={
                    "model": model,
                    "messages": messages,
                    "stream": True,
                    "options": {
                        "temperature": temperature,
                    },
                },
            ) as response:
                response.raise_for_status()

                async for line in response.aiter_lines():
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if chunk.get("done") is True:
                        break
                    message = chunk.get("message", {})
                    content = message.get("content", "")
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
                logger.debug("Failed to read Ollama error response body", exc_info=True)
            if e.response is None:
                raise TransientError(f"HTTP error without response: {message}", status_code=None) from e
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
        """Stream chat response from Ollama with retry logic."""
        from core.ai.providers.base import PermanentError, TransientError

        model = model or request.override_model or self.config.default_model
        temperature = temperature or request.override_temperature or self.config.temperature

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
                async for chunk in self._attempt_streaming(client, model, messages, temperature):
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
