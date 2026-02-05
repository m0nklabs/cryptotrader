"""Base LLM provider interface and provider registry."""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from typing import Any

from core.ai.types import AIRequest, AIResponse, ProviderConfig, ProviderName

logger = logging.getLogger(__name__)


class LLMProvider(ABC):
    """Abstract base class for all LLM provider adapters.

    Each provider (DeepSeek, OpenAI, xAI, Ollama, etc.) implements this
    interface.  The router calls ``complete()`` and the adapter handles
    serialisation, auth, rate-limiting, and response parsing.
    """

    def __init__(self, config: ProviderConfig) -> None:
        self.config = config
        self._client: Any = None  # lazy-initialised httpx/SDK client

    @property
    def name(self) -> ProviderName:
        return self.config.name

    # ------------------------------------------------------------------
    # Abstract interface
    # ------------------------------------------------------------------

    @abstractmethod
    async def complete(
        self,
        request: AIRequest,
        *,
        system_prompt: str,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AIResponse:
        """Send a chat-completion request and return a structured response.

        Args:
            request: The AI request (role, user prompt, context).
            system_prompt: The system prompt to prepend.
            model: Override the provider's default model.
            temperature: Override the default temperature.
            max_tokens: Override the default max tokens.

        Returns:
            An ``AIResponse`` with timing, cost, and parsed content.
        """

    @abstractmethod
    async def health_check(self) -> bool:
        """Return ``True`` if the provider is reachable and authenticated."""

    async def close(self) -> None:
        """Close any open HTTP connections."""
        if self._client is not None and hasattr(self._client, "aclose"):
            await self._client.aclose()
            self._client = None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _start_timer(self) -> float:
        return time.monotonic()

    def _elapsed_ms(self, start: float) -> float:
        return round((time.monotonic() - start) * 1000, 2)

    def _make_error_response(
        self,
        request: AIRequest,
        error: str,
        latency_ms: float = 0.0,
    ) -> AIResponse:
        """Build an error AIResponse without raising."""
        return AIResponse(
            role=request.role,
            provider=self.config.name,
            model=self.config.default_model,
            raw_text="",
            error=error,
            latency_ms=latency_ms,
        )


class ProviderRegistry:
    """Singleton registry mapping ``ProviderName`` → ``LLMProvider`` instances.

    Providers register themselves at startup and the router looks them up
    by name at request time.
    """

    _providers: dict[ProviderName, LLMProvider] = {}

    @classmethod
    def register(cls, provider: LLMProvider) -> None:
        """Register a provider instance."""
        cls._providers[provider.name] = provider
        logger.info("Registered LLM provider: %s", provider.name.value)

    @classmethod
    def get(cls, name: ProviderName) -> LLMProvider | None:
        """Get a registered provider by name."""
        return cls._providers.get(name)

    @classmethod
    def all(cls) -> dict[ProviderName, LLMProvider]:
        """Return all registered providers."""
        return dict(cls._providers)

    @classmethod
    async def close_all(cls) -> None:
        """Gracefully close all provider connections."""
        for provider in cls._providers.values():
            await provider.close()
        cls._providers.clear()
