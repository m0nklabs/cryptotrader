"""Multi-Brain AI API routes.

Provides endpoints for AI configuration, evaluation, and usage tracking.

Phase 2.1 (P2.1) implementation of issue #205.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Query, Path as PathParam
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from core.ai.router import LLMRouter
from core.ai.types import ProviderName, RoleName
from db.crud import ai as ai_crud

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ai", tags=["ai"])

# Global database engine and session factory
_engine = None
_async_session_factory = None


def _pg_ssl_connect_args_from_env() -> dict[str, str]:
    """Build libpq/psycopg SSL kwargs from environment.

    Uses standard libpq env var names so deploy systems (e.g. GH Secrets) can inject them.
    Returns an empty dict when unset.
    """
    mapping = {
        "sslmode": os.environ.get("PGSSLMODE"),
        "sslrootcert": os.environ.get("PGSSLROOTCERT"),
        "sslcert": os.environ.get("PGSSLCERT"),
        "sslkey": os.environ.get("PGSSLKEY"),
    }
    return {k: v for k, v in mapping.items() if v}


def _normalize_database_url(database_url: str) -> str:
    """Normalize DATABASE_URL to an async SQLAlchemy URL.

    Supports:
    - Bare: host:port/dbname or user:pass@host:port/dbname
    - postgresql://
    - postgres://
    - postgresql+<driver>:// (e.g. psycopg2)
    - postgresql+asyncpg://
    """
    if "://" not in database_url:
        candidate = f"postgresql+asyncpg://{database_url}"
        parsed = urlsplit(candidate)
        if not parsed.netloc or parsed.path in {"", "/"}:
            raise ValueError("Unsupported DATABASE_URL format. Expected host:port/dbname or user:pass@host:port/dbname")
        database_url = candidate

    if database_url.startswith("postgresql+asyncpg://"):
        return database_url
    if database_url.startswith("postgresql+"):
        # Handle postgresql+psycopg2://, postgresql+psycopg://, etc.
        return "postgresql+asyncpg://" + database_url.split("://", 1)[1]
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if database_url.startswith("postgres://"):
        return database_url.replace("postgres://", "postgresql+asyncpg://", 1)

    return database_url


def _get_session_factory():
    """Get or create async session factory."""
    global _engine, _async_session_factory
    if _async_session_factory is None:
        database_url = os.environ.get("DATABASE_URL")
        if not database_url:
            raise RuntimeError("DATABASE_URL environment variable is required")

        # Normalize to postgresql+asyncpg://
        database_url = _normalize_database_url(database_url)

        # Create engine with connection hardening (timeout + SSL support)
        _engine = create_async_engine(
            database_url,
            echo=False,
            pool_pre_ping=True,
            connect_args={"timeout": 3, **_pg_ssl_connect_args_from_env()},
        )
        _async_session_factory = sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
    return _async_session_factory


async def get_db() -> AsyncSession:
    """Dependency for getting async database session."""
    factory = _get_session_factory()
    async with factory() as session:
        yield session


# Router factory (request-scoped instances)


def _get_router() -> LLMRouter:
    """Create a new LLM router instance.

    Using a fresh instance per call avoids sharing mutable internal state
    (such as usage logs) across concurrent requests.
    """
    return LLMRouter()


# =============================================================================
# Request/Response Models
# =============================================================================


class ProviderHealthResponse(BaseModel):
    """Provider health status response."""

    name: str
    available: bool
    message: str
    models: list[str] = Field(default_factory=list)


class RoleConfigResponse(BaseModel):
    """Role configuration response."""

    name: str
    provider: str
    model: str
    system_prompt_id: str | None
    temperature: float
    max_tokens: int
    weight: float
    enabled: bool
    fallback_provider: str | None
    fallback_model: str | None
    updated_at: datetime


class RoleConfigUpdate(BaseModel):
    """Role configuration update request."""

    provider: str | None = None
    model: str | None = None
    system_prompt_id: str | None = None
    temperature: float | None = Field(None, ge=0.0, le=2.0)
    max_tokens: int | None = Field(None, gt=0, le=32000)
    weight: float | None = Field(None, ge=0.0, le=10.0)
    enabled: bool | None = None
    fallback_provider: str | None = None
    fallback_model: str | None = None


class SystemPromptResponse(BaseModel):
    """System prompt response."""

    id: str
    role: str
    version: int
    content: str
    description: str
    is_active: bool
    created_at: datetime


class SystemPromptCreate(BaseModel):
    """Create new system prompt request.

    Prompts are created inactive by default. To activate a prompt,
    use the `/prompts/{id}/activate` endpoint.
    """

    role: str
    content: str
    description: str = ""
    is_active: bool = False


class EvaluationRequest(BaseModel):
    """Multi-Brain evaluation request."""

    symbol: str
    timeframe: str = "1h"
    candles: list[dict] | None = None
    indicators: dict | None = None
    portfolio: dict | None = None
    risk_limits: dict | None = None
    roles: list[str] | None = None


class EvaluationResponse(BaseModel):
    """Multi-Brain evaluation response."""

    symbol: str
    timeframe: str
    final_action: str
    final_confidence: float
    reasoning: str
    verdicts: list[dict]
    vetoed_by: str | None = None
    total_cost_usd: float = 0.0
    total_latency_ms: float = 0.0
    created_at: datetime


class UsageSummaryResponse(BaseModel):
    """Usage summary response."""

    total_requests: int
    total_cost_usd: float
    total_tokens_in: int
    total_tokens_out: int
    by_role: dict[str, dict[str, Any]]
    by_provider: dict[str, dict[str, Any]]


# =============================================================================
# P2.1.1 - CRUD Endpoints for AI Configuration
# =============================================================================


@router.get("/providers", response_model=list[ProviderHealthResponse])
async def list_providers():
    """List all providers and their health status.

    Returns status for each configured LLM provider including availability
    and supported models.
    """
    providers = []

    # Check each provider
    for provider in ProviderName:
        # Basic availability check - check if API key is configured
        api_key_env = f"{provider.value.upper()}_API_KEY"
        if provider == ProviderName.OLLAMA:
            api_key_env = "OLLAMA_BASE_URL"

        api_key = os.environ.get(api_key_env)
        available = api_key is not None and len(api_key) > 0

        # Get default models for this provider
        models = []
        if provider == ProviderName.DEEPSEEK:
            models = ["deepseek-chat", "deepseek-reasoner"]
        elif provider == ProviderName.OPENAI:
            models = ["o3-mini", "gpt-4", "gpt-4-turbo"]
        elif provider == ProviderName.XAI:
            models = ["grok-beta", "grok-vision-beta"]
        elif provider == ProviderName.OLLAMA:
            models = ["llama3.2:3b", "llama3.1:8b"]
        elif provider == ProviderName.GOOGLE:
            models = ["gemini-pro", "gemini-1.5-pro"]

        providers.append(
            ProviderHealthResponse(
                name=provider.value,
                available=available,
                message="Configured" if available else f"Missing {api_key_env}",
                models=models,
            )
        )

    return providers


@router.get("/roles", response_model=list[RoleConfigResponse])
async def list_roles():
    """List all role configurations.

    Returns configuration for each agent role including provider assignment,
    model, prompts, and consensus weights.
    """
    factory = _get_session_factory()
    async with factory() as db:
        configs = await ai_crud.get_role_configs(db)
        return [
            RoleConfigResponse(
                name=c.name,
                provider=c.provider,
                model=c.model,
                system_prompt_id=c.system_prompt_id,
                temperature=c.temperature,
                max_tokens=c.max_tokens,
                weight=c.weight,
                enabled=c.enabled,
                fallback_provider=c.fallback_provider,
                fallback_model=c.fallback_model,
                updated_at=c.updated_at,
            )
            for c in configs
        ]


@router.get("/roles/{role}", response_model=RoleConfigResponse)
async def get_role(role: str = PathParam(..., description="Role name")):
    """Get configuration for a specific role.

    Args:
        role: Role name (screener, tactical, fundamental, strategist)
    """
    factory = _get_session_factory()
    async with factory() as db:
        config = await ai_crud.get_role_config(db, role)
        if not config:
            raise HTTPException(status_code=404, detail=f"Role '{role}' not found")

        return RoleConfigResponse(
            name=config.name,
            provider=config.provider,
            model=config.model,
            system_prompt_id=config.system_prompt_id,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
            weight=config.weight,
            enabled=config.enabled,
            fallback_provider=config.fallback_provider,
            fallback_model=config.fallback_model,
            updated_at=config.updated_at,
        )


@router.put("/roles/{role}", response_model=RoleConfigResponse)
async def update_role(
    role: str = PathParam(..., description="Role name"),
    update: RoleConfigUpdate = ...,
):
    """Update role configuration.

    Updates provider assignment, model, temperature, weights, etc.
    Only provided fields will be updated.

    Args:
        role: Role name (screener, tactical, fundamental, strategist)
        update: Fields to update
    """
    factory = _get_session_factory()
    async with factory() as db:
        config = await ai_crud.update_role_config(
            db,
            role_name=role,
            provider=update.provider,
            model=update.model,
            system_prompt_id=update.system_prompt_id,
            temperature=update.temperature,
            max_tokens=update.max_tokens,
            weight=update.weight,
            enabled=update.enabled,
            fallback_provider=update.fallback_provider,
            fallback_model=update.fallback_model,
        )

        if not config:
            raise HTTPException(status_code=404, detail=f"Role '{role}' not found")

        return RoleConfigResponse(
            name=config.name,
            provider=config.provider,
            model=config.model,
            system_prompt_id=config.system_prompt_id,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
            weight=config.weight,
            enabled=config.enabled,
            fallback_provider=config.fallback_provider,
            fallback_model=config.fallback_model,
            updated_at=config.updated_at,
        )


@router.get("/prompts/{role}", response_model=list[SystemPromptResponse])
async def list_prompts(role: str = PathParam(..., description="Role name")):
    """List all prompt versions for a role.

    Returns all prompt versions (active and inactive) for the specified role,
    ordered by version descending (newest first).

    Args:
        role: Role name (screener, tactical, fundamental, strategist)
    """
    factory = _get_session_factory()
    async with factory() as db:
        prompts = await ai_crud.get_prompts(db, role=role)
        return [
            SystemPromptResponse(
                id=p.id,
                role=p.role,
                version=p.version,
                content=p.content,
                description=p.description,
                is_active=p.is_active,
                created_at=p.created_at,
            )
            for p in prompts
        ]


@router.post("/prompts", response_model=SystemPromptResponse, status_code=201)
async def create_prompt(request: SystemPromptCreate):
    """Create a new prompt version.

    Creates a new versioned system prompt for the specified role.
    Version number is auto-incremented based on existing prompts for that role.

    Args:
        request: Prompt creation request with role, content, and description
    """
    factory = _get_session_factory()
    async with factory() as db:
        # Get next version number
        next_version = await ai_crud.get_next_version(db, request.role)

        # Generate prompt ID
        prompt_id = f"{request.role}_v{next_version}"

        # Force new prompts to be inactive by default to prevent multiple active prompts
        # Use activate endpoint to make a prompt active (which deactivates others)
        prompt = await ai_crud.create_prompt(
            db,
            prompt_id=prompt_id,
            role=request.role,
            version=next_version,
            content=request.content,
            description=request.description,
            is_active=False,  # Always create as inactive
        )

        return SystemPromptResponse(
            id=prompt.id,
            role=prompt.role,
            version=prompt.version,
            content=prompt.content,
            description=prompt.description,
            is_active=prompt.is_active,
            created_at=prompt.created_at,
        )


@router.put("/prompts/{prompt_id}/activate", response_model=SystemPromptResponse)
async def activate_prompt(prompt_id: str = PathParam(..., description="Prompt ID")):
    """Activate a prompt version.

    Activates the specified prompt and deactivates all other prompts for the same role.
    This changes which prompt will be used for future AI evaluations.

    Args:
        prompt_id: Prompt ID (e.g., "tactical_v2")
    """
    factory = _get_session_factory()
    async with factory() as db:
        prompt = await ai_crud.activate_prompt(db, prompt_id)
        if not prompt:
            raise HTTPException(status_code=404, detail=f"Prompt '{prompt_id}' not found")

        return SystemPromptResponse(
            id=prompt.id,
            role=prompt.role,
            version=prompt.version,
            content=prompt.content,
            description=prompt.description,
            is_active=prompt.is_active,
            created_at=prompt.created_at,
        )


# =============================================================================
# P2.1.2 - Evaluation Endpoints
# =============================================================================


@router.post("/evaluate", response_model=EvaluationResponse)
async def evaluate_opportunity(request: EvaluationRequest):
    """Trigger Multi-Brain evaluation for a symbol.

    Runs the full Multi-Brain pipeline with all active roles to generate
    a consensus trading decision.

    Args:
        request: Evaluation request with symbol, timeframe, and context data
    """
    router_instance = _get_router()
    factory = _get_session_factory()

    # Convert string role names to RoleName enums if provided
    roles = None
    if request.roles:
        try:
            roles = [RoleName(r) for r in request.roles]
        except ValueError as e:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid role name: {e}. Valid roles: {[r.value for r in RoleName]}",
            )

    # Run evaluation
    decision = await router_instance.evaluate_opportunity(
        symbol=request.symbol,
        timeframe=request.timeframe,
        candles=request.candles,
        indicators=request.indicators,
        portfolio=request.portfolio,
        risk_limits=request.risk_limits,
        roles=roles,
    )

    # Convert verdicts to JSON-serializable format
    verdict_dicts = [
        {
            "role": v.role.value,  # Convert RoleName enum to string
            "action": v.action,
            "confidence": v.confidence,
            "reasoning": v.reasoning,
            "metrics": v.metrics,
        }
        for v in decision.verdicts
    ]

    # Persist decision and usage logs to database
    async with factory() as db:
        # Log the aggregated decision
        logged_decision = await ai_crud.log_decision(
            db,
            symbol=request.symbol,
            timeframe=request.timeframe,
            final_action=decision.final_action,
            final_confidence=decision.final_confidence,
            verdicts=verdict_dicts,
            reasoning=decision.reasoning,
            vetoed_by=decision.vetoed_by.value if decision.vetoed_by else None,  # Convert RoleName to string
            total_cost_usd=decision.total_cost_usd,
            total_latency_ms=decision.total_latency_ms,
        )

        # Log per-role usage records from the router's usage log
        for usage_record in router_instance._usage_log:
            await ai_crud.log_usage(
                db,
                role=usage_record.role.value,
                provider=usage_record.provider.value,
                model=usage_record.model,
                tokens_in=usage_record.tokens_in,
                tokens_out=usage_record.tokens_out,
                cost_usd=usage_record.cost_usd,
                latency_ms=usage_record.latency_ms,
                symbol=usage_record.symbol,
                success=usage_record.success,
            )

    return EvaluationResponse(
        symbol=request.symbol,
        timeframe=request.timeframe,
        final_action=decision.final_action,
        final_confidence=decision.final_confidence,
        reasoning=decision.reasoning,
        verdicts=verdict_dicts,
        vetoed_by=decision.vetoed_by.value if decision.vetoed_by else None,  # Convert RoleName to string
        total_cost_usd=decision.total_cost_usd,
        total_latency_ms=decision.total_latency_ms,
        created_at=logged_decision.created_at,  # Use DB timestamp for consistency
    )


@router.post("/evaluate/single", response_model=dict)
async def evaluate_single_role(request: EvaluationRequest):
    """Test a single role (debugging endpoint).

    Runs only a single role for debugging/testing purposes.
    Requires exactly one role to be specified in the request.

    Args:
        request: Evaluation request with single role specified
    """
    if not request.roles or len(request.roles) != 1:
        raise HTTPException(
            status_code=400,
            detail="Exactly one role must be specified for single-role evaluation",
        )

    router_instance = _get_router()

    # Convert string role name to RoleName enum
    try:
        role = RoleName(request.roles[0])
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid role name '{request.roles[0]}'. Valid roles: {[r.value for r in RoleName]}",
        )

    # Run evaluation with single role
    decision = await router_instance.evaluate_opportunity(
        symbol=request.symbol,
        timeframe=request.timeframe,
        candles=request.candles,
        indicators=request.indicators,
        portfolio=request.portfolio,
        risk_limits=request.risk_limits,
        roles=[role],
    )

    # Return detailed response including individual role verdict
    return {
        "symbol": request.symbol,
        "timeframe": request.timeframe,
        "role": request.roles[0],
        "verdict": decision.verdicts[0].__dict__ if decision.verdicts else None,
        "final_action": decision.final_action,
        "final_confidence": decision.final_confidence,
        "reasoning": decision.reasoning,
        "cost_usd": decision.total_cost_usd,
        "latency_ms": decision.total_latency_ms,
    }


@router.get("/decisions", response_model=list[EvaluationResponse])
async def list_decisions(
    symbol: str | None = Query(None, description="Filter by symbol"),
    action: str | None = Query(None, description="Filter by action (BUY, SELL, NEUTRAL, VETO)"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of decisions to return"),
):
    """List past AI decisions (audit trail).

    Returns recent consensus decisions with optional filtering by symbol or action.
    Useful for auditing, backtesting, and analyzing AI performance.

    Args:
        symbol: Optional symbol filter
        action: Optional action filter (BUY, SELL, NEUTRAL, VETO)
        limit: Maximum number of results (default 100, max 1000)
    """
    factory = _get_session_factory()
    async with factory() as db:
        decisions = await ai_crud.get_decisions(
            db,
            symbol=symbol,
            action=action,
            limit=limit,
        )

        return [
            EvaluationResponse(
                symbol=d.symbol,
                timeframe=d.timeframe,
                final_action=d.final_action,
                final_confidence=d.final_confidence,
                reasoning=d.reasoning,
                verdicts=d.verdicts,
                vetoed_by=d.vetoed_by,
                total_cost_usd=d.total_cost_usd,
                total_latency_ms=d.total_latency_ms,
                created_at=d.created_at,
            )
            for d in decisions
        ]


# =============================================================================
# P2.1.3 - Usage/Cost Endpoints
# =============================================================================


@router.get("/usage", response_model=UsageSummaryResponse)
async def get_usage_summary(
    start_date: datetime | None = Query(None, description="Start date for usage summary"),
    end_date: datetime | None = Query(None, description="End date for usage summary"),
):
    """Get usage summary (by role, provider, time range).

    Returns aggregated token usage and costs across all AI evaluations.
    Useful for monitoring spending and identifying expensive operations.

    Args:
        start_date: Optional start date (default: 30 days ago)
        end_date: Optional end date (default: now)
    """
    # Default to last 30 days
    if not start_date:
        start_date = datetime.now(timezone.utc) - timedelta(days=30)
    if not end_date:
        end_date = datetime.now(timezone.utc)

    factory = _get_session_factory()
    async with factory() as db:
        summary = await ai_crud.get_usage_summary(
            db,
            start_date=start_date,
            end_date=end_date,
        )

        return UsageSummaryResponse(
            total_requests=summary.get("total_requests", 0),
            total_cost_usd=summary.get("total_cost_usd", 0.0),
            total_tokens_in=summary.get("total_tokens_in", 0),
            total_tokens_out=summary.get("total_tokens_out", 0),
            by_role=summary.get("by_role", {}),
            by_provider=summary.get("by_provider", {}),
        )


@router.get("/usage/daily", response_model=list[dict])
async def get_daily_usage(
    days: int = Query(30, ge=1, le=365, description="Number of days to return"),
):
    """Get daily cost breakdown.

    Returns per-day cost breakdown for the specified number of days.
    Useful for tracking spending trends over time.

    Args:
        days: Number of days to return (default 30, max 365)
    """
    factory = _get_session_factory()
    async with factory() as db:
        daily = await ai_crud.get_daily_usage(db, days=days)
        return daily
