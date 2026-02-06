#!/usr/bin/env python3
"""Seed default AI configurations and prompts.

This script populates the database with:
1. Default role configurations (4 roles with their default providers/models)
2. Default system prompts (from core/ai/prompts/defaults.py)

The script is idempotent - it checks before inserting to avoid duplicates.

Usage:
    export DATABASE_URL="postgresql://user:pass@host:port/db"
    python scripts/seed_ai_defaults.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from core.ai.types import RoleName, ProviderName
from core.ai.prompts.defaults import ALL_DEFAULT_PROMPTS
from db.crud.ai import create_role_config, get_role_config, create_prompt, get_prompts


# ---------------------------------------------------------------------------
# Default role configurations (from issue #205)
# ---------------------------------------------------------------------------
# Note: system_prompt_id values reference prompts that will be created by DEFAULT_PROMPTS.
# The seeding order in main() ensures prompts are created before role configs, so these
# foreign keys will be valid. The system_prompt_id column is nullable, so the reference is optional.

DEFAULT_ROLE_CONFIGS = [
    {
        "name": RoleName.SCREENER.value,
        "provider": ProviderName.DEEPSEEK.value,
        "model": "deepseek-chat",  # V3.2
        "system_prompt_id": "screener_v1",
        "temperature": 0.0,
        "max_tokens": 4096,
        "weight": 0.5,
        "enabled": True,
    },
    {
        "name": RoleName.TACTICAL.value,
        "provider": ProviderName.DEEPSEEK.value,
        "model": "deepseek-reasoner",  # R1
        "system_prompt_id": "tactical_v1",
        "temperature": 0.0,
        "max_tokens": 4096,
        "weight": 1.5,
        "enabled": True,
    },
    {
        "name": RoleName.FUNDAMENTAL.value,
        "provider": ProviderName.XAI.value,
        "model": "grok-4",
        "system_prompt_id": "fundamental_v1",
        "temperature": 0.0,
        "max_tokens": 4096,
        "weight": 1.0,
        "enabled": True,
    },
    {
        "name": RoleName.STRATEGIST.value,
        "provider": ProviderName.OPENAI.value,
        "model": "o3-mini",
        "system_prompt_id": "strategist_v1",
        "temperature": 0.0,
        "max_tokens": 4096,
        "weight": 1.2,
        "enabled": True,
    },
]


async def seed_role_configs(session: AsyncSession) -> None:
    """Seed default role configurations."""
    print("Seeding role configurations...")

    for config_data in DEFAULT_ROLE_CONFIGS:
        existing = await get_role_config(session, config_data["name"])
        if existing:
            print(f"  ✓ Role config '{config_data['name']}' already exists, skipping")
            continue

        await create_role_config(session, **config_data)
        print(f"  ✓ Created role config: {config_data['name']} ({config_data['provider']}/{config_data['model']})")


async def seed_system_prompts(session: AsyncSession) -> None:
    """Seed default system prompts."""
    print("Seeding system prompts...")

    for prompt in ALL_DEFAULT_PROMPTS:
        # Check if prompt already exists
        existing_prompts = await get_prompts(session, role=prompt.role.value)
        if any(p.id == prompt.id for p in existing_prompts):
            print(f"  ✓ Prompt '{prompt.id}' already exists, skipping")
            continue

        await create_prompt(
            session,
            prompt_id=prompt.id,
            role=prompt.role.value,
            version=prompt.version,
            content=prompt.content,
            description=prompt.description,
            is_active=prompt.is_active,
        )
        print(f"  ✓ Created prompt: {prompt.id} (role={prompt.role.value}, v{prompt.version})")


async def main() -> int:
    """Main seeding function."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print(
            "❌ ERROR: DATABASE_URL environment variable is not set.\n"
            "   Expected format: postgresql://user:password@host:port/database\n"
            "   Async format is also supported: postgresql+asyncpg://user:password@host:port/database"
        )
        return 1

    # Convert to async URL if needed
    if database_url.startswith("postgresql://") and "asyncpg" not in database_url:
        database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    elif database_url.startswith("postgres://") and "asyncpg" not in database_url:
        database_url = database_url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif not database_url.startswith("postgresql+asyncpg://"):
        print(f"❌ ERROR: Unsupported DATABASE_URL format: {database_url}")
        return 1

    print(f"Connecting to database: {database_url.split('@')[-1]}")  # Don't print credentials

    try:
        # Create async engine and session
        engine = create_async_engine(database_url, echo=False)
        async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        async with async_session() as session:
            # Seed prompts first (role configs reference them)
            await seed_system_prompts(session)

            # Then seed role configs
            await seed_role_configs(session)

        print("\n✅ Seeding completed successfully!")
        return 0

    except Exception as exc:
        print(f"\n❌ ERROR: {exc}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
