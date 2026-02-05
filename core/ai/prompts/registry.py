"""Versioned prompt registry — stores and retrieves system prompts.

Prompts are versioned per role.  The registry supports:
- Loading defaults from ``defaults/`` directory
- Storing new versions (DB-backed in production)
- Retrieving the active prompt for a role
- Listing all versions for audit / A-B testing
"""

from __future__ import annotations

import logging

from core.ai.types import RoleName, SystemPrompt

logger = logging.getLogger(__name__)


class PromptRegistry:
    """In-memory prompt store with versioning.

    In production this will be backed by the ``system_prompts`` DB table.
    For now it serves as a typed interface + defaults loader.
    """

    _prompts: dict[str, SystemPrompt] = {}  # keyed by prompt id

    @classmethod
    def register(cls, prompt: SystemPrompt) -> None:
        """Register a system prompt version."""
        cls._prompts[prompt.id] = prompt
        logger.info(
            "Registered prompt: %s (role=%s, v%d, active=%s)",
            prompt.id,
            prompt.role.value,
            prompt.version,
            prompt.is_active,
        )

    @classmethod
    def get(cls, prompt_id: str) -> SystemPrompt | None:
        """Get a prompt by its ID."""
        return cls._prompts.get(prompt_id)

    @classmethod
    def get_active(cls, role: RoleName) -> SystemPrompt | None:
        """Get the active prompt for a role (highest version with is_active=True)."""
        candidates = [p for p in cls._prompts.values() if p.role == role and p.is_active]
        if not candidates:
            return None
        return max(candidates, key=lambda p: p.version)

    @classmethod
    def list_versions(cls, role: RoleName) -> list[SystemPrompt]:
        """List all prompt versions for a role, newest first."""
        return sorted(
            [p for p in cls._prompts.values() if p.role == role],
            key=lambda p: p.version,
            reverse=True,
        )

    @classmethod
    def load_defaults(cls) -> None:
        """Load the built-in default prompts from ``defaults`` module."""
        from core.ai.prompts.defaults import ALL_DEFAULT_PROMPTS

        for prompt in ALL_DEFAULT_PROMPTS:
            cls.register(prompt)

        logger.info("Loaded %d default prompts", len(ALL_DEFAULT_PROMPTS))

    @classmethod
    def clear(cls) -> None:
        """Clear all registered prompts (for testing)."""
        cls._prompts.clear()
