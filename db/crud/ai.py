"""Async CRUD operations for Multi-Brain AI tables.

Uses asyncpg/SQLAlchemy async sessions for database operations.
All functions are designed to work with FastAPI dependency injection.
"""

from __future__ import annotations

from datetime import datetime
from typing import Sequence

from sqlalchemy import select, update, and_, Integer, func
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.ai import AIDecision, AIRoleConfig, AIUsageLog, SystemPrompt


# ---------------------------------------------------------------------------
# Role Config Operations
# ---------------------------------------------------------------------------


async def get_role_configs(db: AsyncSession) -> Sequence[AIRoleConfig]:
    """Get all role configurations."""
    result = await db.execute(select(AIRoleConfig))
    return result.scalars().all()


async def get_role_config(db: AsyncSession, role_name: str) -> AIRoleConfig | None:
    """Get a specific role configuration."""
    result = await db.execute(select(AIRoleConfig).where(AIRoleConfig.name == role_name))
    return result.scalars().first()


async def update_role_config(
    db: AsyncSession,
    role_name: str,
    provider: str | None = None,
    model: str | None = None,
    system_prompt_id: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    weight: float | None = None,
    enabled: bool | None = None,
    fallback_provider: str | None = None,
    fallback_model: str | None = None,
) -> AIRoleConfig | None:
    """Update a role configuration.

    Only updates fields that are provided (not None).
    Returns the updated config or None if not found.
    """
    values = {"updated_at": func.now()}
    if provider is not None:
        values["provider"] = provider
    if model is not None:
        values["model"] = model
    if system_prompt_id is not None:
        values["system_prompt_id"] = system_prompt_id
    if temperature is not None:
        values["temperature"] = temperature
    if max_tokens is not None:
        values["max_tokens"] = max_tokens
    if weight is not None:
        values["weight"] = weight
    if enabled is not None:
        values["enabled"] = enabled
    if fallback_provider is not None:
        values["fallback_provider"] = fallback_provider
    if fallback_model is not None:
        values["fallback_model"] = fallback_model

    await db.execute(update(AIRoleConfig).where(AIRoleConfig.name == role_name).values(**values))
    await db.commit()

    return await get_role_config(db, role_name)


async def create_role_config(
    db: AsyncSession,
    name: str,
    provider: str,
    model: str,
    system_prompt_id: str | None = None,
    temperature: float = 0.0,
    max_tokens: int = 4096,
    weight: float = 1.0,
    enabled: bool = True,
    fallback_provider: str | None = None,
    fallback_model: str | None = None,
) -> AIRoleConfig:
    """Create a new role configuration."""
    config = AIRoleConfig(
        name=name,
        provider=provider,
        model=model,
        system_prompt_id=system_prompt_id,
        temperature=temperature,
        max_tokens=max_tokens,
        weight=weight,
        enabled=enabled,
        fallback_provider=fallback_provider,
        fallback_model=fallback_model,
    )
    db.add(config)
    await db.commit()
    await db.refresh(config)
    return config


# ---------------------------------------------------------------------------
# System Prompt Operations
# ---------------------------------------------------------------------------


async def get_prompts(db: AsyncSession, role: str | None = None) -> Sequence[SystemPrompt]:
    """Get all system prompts, optionally filtered by role."""
    query = select(SystemPrompt)
    if role:
        query = query.where(SystemPrompt.role == role)
    result = await db.execute(query.order_by(SystemPrompt.version.desc()))
    return result.scalars().all()


async def get_active_prompt(db: AsyncSession, role: str) -> SystemPrompt | None:
    """Get the active prompt for a role (highest version with is_active=True)."""
    result = await db.execute(
        select(SystemPrompt)
        .where(and_(SystemPrompt.role == role, SystemPrompt.is_active))
        .order_by(SystemPrompt.version.desc())
        .limit(1)
    )
    return result.scalars().first()


async def create_prompt(
    db: AsyncSession,
    prompt_id: str,
    role: str,
    version: int,
    content: str,
    description: str = "",
    is_active: bool = True,
) -> SystemPrompt:
    """Create a new system prompt version."""
    prompt = SystemPrompt(
        id=prompt_id,
        role=role,
        version=version,
        content=content,
        description=description,
        is_active=is_active,
    )
    db.add(prompt)
    await db.commit()
    await db.refresh(prompt)
    return prompt


async def activate_prompt(db: AsyncSession, prompt_id: str) -> SystemPrompt | None:
    """Activate a prompt and deactivate all others for the same role.

    Returns the activated prompt or None if not found.
    """
    # First, get the prompt to find its role
    result = await db.execute(select(SystemPrompt).where(SystemPrompt.id == prompt_id))
    prompt = result.scalars().first()
    if not prompt:
        return None

    # Deactivate all prompts for this role
    await db.execute(update(SystemPrompt).where(SystemPrompt.role == prompt.role).values(is_active=False))

    # Activate the target prompt
    await db.execute(update(SystemPrompt).where(SystemPrompt.id == prompt_id).values(is_active=True))

    await db.commit()
    await db.refresh(prompt)
    return prompt


async def get_next_version(db: AsyncSession, role: str) -> int:
    """Get the next version number for a role's prompts."""
    result = await db.execute(
        select(SystemPrompt.version).where(SystemPrompt.role == role).order_by(SystemPrompt.version.desc()).limit(1)
    )
    max_version = result.scalars().first()
    return (max_version or 0) + 1


# ---------------------------------------------------------------------------
# Usage Log Operations
# ---------------------------------------------------------------------------


async def log_usage(
    db: AsyncSession,
    role: str,
    provider: str,
    model: str,
    tokens_in: int,
    tokens_out: int,
    cost_usd: float,
    latency_ms: float,
    symbol: str = "",
    success: bool = True,
    error: str | None = None,
) -> AIUsageLog:
    """Log AI usage (tokens, cost, latency)."""
    log = AIUsageLog(
        role=role,
        provider=provider,
        model=model,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        cost_usd=cost_usd,
        latency_ms=latency_ms,
        symbol=symbol,
        success=success,
        error=error,
    )
    db.add(log)
    await db.commit()
    await db.refresh(log)
    return log


async def get_usage_summary(
    db: AsyncSession,
    role: str | None = None,
    provider: str | None = None,
    symbol: str | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> dict:
    """Get usage summary with filters.

    Returns aggregate statistics: total requests, total cost, avg latency, success rate.
    """
    query = select(
        func.count(AIUsageLog.id).label("total_requests"),
        func.sum(AIUsageLog.tokens_in).label("total_tokens_in"),
        func.sum(AIUsageLog.tokens_out).label("total_tokens_out"),
        func.sum(AIUsageLog.cost_usd).label("total_cost"),
        func.avg(AIUsageLog.latency_ms).label("avg_latency"),
        func.sum(AIUsageLog.success).label("successful_requests"),
    )

    # Apply filters
    conditions = []
    if role:
        conditions.append(AIUsageLog.role == role)
    if provider:
        conditions.append(AIUsageLog.provider == provider)
    if symbol:
        conditions.append(AIUsageLog.symbol == symbol)
    if start_date:
        conditions.append(AIUsageLog.created_at >= start_date)
    if end_date:
        conditions.append(AIUsageLog.created_at <= end_date)

    if conditions:
        query = query.where(and_(*conditions))

    result = await db.execute(query)
    row = result.first()

    if not row or row.total_requests == 0:
        return {
            "total_requests": 0,
            "total_tokens_in": 0,
            "total_tokens_out": 0,
            "total_cost": 0.0,
            "avg_latency": 0.0,
            "success_rate": 0.0,
        }

    return {
        "total_requests": row.total_requests,
        "total_tokens_in": row.total_tokens_in or 0,
        "total_tokens_out": row.total_tokens_out or 0,
        "total_cost": float(row.total_cost or 0.0),
        "avg_latency": float(row.avg_latency or 0.0),
        "success_rate": (row.successful_requests / row.total_requests) if row.total_requests > 0 else 0.0,
    }


# ---------------------------------------------------------------------------
# Decision Log Operations
# ---------------------------------------------------------------------------


async def log_decision(
    db: AsyncSession,
    symbol: str,
    timeframe: str,
    final_action: str,
    final_confidence: float,
    verdicts: list[dict],
    reasoning: str = "",
    vetoed_by: str | None = None,
    total_cost_usd: float = 0.0,
    total_latency_ms: float = 0.0,
) -> AIDecision:
    """Log an AI consensus decision."""
    decision = AIDecision(
        symbol=symbol,
        timeframe=timeframe,
        final_action=final_action,
        final_confidence=final_confidence,
        verdicts=verdicts,
        reasoning=reasoning,
        vetoed_by=vetoed_by,
        total_cost_usd=total_cost_usd,
        total_latency_ms=total_latency_ms,
    )
    db.add(decision)
    await db.commit()
    await db.refresh(decision)
    return decision


async def get_decisions(
    db: AsyncSession,
    symbol: str | None = None,
    action: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> Sequence[AIDecision]:
    """Get AI decisions with optional filters.

    The number of returned records is capped to avoid excessive memory usage.
    """
    # Enforce a sensible upper bound to prevent memory exhaustion
    max_limit = 1000
    if limit < 1:
        limit = 100
    elif limit > max_limit:
        limit = max_limit

    query = select(AIDecision)

    if symbol:
        query = query.where(AIDecision.symbol == symbol)
    if action:
        query = query.where(AIDecision.final_action == action)

    query = query.order_by(AIDecision.created_at.desc()).limit(limit).offset(offset)

    result = await db.execute(query)
    return result.scalars().all()
