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
    GUARDIAN = "guardian"  # llama_cpp_guardian proxy — LOCAL, always prefer this
    GOOGLE = "google"  # Gemini
    OLLAMA = "ollama"  # DEPRECATED — use GUARDIAN instead


class RoleName(str, Enum):
    """Agent roles in the Multi-Brain topology."""

    SCREENER = "screener"  # Bulk filtering  (DeepSeek V3.2 default)
    TACTICAL = "tactical"  # Price action     (DeepSeek-R1 default)
    FUNDAMENTAL = "fundamental"  # News/sentiment   (Grok 4 default)
    STRATEGIST = "strategist"  # Risk/veto        (o3-mini default)


# ---------------------------------------------------------------------------
# Provider error taxonomy
# ---------------------------------------------------------------------------


class ProviderErrorType(str, Enum):
    """Normalized error taxonomy for provider failures."""

    RATE_LIMITED = "rate_limited"
    TIMEOUT = "timeout"
    INVALID_RESPONSE = "invalid_response"
    AUTH_ERROR = "auth_error"
    NETWORK_ERROR = "network_error"
    SERVER_ERROR = "server_error"
    CLIENT_ERROR = "client_error"
    CIRCUIT_BREAKER_OPEN = "circuit_breaker_open"
    UNKNOWN = "unknown"


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
    timeout_connect_seconds: float | None = None
    timeout_read_seconds: float | None = None
    timeout_write_seconds: float | None = None
    timeout_pool_seconds: float | None = None
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
    error_type: ProviderErrorType | None = None


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
    error: str | None = None  # Error message for failed requests


# ---------------------------------------------------------------------------
# Execution / Risk types
# ---------------------------------------------------------------------------


@dataclass
class RiskGateResult:
    """Result of a single risk gate check."""

    gate: str
    passed: bool
    reason: str = ""
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class RiskDecision:
    """Complete risk-gate evaluation result for a symbol."""

    symbol: str
    timeframe: str
    final_action: SignalAction
    final_confidence: float
    gate_results: list[RiskGateResult] = field(default_factory=list)
    action: str = ""  # "EXECUTED" or "REJECTED"
    reason: str = ""
    paper_order: Any = None  # PaperOrder from core.execution.paper
    market_price: Any = None  # Decimal
    portfolio_value: Any = None  # Decimal
    position_size: Any = None  # Decimal
    position_value: Any = None  # Decimal
    latency_ms: float = 0.0
    timestamp: datetime = field(default_factory=datetime.utcnow)
    verdicts: list[RoleVerdict] = field(default_factory=list)
    vetoed_by: RoleName | None = None
    reasoning: str = ""


@dataclass
class PaperOrderIntent:
    """Intent to create a paper order."""

    symbol: str
    side: SignalAction
    qty: Any = None  # Decimal
    order_type: str = "market"  # "market" or "limit"
    limit_price: Any = None  # Decimal
    market_price: Any = None  # Decimal
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AIDecision:
    """AI decision record (consensus-driven trade decision)."""

    symbol: str
    timeframe: str
    final_action: SignalAction
    final_confidence: float
    verdicts: list[RoleVerdict] = field(default_factory=list)
    reasoning: str = ""
    vetoed_by: RoleName | None = None
    total_cost_usd: float = 0.0
    total_latency_ms: float = 0.0
    created_at: datetime = field(default_factory=datetime.utcnow)
