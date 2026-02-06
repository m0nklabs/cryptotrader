"""Integration tests for AI database layer.

Tests the full CRUD cycle for:
- System prompts
- Role configurations
- Usage logging
- Decision logging
- PromptRegistry DB backend

Requires DATABASE_URL to be set and PostgreSQL running.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable

import pytest
import pytest_asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from core.ai.types import RoleName
from core.ai.prompts.registry import PromptRegistry
from db.crud.ai import (
    create_role_config,
    get_role_config,
    get_role_configs,
    update_role_config,
    create_prompt,
    get_prompts,
    get_active_prompt,
    activate_prompt,
    get_next_version,
    log_usage,
    get_usage_summary,
    log_decision,
    get_decisions,
)


def _iter_sql_statements(sql: str) -> Iterable[str]:
    """Split a SQL script into executable statements.

    Supports:
    - `--` line comments
    - quoted strings (single and double quotes)

    This is intentionally simple and designed for our migration SQL (no $$ quoting).
    """

    buf: list[str] = []
    in_single = False
    in_double = False
    i = 0
    while i < len(sql):
        ch = sql[i]

        # Handle -- comments (only when not in quotes)
        if not in_single and not in_double and ch == "-" and i + 1 < len(sql) and sql[i + 1] == "-":
            while i < len(sql) and sql[i] not in ("\n", "\r"):
                i += 1
            continue

        if ch == "'" and not in_double:
            # Toggle single quote state unless escaped by doubling ''
            if in_single and i + 1 < len(sql) and sql[i + 1] == "'":
                buf.append("''")
                i += 2
                continue
            in_single = not in_single
            buf.append(ch)
            i += 1
            continue

        if ch == '"' and not in_single:
            in_double = not in_double
            buf.append(ch)
            i += 1
            continue

        if ch == ";" and not in_single and not in_double:
            stmt = "".join(buf).strip()
            buf = []
            if stmt:
                yield stmt
            i += 1
            continue

        buf.append(ch)
        i += 1

    tail = "".join(buf).strip()
    if tail:
        yield tail


def _get_test_database_url() -> str:
    """Get DATABASE_URL normalized to asyncpg.

    CI may use psycopg2 (sync) URL format, but these tests use SQLAlchemy async.
    """
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        pytest.skip("DATABASE_URL not set")

    # Convert to async URL if needed
    # Ensure we always use postgresql+asyncpg:// scheme
    # CI may use psycopg2 or other drivers — normalize to asyncpg
    if database_url.startswith("postgresql+asyncpg://"):
        pass  # Already correct
    elif database_url.startswith("postgresql+"):
        # Handle postgresql+psycopg2://, postgresql+psycopg://, etc.
        database_url = "postgresql+asyncpg://" + database_url.split("://", 1)[1]
    elif database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    elif database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql+asyncpg://", 1)
    else:
        pytest.skip(f"Unsupported DATABASE_URL format: {database_url}")

    # Verify asyncpg is importable (required for SQLAlchemy async engine)
    try:
        import asyncpg  # noqa: F401
    except ImportError:
        pytest.skip("asyncpg not installed — skipping async DB tests")

    return database_url


@pytest.fixture(autouse=True)
def _reset_prompt_registry_state() -> None:
    """Reset PromptRegistry global state between tests for isolation."""
    PromptRegistry._prompts = {}
    PromptRegistry._db_enabled = False
    PromptRegistry._db_loaded = False
    PromptRegistry._activation_lock = None


@pytest_asyncio.fixture
async def db_session():
    """Create an async database session for testing.

    Creates a fresh engine per test to avoid event-loop cross-contamination
    under pytest-asyncio strict mode (default loop scope is function).

    Also applies the AI tables migration to the CI-created database.
    """
    database_url = _get_test_database_url()
    engine = create_async_engine(database_url, echo=False)

    migrations_sql_path = Path(__file__).resolve().parents[1] / "db" / "migrations" / "001_ai_tables.sql"
    migration_sql = migrations_sql_path.read_text(encoding="utf-8")

    async with engine.begin() as conn:
        # Apply migration (idempotent)
        for stmt in _iter_sql_statements(migration_sql):
            await conn.execute(text(stmt))

        # Ensure a clean DB state per test
        await conn.execute(
            text("TRUNCATE system_prompts, ai_role_configs, ai_usage_log, ai_decisions RESTART IDENTITY CASCADE")
        )

    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with async_session() as session:
            yield session
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_role_config_crud(db_session):
    """Test full CRUD cycle for role configurations."""
    test_role = "test_screener"

    # Delete if exists (cleanup from previous runs)
    await db_session.execute(text("DELETE FROM ai_role_configs WHERE name = :name"), {"name": test_role})
    await db_session.commit()

    try:
        config = await create_role_config(
            db_session,
            name=test_role,
            provider="deepseek",
            model="deepseek-chat",
            temperature=0.0,
            max_tokens=2048,
            weight=0.8,
            enabled=True,
        )

        assert config.name == test_role
        assert config.provider == "deepseek"
        assert config.model == "deepseek-chat"
        assert abs(config.weight - 0.8) < 0.01  # Floating point comparison

        # Read it back
        retrieved = await get_role_config(db_session, test_role)
        assert retrieved is not None
        assert retrieved.name == test_role
        assert retrieved.provider == "deepseek"

        # Update it
        updated = await update_role_config(
            db_session,
            test_role,
            model="deepseek-reasoner",
            weight=1.5,
        )
        assert updated is not None
        assert updated.model == "deepseek-reasoner"
        assert abs(updated.weight - 1.5) < 0.01  # Floating point comparison

        # List all configs
        all_configs = await get_role_configs(db_session)
        assert len(all_configs) >= 5  # 4 defaults + our test one
    finally:
        try:
            await db_session.execute(text("DELETE FROM ai_role_configs WHERE name = :name"), {"name": test_role})
            await db_session.commit()
        except Exception:
            await db_session.rollback()


@pytest.mark.asyncio
async def test_prompt_versioning(db_session):
    """Test prompt creation, versioning, and activation."""
    test_role = "test_tactical"

    try:
        # Get next version (should start at 1 if no prompts exist for this role)
        next_ver = await get_next_version(db_session, test_role)
        assert next_ver >= 1

        # Create first prompt
        prompt1 = await create_prompt(
            db_session,
            prompt_id=f"{test_role}_v{next_ver}",
            role=test_role,
            version=next_ver,
            content="Test prompt version 1",
            description="First test prompt",
            is_active=True,
        )
        assert prompt1.version == next_ver
        assert prompt1.is_active is True

        # Create second version
        next_ver2 = await get_next_version(db_session, test_role)
        assert next_ver2 == next_ver + 1

        prompt2 = await create_prompt(
            db_session,
            prompt_id=f"{test_role}_v{next_ver2}",
            role=test_role,
            version=next_ver2,
            content="Test prompt version 2",
            description="Second test prompt",
            is_active=False,
        )
        assert prompt2.version == next_ver2

        # Get all prompts for the role
        prompts = await get_prompts(db_session, role=test_role)
        assert len(prompts) >= 2

        # Get active prompt (should be v1)
        active = await get_active_prompt(db_session, test_role)
        assert active is not None
        assert active.version == next_ver

        # Activate v2
        activated = await activate_prompt(db_session, prompt2.id)
        assert activated is not None
        assert activated.is_active is True

        # Verify v1 is now inactive
        active_now = await get_active_prompt(db_session, test_role)
        assert active_now is not None
        assert active_now.version == next_ver2
    finally:
        # Clean up
        try:
            await db_session.execute(text("DELETE FROM system_prompts WHERE role = :role"), {"role": test_role})
            await db_session.commit()
        except Exception:
            await db_session.rollback()


@pytest.mark.asyncio
async def test_usage_logging(db_session):
    """Test AI usage logging and summary."""
    try:
        # Log some usage
        usage1 = await log_usage(
            db_session,
            role="tactical",
            provider="deepseek",
            model="deepseek-reasoner",
            tokens_in=1000,
            tokens_out=500,
            cost_usd=0.005,
            latency_ms=2500.0,
            symbol="BTCUSD",
            success=True,
        )
        assert usage1.role == "tactical"
        assert abs(usage1.cost_usd - 0.005) < 0.001  # Floating point comparison

        await log_usage(
            db_session,
            role="tactical",
            provider="deepseek",
            model="deepseek-reasoner",
            tokens_in=800,
            tokens_out=400,
            cost_usd=0.004,
            latency_ms=2000.0,
            symbol="ETHUSD",
            success=True,
        )

        # Get summary for tactical role
        summary = await get_usage_summary(db_session, role="tactical")
        assert summary["total_requests"] >= 2
        assert summary["total_cost"] >= 0.009
        assert summary["success_rate"] > 0.0

        # Get summary for a specific symbol
        symbol_summary = await get_usage_summary(db_session, symbol="BTCUSD")
        assert symbol_summary["total_requests"] >= 1
    finally:
        # Rollback to avoid polluting database
        await db_session.rollback()


@pytest.mark.asyncio
async def test_decision_logging(db_session):
    """Test AI decision logging and retrieval."""
    test_symbol = "BTCUSD_TEST"
    try:
        # Log a decision
        decision = await log_decision(
            db_session,
            symbol=test_symbol,
            timeframe="1h",
            final_action="BUY",
            final_confidence=0.85,
            verdicts=[
                {"role": "tactical", "action": "BUY", "confidence": 0.9},
                {"role": "fundamental", "action": "NEUTRAL", "confidence": 0.6},
            ],
            reasoning="Strong technical setup with neutral fundamentals",
            total_cost_usd=0.034,
            total_latency_ms=5000.0,
        )
        assert decision.symbol == test_symbol
        assert decision.final_action == "BUY"
        assert len(decision.verdicts) == 2

        # Retrieve decisions for the symbol
        decisions = await get_decisions(db_session, symbol=test_symbol, limit=10)
        assert len(decisions) >= 1

        # Retrieve BUY decisions
        buy_decisions = await get_decisions(db_session, action="BUY", limit=10)
        assert len(buy_decisions) >= 1
    finally:
        # Clean up test decisions to avoid DB pollution
        try:
            await db_session.execute(
                text("DELETE FROM ai_decisions WHERE symbol = :symbol"),
                {"symbol": test_symbol},
            )
            await db_session.commit()
        except Exception:
            await db_session.rollback()


@pytest.mark.asyncio
async def test_prompt_registry_db_backend(db_session):
    """Test PromptRegistry with DB backend."""
    # Clear registry first
    PromptRegistry.clear()

    # Load from DB
    await PromptRegistry.load_from_db(db_session)
    assert PromptRegistry.is_db_enabled()

    # Should have loaded the 4 default prompts from the seeded DB
    tactical = PromptRegistry.get_active(RoleName.TACTICAL)
    assert tactical is not None
    assert tactical.role == RoleName.TACTICAL
    assert tactical.is_active is True

    screener = PromptRegistry.get_active(RoleName.SCREENER)
    assert screener is not None
    assert screener.role == RoleName.SCREENER

    # Create a new prompt version via registry
    new_prompt = await PromptRegistry.create_prompt(
        db_session,
        role=RoleName.TACTICAL,
        content="Test tactical prompt v2",
        description="Test version",
        is_active=False,
    )
    assert new_prompt.role == RoleName.TACTICAL
    assert new_prompt.version >= 2

    # Activate the new prompt
    activated = await PromptRegistry.activate_prompt(db_session, new_prompt.id)
    assert activated is not None
    assert activated.is_active is True

    # Verify it's now the active prompt in the registry
    active = PromptRegistry.get_active(RoleName.TACTICAL)
    assert active is not None
    assert active.id == new_prompt.id

    # List all versions for the role
    versions = PromptRegistry.list_versions(RoleName.TACTICAL)
    assert len(versions) >= 2  # At least v1 (default) and our new version

    # Clean up
    PromptRegistry.clear()


@pytest.mark.asyncio
async def test_seed_idempotency(db_session):
    """Test that seeding is idempotent (can be run multiple times)."""
    # Get current count of role configs
    configs_before = await get_role_configs(db_session)
    prompts_before = await get_prompts(db_session)

    # Import seed functions (project root is already on sys.path via conftest/pytest)
    from scripts.seed_ai_defaults import seed_role_configs, seed_system_prompts

    # Seed again
    await seed_system_prompts(db_session)
    await seed_role_configs(db_session)

    # Get counts after
    configs_after = await get_role_configs(db_session)
    prompts_after = await get_prompts(db_session)

    # Should have the same counts (no duplicates)
    assert len(configs_after) == len(configs_before)
    assert len(prompts_after) == len(prompts_before)
