"""Multi-Brain AI API routes.

Provides endpoints for AI configuration, evaluation, and usage tracking.

Phase 2.1 (P2.1) implementation of issue #205.
"""

from __future__ import annotations

import logging
import os
import ssl
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Path as PathParam
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from core.ai.prompts.registry import PromptRegistry
from core.ai.providers.base import ProviderRegistry
from core.ai.providers.deepseek import DEEPSEEK_R1_CONFIG, DEEPSEEK_V3_CONFIG, DeepSeekProvider
from core.ai.providers.ollama import OLLAMA_CONFIG, OllamaProvider
from core.ai.providers.openai import OPENAI_CONFIG, OpenAIProvider
from core.ai.providers.openrouter import OPENROUTER_CONFIG, OpenRouterProvider
from core.ai.providers.xai import XAI_CONFIG, XAIProvider
from core.ai.router import LLMRouter
from core.ai.roles.base import RoleRegistry
from core.ai.roles.fundamental import DEFAULT_FUNDAMENTAL_CONFIG, FundamentalRole
from core.ai.roles.screener import DEFAULT_SCREENER_CONFIG, ScreenerRole
from core.ai.roles.strategist import DEFAULT_STRATEGIST_CONFIG, StrategistRole
from core.ai.roles.tactical import DEFAULT_TACTICAL_CONFIG, TacticalRole
from core.ai.types import ProviderName, RoleConfig, RoleName
from db.crud import ai as ai_crud

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ai", tags=["ai"])

# Global database engine and session factory
_engine = None
_async_session_factory = None


def _asyncpg_ssl_connect_args_from_env() -> dict[str, ssl.SSLContext]:
    """Build asyncpg SSL connect args from environment.

    Supports PGSSLMODE/PGSSL* env vars and translates them into an SSLContext.
    Returns an empty dict when SSL is disabled or not configured.
    """
    sslmode = (os.environ.get("PGSSLMODE") or "").lower()
    if sslmode in {"", "disable"}:
        return {}

    sslrootcert = os.environ.get("PGSSLROOTCERT")
    sslcert = os.environ.get("PGSSLCERT")
    sslkey = os.environ.get("PGSSLKEY")

    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)

    if sslmode in {"verify-ca", "verify-full"}:
        context.check_hostname = sslmode == "verify-full"
        context.verify_mode = ssl.CERT_REQUIRED
    else:
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE

    if sslrootcert:
        context.load_verify_locations(cafile=sslrootcert)
    elif context.verify_mode == ssl.CERT_REQUIRED:
        context.load_default_certs()

    if sslcert and sslkey:
        context.load_cert_chain(certfile=sslcert, keyfile=sslkey)

    return {"ssl": context}


def _register_providers() -> None:
    """Register default provider instances."""
    ProviderRegistry.register(DeepSeekProvider())
    ProviderRegistry.register(OpenAIProvider())
    ProviderRegistry.register(XAIProvider())
    ProviderRegistry.register(OllamaProvider())
    ProviderRegistry.register(OpenRouterProvider())


def _role_defaults() -> dict[RoleName, RoleConfig]:
    return {
        RoleName.SCREENER: DEFAULT_SCREENER_CONFIG,
        RoleName.TACTICAL: DEFAULT_TACTICAL_CONFIG,
        RoleName.FUNDAMENTAL: DEFAULT_FUNDAMENTAL_CONFIG,
        RoleName.STRATEGIST: DEFAULT_STRATEGIST_CONFIG,
    }


def _role_factory() -> dict[RoleName, type]:
    return {
        RoleName.SCREENER: ScreenerRole,
        RoleName.TACTICAL: TacticalRole,
        RoleName.FUNDAMENTAL: FundamentalRole,
        RoleName.STRATEGIST: StrategistRole,
    }


def _register_default_roles() -> None:
    defaults = _role_defaults()
    factories = _role_factory()
    for role_name, role_config in defaults.items():
        role_class = factories[role_name]
        RoleRegistry.register(role_class(role_config))


def _role_config_from_db(db_config) -> RoleConfig | None:
    defaults = _role_defaults()
    try:
        role_name = RoleName(db_config.name)
        provider = ProviderName(db_config.provider)
        fallback_provider = ProviderName(db_config.fallback_provider) if db_config.fallback_provider else None
    except ValueError as exc:
        logger.warning("Skipping invalid role config %s: %s", db_config.name, exc)
        return None

    default_config = defaults.get(role_name)
    if default_config is None:
        return None
    return RoleConfig(
        name=role_name,
        provider=provider,
        model=db_config.model or default_config.model,
        system_prompt_id=db_config.system_prompt_id or default_config.system_prompt_id,
        temperature=db_config.temperature if db_config.temperature is not None else default_config.temperature,
        max_tokens=db_config.max_tokens or default_config.max_tokens,
        weight=db_config.weight if db_config.weight is not None else default_config.weight,
        enabled=db_config.enabled if db_config.enabled is not None else default_config.enabled,
        fallback_provider=fallback_provider or default_config.fallback_provider,
        fallback_model=db_config.fallback_model or default_config.fallback_model,
    )


async def bootstrap_ai() -> None:
    """Register providers, roles, and prompts for AI evaluation."""
    await ProviderRegistry.close_all()
    RoleRegistry.clear()
    PromptRegistry.clear()
    _register_providers()

    try:
        factory = _get_session_factory()
    except Exception as exc:
        logger.warning("AI bootstrap skipped DB load: %s", exc)
        PromptRegistry.load_defaults()
        _register_default_roles()
        return

    async with factory() as db:
        await PromptRegistry.load_from_db(db)
        configs = await ai_crud.get_role_configs(db)

    if not configs:
        _register_default_roles()
        return

    factories = _role_factory()
    for config in configs:
        role_config = _role_config_from_db(config)
        if not role_config:
            continue
        role_class = factories.get(role_config.name)
        if role_class is None:
            continue
        RoleRegistry.register(role_class(role_config))

    if not RoleRegistry.active_roles():
        _register_default_roles()


async def shutdown_ai() -> None:
    """Shutdown AI resources (providers + DB engine)."""
    global _engine, _async_session_factory

    await ProviderRegistry.close_all()
    RoleRegistry.clear()
    PromptRegistry.clear()

    if _engine is not None:
        await _engine.dispose()

    _engine = None
    _async_session_factory = None


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
            connect_args={"timeout": 3, **_asyncpg_ssl_connect_args_from_env()},
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


async def _require_ai_api_key(x_api_key: str | None = Header(None, alias="X-API-Key")) -> None:
    """Require a static API key when AI_API_KEY is set.

    Keeps local/dev usage frictionless, but blocks unauthenticated calls in exposed deployments.
    """
    import secrets

    expected = os.environ.get("AI_API_KEY")
    if not expected:
        return
    if not x_api_key or not secrets.compare_digest(x_api_key, expected):
        raise HTTPException(status_code=401, detail="Invalid API key")


router.dependencies = [Depends(_require_ai_api_key)]


def _provider_models(provider: ProviderName) -> list[str]:
    if provider == ProviderName.DEEPSEEK:
        return [DEEPSEEK_V3_CONFIG.default_model, DEEPSEEK_R1_CONFIG.default_model]
    if provider == ProviderName.OPENAI:
        return [OPENAI_CONFIG.default_model, "gpt-4", "gpt-4-turbo"]
    if provider == ProviderName.XAI:
        return [XAI_CONFIG.default_model, "grok-beta", "grok-vision-beta"]
    if provider == ProviderName.OLLAMA:
        return [OLLAMA_CONFIG.default_model, "llama3.2:3b", "llama3.1:8b"]
    if provider == ProviderName.OPENROUTER:
        return [OPENROUTER_CONFIG.default_model]
    return []


def _provider_factory(provider: ProviderName):
    if provider == ProviderName.DEEPSEEK:
        return DeepSeekProvider
    if provider == ProviderName.OPENAI:
        return OpenAIProvider
    if provider == ProviderName.XAI:
        return XAIProvider
    if provider == ProviderName.OLLAMA:
        return OllamaProvider
    if provider == ProviderName.OPENROUTER:
        return OpenRouterProvider
    return None


# =============================================================================
# Request/Response Models
# =============================================================================


class ProviderHealthResponse(BaseModel):
    """Provider health status response."""

    name: str
    healthy: bool
    model: str
    last_checked: datetime = Field(..., alias="lastChecked")
    message: str = ""

    model_config = ConfigDict(populate_by_name=True)


class RoleConfigResponse(BaseModel):
    """Role configuration response."""

    name: str
    provider: str
    model: str
    system_prompt_id: str | None = Field(None, alias="systemPromptId")
    temperature: float
    max_tokens: int = Field(..., alias="maxTokens")
    weight: float
    enabled: bool
    fallback_provider: str | None = Field(None, alias="fallbackProvider")
    fallback_model: str | None = Field(None, alias="fallbackModel")
    updated_at: datetime = Field(..., alias="updatedAt")

    model_config = ConfigDict(populate_by_name=True)


class RoleConfigUpdate(BaseModel):
    """Role configuration update request."""

    provider: str | None = None
    model: str | None = None
    system_prompt_id: str | None = Field(None, alias="systemPromptId")
    temperature: float | None = Field(None, ge=0.0, le=2.0)
    max_tokens: int | None = Field(None, gt=0, le=32000, alias="maxTokens")
    weight: float | None = Field(None, ge=0.0, le=10.0)
    enabled: bool | None = None
    fallback_provider: str | None = Field(None, alias="fallbackProvider")
    fallback_model: str | None = Field(None, alias="fallbackModel")

    model_config = ConfigDict(populate_by_name=True)


class SystemPromptResponse(BaseModel):
    """System prompt response."""

    id: str
    role: str
    version: int
    content: str
    description: str
    is_active: bool = Field(..., alias="isActive")
    created_at: datetime = Field(..., alias="createdAt")

    model_config = ConfigDict(populate_by_name=True)


class SystemPromptCreate(BaseModel):
    """Create new system prompt request.

    Prompts are created inactive by default. To activate a prompt,
    use the `/prompts/{id}/activate` endpoint.
    """

    role: str
    content: str
    description: str = ""
    is_active: bool = Field(False, alias="isActive")

    model_config = ConfigDict(populate_by_name=True)


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
    final_action: str = Field(..., alias="finalAction")
    final_confidence: float = Field(..., alias="finalConfidence")
    reasoning: str
    verdicts: list[dict]
    vetoed_by: str | None = Field(None, alias="vetoedBy")
    total_cost_usd: float = Field(0.0, alias="totalCostUsd")
    total_latency_ms: float = Field(0.0, alias="totalLatencyMs")
    created_at: datetime = Field(..., alias="createdAt")

    model_config = ConfigDict(populate_by_name=True)


class UsageSummaryResponse(BaseModel):
    """Usage summary response."""

    total_requests: int = Field(..., alias="totalRequests")
    total_cost_usd: float = Field(..., alias="totalCostUsd")
    total_tokens_in: int = Field(..., alias="totalTokensIn")
    total_tokens_out: int = Field(..., alias="totalTokensOut")
    by_role: dict[str, dict[str, Any]] = Field(..., alias="byRole")
    by_provider: dict[str, dict[str, Any]] = Field(..., alias="byProvider")

    model_config = ConfigDict(populate_by_name=True)


# =============================================================================
# P2.1.1 - CRUD Endpoints for AI Configuration
# =============================================================================


@router.get("/providers", response_model=list[ProviderHealthResponse])
async def list_providers():
    """List all providers and their health status.

    Returns status for each configured LLM provider including availability
    and supported models.
    """
    providers: list[ProviderHealthResponse] = []
    checked_at = datetime.now(timezone.utc)

    # Check each provider
    for provider in ProviderName.__members__.values():
        factory = _provider_factory(provider)
        models = _provider_models(provider)
        if factory is None:
            providers.append(
                ProviderHealthResponse(
                    name=provider.value,
                    healthy=False,
                    model=models[0] if models else "",
                    last_checked=checked_at,
                    message="Provider not implemented",
                )
            )
            continue

        instance = factory()
        api_key_env = instance.config.api_key_env
        if api_key_env:
            api_key = os.environ.get(api_key_env, "")
            if not api_key:
                await instance.close()  # Close before continue to prevent resource leak
                providers.append(
                    ProviderHealthResponse(
                        name=provider.value,
                        healthy=False,
                        model=models[0] if models else instance.config.default_model,
                        last_checked=checked_at,
                        message=f"Missing {api_key_env}",
                    )
                )
                continue

        try:
            healthy = await instance.health_check()
            message = "OK" if healthy else "Unavailable"
        except Exception:
            healthy = False
            logger.exception("Health check failed for provider %s", provider.value)
            message = "Health check failed"
        finally:
            await instance.close()

        providers.append(
            ProviderHealthResponse(
                name=provider.value,
                healthy=healthy,
                model=models[0] if models else instance.config.default_model,
                last_checked=checked_at,
                message=message,
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
    # Validate role name
    try:
        RoleName(role)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=(f"Invalid role name '{role}'. Valid roles: {[r.value for r in RoleName.__members__.values()]}"),
        )

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
                detail=(f"Invalid role name: {e}. Valid roles: {[r.value for r in RoleName.__members__.values()]}"),
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

    # Persist decision + usage logs to database (single transaction)
    usage_records = [
        {
            "role": u.role.value,
            "provider": u.provider.value,
            "model": u.model,
            "tokens_in": u.tokens_in,
            "tokens_out": u.tokens_out,
            "cost_usd": u.cost_usd,
            "latency_ms": u.latency_ms,
            "symbol": u.symbol,
            "success": u.success,
            "error": getattr(u, "error", None),
        }
        for u in router_instance.get_usage_log()
    ]

    async with factory() as db:
        logged_decision = await ai_crud.log_decision_with_usage(
            db,
            symbol=request.symbol,
            timeframe=request.timeframe,
            final_action=decision.final_action,
            final_confidence=decision.final_confidence,
            verdicts=verdict_dicts,
            reasoning=decision.reasoning,
            vetoed_by=decision.vetoed_by.value if decision.vetoed_by else None,
            total_cost_usd=decision.total_cost_usd,
            total_latency_ms=decision.total_latency_ms,
            usage_records=usage_records,
        )

    if usage_records:
        router_instance.clear_usage_log()

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


@router.get("/evaluate", response_model=EvaluationResponse)
async def evaluate_opportunity_get(
    symbol: str = Query(..., description="Trading symbol (e.g., BTC/USDT)"),
    timeframe: str = Query("1h", description="Timeframe (e.g., 1h, 4h, 1d)"),
    roles: str | None = Query(
        None,
        description="Optional comma-separated role list (e.g., tactical,strategist)",
    ),
):
    """GET wrapper for Multi-Brain evaluation.

    This endpoint exists for compatibility with the current frontend,
    which calls `/api/ai/evaluate` as a GET with query parameters.
    """
    role_list = [r.strip() for r in roles.split(",") if r.strip()] if roles else None
    request = EvaluationRequest(
        symbol=symbol,
        timeframe=timeframe,
        candles=None,
        indicators=None,
        portfolio=None,
        risk_limits=None,
        roles=role_list,
    )
    return await evaluate_opportunity(request)


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
            detail=(
                f"Invalid role name '{request.roles[0]}'. Valid roles: {[r.value for r in RoleName.__members__.values()]}"
            ),
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
        "verdict": (
            {
                "role": decision.verdicts[0].role.value,
                "action": decision.verdicts[0].action,
                "confidence": decision.verdicts[0].confidence,
                "reasoning": decision.verdicts[0].reasoning,
                "metrics": decision.verdicts[0].metrics,
            }
            if decision.verdicts
            else None
        ),
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

        by_role = {
            role: {
                "cost": details.get("cost_usd", 0.0),
                "requests": details.get("requests", 0),
                "avgLatencyMs": details.get("avg_latency_ms", 0.0),
            }
            for role, details in summary.get("by_role", {}).items()
        }
        by_provider = {
            provider: {
                "cost": details.get("cost_usd", 0.0),
                "requests": details.get("requests", 0),
            }
            for provider, details in summary.get("by_provider", {}).items()
        }

        return UsageSummaryResponse(
            total_requests=summary.get("total_requests", 0),
            total_cost_usd=summary.get("total_cost_usd", 0.0),
            total_tokens_in=summary.get("total_tokens_in", 0),
            total_tokens_out=summary.get("total_tokens_out", 0),
            by_role=by_role,
            by_provider=by_provider,
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
