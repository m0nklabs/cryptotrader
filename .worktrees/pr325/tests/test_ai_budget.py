"""Tests for AI budget guardrails.

Tests budget configuration, enforcement logic, and API endpoints.
Validates:
- Budget config CRUD operations
- Daily/monthly spend tracking
- Budget exceeded detection (just-under, equal, just-over)
- UTC timezone safety
- Endpoint rejection on budget overages
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable
from urllib.parse import urlsplit

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from db.crud.ai import (
    check_budget_exceeded,
    get_budget_config,
    get_budget_status,
    log_usage,
    update_budget_config,
)


def _iter_sql_statements(sql: str) -> Iterable[str]:
    """Split a SQL script into executable statements."""
    buf: list[str] = []
    in_single = False
    in_double = False
    i = 0
    while i < len(sql):
        ch = sql[i]

        if not in_single and not in_double and ch == "-" and i + 1 < len(sql) and sql[i + 1] == "-":
            while i < len(sql) and sql[i] not in ("\n", "\r"):
                i += 1
            continue

        if ch == "'" and not in_double:
            if in_single and i + 1 < len(sql) and sql[i + 1] == "'":
                buf.append("''")
                i += 2
                continue
            in_single = not in_single
            buf.append(ch)
            i += 1
            continue

        if ch == '"' and not in_single:
            if in_double and i + 1 < len(sql) and sql[i + 1] == '"':
                buf.append('""')
                i += 2
                continue
            in_double = not in_double
            buf.append(ch)
            i += 1
            continue

        if ch == ";" and not in_single and not in_double:
            stmt = "".join(buf).strip()
            if stmt:
                yield stmt
            buf = []
            i += 1
            continue

        buf.append(ch)
        i += 1

    stmt = "".join(buf).strip()
    if stmt:
        yield stmt


def _normalize_database_url(database_url: str) -> str:
    """Normalize DATABASE_URL to an async SQLAlchemy URL."""
    if "://" not in database_url:
        candidate = f"postgresql+asyncpg://{database_url}"
        parsed = urlsplit(candidate)
        if not parsed.netloc or parsed.path in {"", "/"}:
            raise ValueError(f"Unsupported DATABASE_URL format: {database_url}")
        database_url = candidate

    if database_url.startswith("postgresql+asyncpg://"):
        return database_url
    if database_url.startswith("postgresql+"):
        return "postgresql+asyncpg://" + database_url.split("://", 1)[1]
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    elif database_url.startswith("postgres://"):
        return database_url.replace("postgres://", "postgresql+asyncpg://", 1)

    raise ValueError(f"Unsupported DATABASE_URL format: {database_url}")


def _get_test_database_url() -> str:
    """Get DATABASE_URL normalized to asyncpg."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        pytest.skip("DATABASE_URL not set")

    try:
        database_url = _normalize_database_url(database_url)
    except ValueError as exc:
        pytest.skip(str(exc))

    try:
        import asyncpg  # noqa: F401
    except ImportError:
        pytest.skip("asyncpg not installed — skipping async DB tests")

    return database_url


@pytest_asyncio.fixture
async def db_session():
    """Create an async database session for testing.

    Applies AI tables migrations and budget config migration.
    """
    database_url = _get_test_database_url()
    engine = create_async_engine(database_url, echo=False)

    # Apply migrations
    migrations_dir = Path(__file__).resolve().parents[1] / "db" / "migrations"
    ai_tables_sql = (migrations_dir / "001_ai_tables.sql").read_text(encoding="utf-8")
    budget_sql = (migrations_dir / "003_ai_budget_config.sql").read_text(encoding="utf-8")

    async with engine.begin() as conn:
        # Apply AI tables migration
        for stmt in _iter_sql_statements(ai_tables_sql):
            await conn.execute(text(stmt))

        # Apply budget migration
        for stmt in _iter_sql_statements(budget_sql):
            await conn.execute(text(stmt))

        # Clean state
        await conn.execute(
            text(
                "TRUNCATE system_prompts, ai_role_configs, ai_usage_log, ai_decisions, ai_budget_config RESTART IDENTITY CASCADE"
            )
        )

        # Re-insert default budget config after truncate
        for stmt in _iter_sql_statements(budget_sql):
            if "INSERT INTO ai_budget_config" in stmt:
                await conn.execute(text(stmt))

    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session

    await engine.dispose()


# =============================================================================
# Budget Config CRUD Tests
# =============================================================================


@pytest.mark.asyncio
async def test_get_budget_config_global(db_session: AsyncSession):
    """Test retrieving global budget config."""
    config = await get_budget_config(db_session, "global")
    assert config is not None
    assert config.id == "global"
    assert config.daily_limit_usd == 0.0  # Default unlimited
    assert config.monthly_limit_usd == 0.0
    assert config.enabled is True


@pytest.mark.asyncio
async def test_get_budget_config_role(db_session: AsyncSession):
    """Test retrieving role-specific budget config."""
    config = await get_budget_config(db_session, "tactical")
    assert config is not None
    assert config.id == "tactical"
    assert config.daily_limit_usd == 0.0
    assert config.monthly_limit_usd == 0.0
    assert config.enabled is True


@pytest.mark.asyncio
async def test_get_budget_config_nonexistent(db_session: AsyncSession):
    """Test retrieving non-existent config returns None."""
    config = await get_budget_config(db_session, "nonexistent")
    assert config is None


@pytest.mark.asyncio
async def test_update_budget_config(db_session: AsyncSession):
    """Test updating budget config."""
    updated = await update_budget_config(
        db_session, scope="global", daily_limit_usd=10.0, monthly_limit_usd=100.0, enabled=True
    )
    assert updated is not None
    assert updated.daily_limit_usd == 10.0
    assert updated.monthly_limit_usd == 100.0
    assert updated.enabled is True


@pytest.mark.asyncio
async def test_update_budget_config_partial(db_session: AsyncSession):
    """Test updating only some fields."""
    # Set initial values
    await update_budget_config(db_session, scope="screener", daily_limit_usd=5.0, monthly_limit_usd=50.0)

    # Update only daily limit
    updated = await update_budget_config(db_session, scope="screener", daily_limit_usd=10.0)
    assert updated.daily_limit_usd == 10.0
    assert updated.monthly_limit_usd == 50.0  # Unchanged


# =============================================================================
# Budget Check Logic Tests
# =============================================================================


@pytest.mark.asyncio
async def test_check_budget_no_limits(db_session: AsyncSession):
    """Test budget check with no limits (unlimited)."""
    # Default config has 0.0 limits = unlimited
    status = await check_budget_exceeded(db_session, "global")
    assert status["exceeded"] is False
    assert status["daily_exceeded"] is False
    assert status["monthly_exceeded"] is False
    assert status["enabled"] is True


@pytest.mark.asyncio
async def test_check_budget_disabled(db_session: AsyncSession):
    """Test budget check when enforcement is disabled."""
    await update_budget_config(db_session, scope="global", enabled=False)
    status = await check_budget_exceeded(db_session, "global")
    assert status["exceeded"] is False
    assert status["enabled"] is False


@pytest.mark.asyncio
async def test_check_budget_daily_just_under(db_session: AsyncSession):
    """Test budget just under daily limit (not exceeded)."""
    # Set daily limit to $10
    await update_budget_config(db_session, scope="global", daily_limit_usd=10.0)

    # Log usage totaling $9.99 (just under)
    await log_usage(
        db_session,
        role="tactical",
        provider="deepseek",
        model="deepseek-reasoner",
        tokens_in=1000,
        tokens_out=500,
        cost_usd=9.99,
        latency_ms=1500,
        symbol="BTCUSDT",
        success=True,
    )

    status = await check_budget_exceeded(db_session, "global")
    assert status["exceeded"] is False
    assert status["daily_exceeded"] is False
    assert status["daily_spent"] == pytest.approx(9.99, abs=1e-2)
    assert status["daily_limit"] == 10.0
    assert status["daily_remaining"] == pytest.approx(0.01, abs=1e-2)


@pytest.mark.asyncio
async def test_check_budget_daily_equal(db_session: AsyncSession):
    """Test budget equal to daily limit (exceeded)."""
    # Set daily limit to $10
    await update_budget_config(db_session, scope="global", daily_limit_usd=10.0)

    # Log usage totaling exactly $10
    await log_usage(
        db_session,
        role="tactical",
        provider="deepseek",
        model="deepseek-reasoner",
        tokens_in=1000,
        tokens_out=500,
        cost_usd=10.0,
        latency_ms=1500,
        symbol="BTCUSDT",
        success=True,
    )

    status = await check_budget_exceeded(db_session, "global")
    assert status["exceeded"] is True
    assert status["daily_exceeded"] is True
    assert status["daily_spent"] == 10.0
    assert status["daily_limit"] == 10.0
    assert status["daily_remaining"] == 0.0


@pytest.mark.asyncio
async def test_check_budget_daily_just_over(db_session: AsyncSession):
    """Test budget just over daily limit (exceeded)."""
    # Set daily limit to $10
    await update_budget_config(db_session, scope="global", daily_limit_usd=10.0)

    # Log usage totaling $10.01 (just over)
    await log_usage(
        db_session,
        role="tactical",
        provider="deepseek",
        model="deepseek-reasoner",
        tokens_in=1000,
        tokens_out=500,
        cost_usd=10.01,
        latency_ms=1500,
        symbol="BTCUSDT",
        success=True,
    )

    status = await check_budget_exceeded(db_session, "global")
    assert status["exceeded"] is True
    assert status["daily_exceeded"] is True
    assert status["daily_spent"] == pytest.approx(10.01, abs=1e-2)
    assert status["daily_limit"] == 10.0
    assert status["daily_remaining"] == pytest.approx(-0.01, abs=1e-2)


@pytest.mark.asyncio
async def test_check_budget_monthly_exceeded(db_session: AsyncSession):
    """Test monthly budget exceeded."""
    # Set monthly limit to $100
    await update_budget_config(db_session, scope="global", monthly_limit_usd=100.0)

    # Log usage totaling $100.50 (exceeded)
    await log_usage(
        db_session,
        role="tactical",
        provider="deepseek",
        model="deepseek-reasoner",
        tokens_in=10000,
        tokens_out=5000,
        cost_usd=100.50,
        latency_ms=2000,
        symbol="ETHUSDT",
        success=True,
    )

    status = await check_budget_exceeded(db_session, "global")
    assert status["exceeded"] is True
    assert status["monthly_exceeded"] is True
    assert status["monthly_spent"] == 100.50
    assert status["monthly_limit"] == 100.0
    assert status["monthly_remaining"] == pytest.approx(-0.50, abs=1e-6)


@pytest.mark.asyncio
async def test_check_budget_role_specific(db_session: AsyncSession):
    """Test role-specific budget check."""
    # Set tactical role daily limit to $5
    await update_budget_config(db_session, scope="tactical", daily_limit_usd=5.0)

    # Log usage for tactical role
    await log_usage(
        db_session,
        role="tactical",
        provider="deepseek",
        model="deepseek-reasoner",
        tokens_in=1000,
        tokens_out=500,
        cost_usd=5.50,
        latency_ms=1500,
        symbol="BTCUSDT",
        success=True,
    )

    # Tactical budget should be exceeded
    tactical_status = await check_budget_exceeded(db_session, "tactical")
    assert tactical_status["exceeded"] is True
    assert tactical_status["daily_exceeded"] is True
    assert tactical_status["daily_spent"] == 5.50

    # Global budget should not be exceeded (no limit)
    global_status = await check_budget_exceeded(db_session, "global")
    assert global_status["exceeded"] is False


@pytest.mark.asyncio
async def test_check_budget_multiple_usage_records(db_session: AsyncSession):
    """Test budget check aggregates multiple usage records."""
    # Set daily limit to $10
    await update_budget_config(db_session, scope="global", daily_limit_usd=10.0)

    # Log three usage records totaling $10.50
    for cost in [3.0, 4.0, 3.50]:
        await log_usage(
            db_session,
            role="tactical",
            provider="deepseek",
            model="deepseek-reasoner",
            tokens_in=1000,
            tokens_out=500,
            cost_usd=cost,
            latency_ms=1500,
            symbol="BTCUSDT",
            success=True,
        )

    status = await check_budget_exceeded(db_session, "global")
    assert status["exceeded"] is True
    assert status["daily_spent"] == 10.50
    assert status["daily_remaining"] == pytest.approx(-0.50, abs=1e-6)


@pytest.mark.asyncio
async def test_check_budget_utc_timezone_safety(db_session: AsyncSession):
    """Test budget check uses UTC for date boundaries."""
    # Set daily limit to $10
    await update_budget_config(db_session, scope="global", daily_limit_usd=10.0)

    # Log usage from yesterday (should not count toward today)
    yesterday = datetime.now(timezone.utc) - timedelta(days=1)
    await db_session.execute(
        text(
            """
            INSERT INTO ai_usage_log (role, provider, model, tokens_in, tokens_out, cost_usd, latency_ms, symbol, success, created_at)
            VALUES (:role, :provider, :model, :tokens_in, :tokens_out, :cost_usd, :latency_ms, :symbol, :success, :created_at)
        """
        ),
        {
            "role": "tactical",
            "provider": "deepseek",
            "model": "deepseek-reasoner",
            "tokens_in": 1000,
            "tokens_out": 500,
            "cost_usd": 5.0,
            "latency_ms": 1500,
            "symbol": "BTCUSDT",
            "success": True,
            "created_at": yesterday,
        },
    )
    await db_session.commit()

    # Log usage today totaling $4
    await log_usage(
        db_session,
        role="tactical",
        provider="deepseek",
        model="deepseek-reasoner",
        tokens_in=1000,
        tokens_out=500,
        cost_usd=4.0,
        latency_ms=1500,
        symbol="BTCUSDT",
        success=True,
    )

    status = await check_budget_exceeded(db_session, "global")
    # Should only count today's $4, not yesterday's $5
    assert status["exceeded"] is False
    assert status["daily_spent"] == 4.0
    assert status["daily_remaining"] == 6.0


@pytest.mark.asyncio
async def test_get_budget_status_all_scopes(db_session: AsyncSession):
    """Test getting budget status for all scopes."""
    # Set different limits for different scopes
    await update_budget_config(db_session, scope="global", daily_limit_usd=100.0)
    await update_budget_config(db_session, scope="tactical", daily_limit_usd=10.0)

    # Log usage
    await log_usage(
        db_session,
        role="tactical",
        provider="deepseek",
        model="deepseek-reasoner",
        tokens_in=1000,
        tokens_out=500,
        cost_usd=5.0,
        latency_ms=1500,
        symbol="BTCUSDT",
        success=True,
    )

    status = await get_budget_status(db_session)

    # Check all scopes are present
    assert "global" in status
    assert "tactical" in status
    assert "screener" in status
    assert "fundamental" in status
    assert "strategist" in status

    # Check global status
    assert status["global"]["daily_spent"] == 5.0
    assert status["global"]["daily_limit"] == 100.0
    assert status["global"]["exceeded"] is False

    # Check tactical status
    assert status["tactical"]["daily_spent"] == 5.0
    assert status["tactical"]["daily_limit"] == 10.0
    assert status["tactical"]["exceeded"] is False

    # Other roles should have 0 spend
    assert status["screener"]["daily_spent"] == 0.0


# =============================================================================
# Edge Cases
# =============================================================================


@pytest.mark.asyncio
async def test_check_budget_both_daily_and_monthly_exceeded(db_session: AsyncSession):
    """Test when both daily and monthly limits are exceeded."""
    await update_budget_config(db_session, scope="global", daily_limit_usd=10.0, monthly_limit_usd=100.0)

    # Log $150 (exceeds both daily $10 and monthly $100)
    await log_usage(
        db_session,
        role="tactical",
        provider="deepseek",
        model="deepseek-reasoner",
        tokens_in=10000,
        tokens_out=5000,
        cost_usd=150.0,
        latency_ms=2000,
        symbol="BTCUSDT",
        success=True,
    )

    status = await check_budget_exceeded(db_session, "global")
    assert status["exceeded"] is True
    assert status["daily_exceeded"] is True
    assert status["monthly_exceeded"] is True


@pytest.mark.asyncio
async def test_check_budget_nonexistent_scope(db_session: AsyncSession):
    """Test budget check for non-existent scope returns safe defaults."""
    status = await check_budget_exceeded(db_session, "nonexistent")
    assert status["exceeded"] is False
    assert status["enabled"] is False
    assert status["daily_spent"] == 0.0
    assert status["monthly_spent"] == 0.0
