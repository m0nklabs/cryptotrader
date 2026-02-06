"""Versioned prompt registry — stores and retrieves system prompts.

Prompts are versioned per role.  The registry supports:
- Loading defaults from ``defaults/`` directory
- Storing new versions (DB-backed in production)
- Retrieving the active prompt for a role
- Listing all versions for audit / A-B testing

The registry uses a write-through cache:
- Prompts are loaded from DB on startup
- Writes go to both DB and cache
- Falls back to in-memory defaults if DB is unavailable
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from core.ai.types import RoleName, SystemPrompt

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class PromptRegistry:
    """In-memory prompt store with DB backend and versioning.

    The registry maintains a cache of prompts in memory and syncs with PostgreSQL.
    On startup, prompts are loaded from the DB. If the DB is unavailable, it falls
    back to loading default prompts from the ``defaults`` module.
    """

    _prompts: dict[str, SystemPrompt] = {}  # keyed by prompt id
    _db_enabled: bool = False
    _db_loaded: bool = False
    _activation_lock: asyncio.Lock | None = None  # Lazy-initialized to avoid event loop issues

    @classmethod
    def _get_activation_lock(cls) -> asyncio.Lock:
        """Get or create the activation lock (lazy initialization)."""
        if cls._activation_lock is None:
            cls._activation_lock = asyncio.Lock()
        return cls._activation_lock

    @classmethod
    async def load_from_db(cls, db: AsyncSession) -> None:
        """Load all prompts from the database into memory cache.

        This should be called once on application startup.
        Falls back to loading defaults if DB is empty or unavailable.
        """
        try:
            from db.crud.ai import get_prompts as db_get_prompts

            db_prompts = await db_get_prompts(db)

            if not db_prompts:
                logger.warning("No prompts found in DB, loading defaults")
                cls.load_defaults()
                cls._db_loaded = True
                cls._db_enabled = True
                return

            # Convert DB models to dataclass types
            for db_prompt in db_prompts:
                try:
                    prompt = SystemPrompt(
                        id=db_prompt.id,
                        role=RoleName(db_prompt.role),
                        version=db_prompt.version,
                        content=db_prompt.content,
                        description=db_prompt.description,
                        is_active=db_prompt.is_active,
                        created_at=db_prompt.created_at,
                    )
                    cls._prompts[prompt.id] = prompt
                except ValueError:
                    # Skip prompts with invalid role names (e.g., test roles)
                    logger.warning("Skipping prompt %s with invalid role: %s", db_prompt.id, db_prompt.role)
                    continue

            cls._db_loaded = True
            cls._db_enabled = True
            logger.info("Loaded %d prompts from database", len(db_prompts))

        except Exception as exc:
            logger.error("Failed to load prompts from DB: %s", exc)
            logger.info("Falling back to default prompts")
            cls.load_defaults()
            cls._db_enabled = False

    @classmethod
    def register(cls, prompt: SystemPrompt) -> None:
        """Register a system prompt version (in-memory only).

        For production use, prefer create_prompt() which writes to the DB.
        """
        cls._prompts[prompt.id] = prompt
        logger.info(
            "Registered prompt: %s (role=%s, v%d, active=%s)",
            prompt.id,
            prompt.role.value,
            prompt.version,
            prompt.is_active,
        )

    @classmethod
    async def create_prompt(
        cls,
        db: AsyncSession,
        role: RoleName,
        content: str,
        description: str = "",
        is_active: bool = True,
    ) -> SystemPrompt:
        """Create a new prompt version and write to DB (write-through).

        Automatically assigns the next version number for the role.
        """
        if not cls._db_enabled:
            raise RuntimeError("DB backend is not enabled. Call load_from_db() first.")

        from db.crud.ai import create_prompt as db_create_prompt, get_next_version

        # Get the next version number
        next_version = await get_next_version(db, role.value)
        prompt_id = f"{role.value}_v{next_version}"

        # Write to DB
        db_prompt = await db_create_prompt(
            db,
            prompt_id=prompt_id,
            role=role.value,
            version=next_version,
            content=content,
            description=description,
            is_active=is_active,
        )

        # Update cache
        prompt = SystemPrompt(
            id=db_prompt.id,
            role=role,
            version=db_prompt.version,
            content=db_prompt.content,
            description=db_prompt.description,
            is_active=db_prompt.is_active,
            created_at=db_prompt.created_at,
        )
        cls._prompts[prompt.id] = prompt

        logger.info("Created prompt %s (role=%s, v%d)", prompt_id, role.value, next_version)
        return prompt

    @classmethod
    async def activate_prompt(cls, db: AsyncSession, prompt_id: str) -> SystemPrompt | None:
        """Activate a prompt and deactivate all others for the same role (write-through).

        Returns the activated prompt or None if not found.

        Uses a lock to prevent race conditions when multiple concurrent requests
        try to activate different prompts for the same role.
        """
        if not cls._db_enabled:
            raise RuntimeError("DB backend is not enabled. Call load_from_db() first.")

        async with cls._get_activation_lock():
            from db.crud.ai import activate_prompt as db_activate_prompt

            # Write to DB
            db_prompt = await db_activate_prompt(db, prompt_id)
            if not db_prompt:
                return None

            # Update cache: deactivate all prompts for this role, then activate the target
            prompt_role = db_prompt.role
            for p_id, p in cls._prompts.items():
                if p.role.value == prompt_role:
                    # Create new dataclass with updated is_active
                    cls._prompts[p_id] = SystemPrompt(
                        id=p.id,
                        role=p.role,
                        version=p.version,
                        content=p.content,
                        description=p.description,
                        is_active=(p.id == prompt_id),
                        created_at=p.created_at,
                    )

            logger.info("Activated prompt %s (role=%s)", prompt_id, prompt_role)
            return cls._prompts.get(prompt_id)

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
    def is_db_enabled(cls) -> bool:
        """Check if DB backend is enabled."""
        return cls._db_enabled

    @classmethod
    def clear(cls) -> None:
        """Clear all registered prompts (for testing)."""
        cls._prompts.clear()
        cls._db_loaded = False
        cls._db_enabled = False
