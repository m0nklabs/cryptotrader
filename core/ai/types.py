"""AI module types — shared dataclasses and enums."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Literal


# ---------------------------------------------------------------------------
# Provider / Model enums
# ---------------------------------------------------------------------------


class ProviderName(str, Enum):
    """Supported LLM API providers."""

    DEEPSEEK = "deepseek"
    OPENAI = "openai"
    OPENROUTER = "openrouter"  # OpenAI-compatible gateway
    XAI = "xai"  # Grok
    OLLAMA = "ollama"  # Local inference
    GOOGLE = "google"  # Gemini


class RoleName(str, Enum):
    """Agent roles in the Multi-Brain topology."""

    SCREENER = "screener"  # Bulk filtering  (DeepSeek V3.2 default)
    TACTICAL = "tactical"  # Price action     (DeepSeek-R1 default)
    FUNDAMENTAL = "fundamental"  # News/sentiment   (Grok 4 default)
    STRATEGIST = "strategist"  # Risk/veto        (o3-mini default)


# ---------------------------------------------------------------------------
# Provider configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ProviderConfig:
    """Configuration for an LLM provider."""

    name: ProviderName
    api_key_env: str  # e.g. "DEEPSEEK_API_KEY"
    base_url: str  # e.g. "https://api.deepseek.com"
    default_model: str  # e.g. "deepseek-reasoner"
    max_tokens: int = 4096
    temperature: float = 0.0
    timeout_seconds: int = 60
    rate_limit_rpm: int = 60  # requests per minute


# ---------------------------------------------------------------------------
# Role configuration
# ---------------------------------------------------------------------------


@dataclass
class RoleConfig:
    """Configuration for an agent role."""

    name: RoleName
    provider: ProviderName
    model: str  # override provider default
    system_prompt_id: str  # key into PromptRegistry
    temperature: float = 0.0
    max_tokens: int = 4096
    weight: float = 1.0  # consensus weight
    enabled: bool = True
    fallback_provider: ProviderName | None = None
    fallback_model: str | None = None


# ---------------------------------------------------------------------------
# Prompt versioning
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SystemPrompt:
    """A versioned system prompt."""

    id: str  # e.g. "tactical_v1"
    role: RoleName
    version: int
    content: str
    created_at: datetime = field(default_factory=datetime.utcnow)
    description: str = ""
    is_active: bool = True


# ---------------------------------------------------------------------------
# Request / Response
# ---------------------------------------------------------------------------


@dataclass
class AIRequest:
    """A request to an AI agent role."""

    role: RoleName
    user_prompt: str
    context: dict[str, Any] = field(default_factory=dict)
    override_model: str | None = None
    override_temperature: float | None = None


@dataclass
class AIResponse:
    """Response from an AI agent role."""

    role: RoleName
    provider: ProviderName
    model: str
    raw_text: str
    parsed: dict[str, Any] | None = None
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: float = 0.0
    cost_usd: float = 0.0
    timestamp: datetime = field(default_factory=datetime.utcnow)
    error: str | None = None


# ---------------------------------------------------------------------------
# Consensus / Decision
# ---------------------------------------------------------------------------

SignalAction = Literal["BUY", "SELL", "NEUTRAL", "VETO"]


@dataclass
class RoleVerdict:
    """A single role's verdict on a trading opportunity."""

    role: RoleName
    action: SignalAction
    confidence: float  # 0.0 – 1.0
    reasoning: str
    metrics: dict[str, float] = field(default_factory=dict)


@dataclass
class ConsensusDecision:
    """Aggregated decision from all roles."""

    final_action: SignalAction
    final_confidence: float
    verdicts: list[RoleVerdict] = field(default_factory=list)
    reasoning: str = ""
    vetoed_by: RoleName | None = None
    total_cost_usd: float = 0.0
    total_latency_ms: float = 0.0


# ---------------------------------------------------------------------------
# Usage tracking
# ---------------------------------------------------------------------------


@dataclass
class UsageRecord:
    """Token/cost tracking per request."""

    role: RoleName
    provider: ProviderName
    model: str
    tokens_in: int
    tokens_out: int
    cost_usd: float
    latency_ms: float
    timestamp: datetime = field(default_factory=datetime.utcnow)
    symbol: str = ""
    success: bool = True
