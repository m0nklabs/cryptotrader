"""Base agent role and role registry."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

from core.ai.providers.base import ProviderRegistry
from core.ai.types import (
    AIRequest,
    AIResponse,
    RoleConfig,
    RoleName,
    RoleVerdict,
)

logger = logging.getLogger(__name__)


class AgentRole(ABC):
    """Abstract base for an agent role in the Multi-Brain topology.

    Each role knows:
    - Which provider/model to use (primary + fallback)
    - Its system prompt key
    - How to parse the LLM response into a ``RoleVerdict``
    """

    def __init__(self, config: RoleConfig) -> None:
        self.config = config

    @property
    def name(self) -> RoleName:
        return self.config.name

    @property
    def weight(self) -> float:
        return self.config.weight

    @abstractmethod
    def build_prompt(self, request: AIRequest) -> str:
        """Build the user-prompt from the AI request context.

        Roles can enrich the prompt with indicator data, news snippets,
        portfolio state, etc. depending on their domain.
        """

    @abstractmethod
    def parse_response(self, response: AIResponse) -> RoleVerdict:
        """Parse the raw LLM response into a structured verdict."""

    async def evaluate(
        self,
        request: AIRequest,
        system_prompt: str,
    ) -> tuple[AIResponse, RoleVerdict]:
        """Run the full evaluation pipeline for this role.

        1. Resolve the provider
        2. Build the enriched prompt
        3. Call the LLM
        4. Parse the response into a verdict

        Falls back to ``fallback_provider`` if the primary fails.
        """
        enriched_prompt = self.build_prompt(request)
        enriched_request = AIRequest(
            role=request.role,
            user_prompt=enriched_prompt,
            context=request.context,
        )

        # Try primary provider
        provider = ProviderRegistry.get(self.config.provider)
        if provider is None:
            logger.error("Provider %s not registered", self.config.provider)
            raise RuntimeError(f"Provider {self.config.provider} not registered")

        response = await provider.complete(
            enriched_request,
            system_prompt=system_prompt,
            model=self.config.model,
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
        )

        # Fallback on error
        if response.error and self.config.fallback_provider:
            logger.warning(
                "Role %s primary failed, trying fallback %s",
                self.name.value,
                self.config.fallback_provider.value,
            )
            fallback = ProviderRegistry.get(self.config.fallback_provider)
            if fallback:
                response = await fallback.complete(
                    enriched_request,
                    system_prompt=system_prompt,
                    model=self.config.fallback_model or fallback.config.default_model,
                    temperature=self.config.temperature,
                    max_tokens=self.config.max_tokens,
                )

        verdict = self.parse_response(response)
        return response, verdict


class RoleRegistry:
    """Registry of active agent roles."""

    _roles: dict[RoleName, AgentRole] = {}

    @classmethod
    def register(cls, role: AgentRole) -> None:
        cls._roles[role.name] = role
        logger.info("Registered AI role: %s", role.name.value)

    @classmethod
    def get(cls, name: RoleName) -> AgentRole | None:
        return cls._roles.get(name)

    @classmethod
    def active_roles(cls) -> list[AgentRole]:
        """Return all enabled roles, ordered by weight (descending)."""
        return sorted(
            [r for r in cls._roles.values() if r.config.enabled],
            key=lambda r: r.weight,
            reverse=True,
        )

    @classmethod
    def clear(cls) -> None:
        cls._roles.clear()
