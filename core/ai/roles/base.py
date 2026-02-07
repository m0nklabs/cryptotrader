"""Base agent role and role registry."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Any, Sequence

from core.ai.providers.base import ProviderRegistry
from core.ai.types import (
    AIRequest,
    AIResponse,
    RoleConfig,
    RoleName,
    RoleVerdict,
)
from core.types import Candle

logger = logging.getLogger(__name__)


class AgentRole(ABC):
    """Abstract base for an agent role in the Multi-Brain topology.

    Each role knows:
    - Which provider/model to use (primary + fallback)
    - Its system prompt key
    - How to parse the LLM response into a ``RoleVerdict``
    """

    def __init__(self, config: RoleConfig) -> None:
        self.config = config

    @property
    def name(self) -> RoleName:
        return self.config.name

    @property
    def weight(self) -> float:
        return self.config.weight

    @abstractmethod
    def build_prompt(self, request: AIRequest) -> str:
        """Build the user-prompt from the AI request context.

        Roles can enrich the prompt with indicator data, news snippets,
        portfolio state, etc. depending on their domain.
        """

    @abstractmethod
    def parse_response(self, response: AIResponse) -> RoleVerdict:
        """Parse the raw LLM response into a structured verdict."""

    async def evaluate(
        self,
        request: AIRequest,
        system_prompt: str,
    ) -> tuple[AIResponse, RoleVerdict]:
        """Run the full evaluation pipeline for this role.

        1. Resolve the provider
        2. Build the enriched prompt
        3. Call the LLM
        4. Parse the response into a verdict

        Falls back to ``fallback_provider`` if the primary fails.
        """
        enriched_prompt = self.build_prompt(request)
        enriched_request = AIRequest(
            role=request.role,
            user_prompt=enriched_prompt,
            context=request.context,
        )

        # Try primary provider
        provider = ProviderRegistry.get(self.config.provider)
        if provider is None:
            logger.error("Provider %s not registered", self.config.provider)
            raise RuntimeError(f"Provider {self.config.provider} not registered")

        response = await provider.complete(
            enriched_request,
            system_prompt=system_prompt,
            model=self.config.model,
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
        )

        # Fallback on error
        if response.error and self.config.fallback_provider:
            logger.warning(
                "Role %s primary failed, trying fallback %s",
                self.name.value,
                self.config.fallback_provider.value,
            )
            fallback = ProviderRegistry.get(self.config.fallback_provider)
            if fallback:
                response = await fallback.complete(
                    enriched_request,
                    system_prompt=system_prompt,
                    model=self.config.fallback_model or fallback.config.default_model,
                    temperature=self.config.temperature,
                    max_tokens=self.config.max_tokens,
                )

        verdict = self.parse_response(response)
        return response, verdict


class RoleRegistry:
    """Registry of active agent roles."""

    _roles: dict[RoleName, AgentRole] = {}

    @classmethod
    def register(cls, role: AgentRole) -> None:
        cls._roles[role.name] = role
        logger.info("Registered AI role: %s", role.name.value)

    @classmethod
    def get(cls, name: RoleName) -> AgentRole | None:
        return cls._roles.get(name)

    @classmethod
    def active_roles(cls) -> list[AgentRole]:
        """Return all enabled roles, ordered by weight (descending)."""
        return sorted(
            [r for r in cls._roles.values() if r.config.enabled],
            key=lambda r: r.weight,
            reverse=True,
        )

    @classmethod
    def clear(cls) -> None:
        cls._roles.clear()


# ---------------------------------------------------------------------------
# Common helpers for role implementations
# ---------------------------------------------------------------------------


def serialize_candles(
    candles: Sequence[Candle],
    max_candles: int | None = None,
    include_full_data: bool = False,
) -> list[dict[str, Any]]:
    """Serialize candles for LLM prompt.

    Args:
        candles: Sequence of OHLCV candles
        max_candles: Optional limit on number of candles to include
        include_full_data: If True, include all OHLCV data; if False, only close prices

    Returns:
        List of serialized candle dictionaries
    """
    if not candles:
        return []

    # Take most recent candles if limit specified
    selected = candles[-max_candles:] if max_candles else candles

    if include_full_data:
        return [
            {
                "time": c.open_time.isoformat(),
                "open": float(c.open),
                "high": float(c.high),
                "low": float(c.low),
                "close": float(c.close),
                "volume": float(c.volume),
            }
            for c in selected
        ]
    else:
        # Compact format: just timestamp + close for quick analysis
        return [
            {
                "time": c.open_time.isoformat(),
                "close": float(c.close),
            }
            for c in selected
        ]


def serialize_indicators(indicators: dict[str, Any]) -> dict[str, Any]:
    """Serialize indicator values for LLM prompt.

    Handles Decimal conversion and formats values consistently.

    Args:
        indicators: Dictionary of indicator names to values

    Returns:
        Serialized indicator dictionary safe for JSON encoding
    """
    result = {}
    for key, value in indicators.items():
        if isinstance(value, Decimal):
            result[key] = float(value)
        elif isinstance(value, dict):
            result[key] = serialize_indicators(value)
        elif isinstance(value, (list, tuple)):
            result[key] = [
                float(v) if isinstance(v, Decimal) else v
                for v in value
            ]
        else:
            result[key] = value
    return result


def format_portfolio_state(
    positions: list[dict[str, Any]],
    total_equity: float,
    available_balance: float,
) -> dict[str, Any]:
    """Format portfolio state for strategist role.

    Args:
        positions: List of open position dictionaries
        total_equity: Total portfolio equity
        available_balance: Available balance for new trades

    Returns:
        Formatted portfolio state dictionary
    """
    return {
        "total_equity": total_equity,
        "available_balance": available_balance,
        "num_positions": len(positions),
        "positions": [
            {
                "symbol": p.get("symbol"),
                "side": p.get("side"),
                "size": float(p.get("quantity", 0)),
                "entry_price": float(p.get("avg_entry_price", 0)),
                "unrealized_pnl": float(p.get("unrealized_pnl", 0)),
                "notional": float(p.get("notional", 0)),
            }
            for p in positions
        ],
        "total_exposure": sum(float(p.get("notional", 0)) for p in positions),
    }


def calculate_position_size_kelly(
    win_rate: float,
    avg_win: float,
    avg_loss: float,
    max_kelly_fraction: float = 0.25,
) -> float:
    """Calculate position size using Kelly Criterion.

    Note: This is a simplified implementation assuming independent trades
    and stationary win rate/returns. Real-world trading with autocorrelated
    returns may require fractional Kelly or other adjustments.

    Args:
        win_rate: Historical win rate (0.0-1.0)
        avg_win: Average winning trade size (positive)
        avg_loss: Average losing trade size (positive)
        max_kelly_fraction: Maximum Kelly fraction to use (default 0.25 for quarter-Kelly)

    Returns:
        Recommended position size as fraction of capital (0.0-1.0)
    """
    if avg_loss == 0 or win_rate == 0:
        return 0.0

    # Kelly formula: f* = (p*b - q) / b
    # where p = win_rate, q = 1-win_rate, b = avg_win/avg_loss
    b = avg_win / avg_loss
    kelly_fraction = (win_rate * b - (1 - win_rate)) / b

    # Clamp to reasonable bounds
    kelly_fraction = max(0.0, min(kelly_fraction, max_kelly_fraction))

    return kelly_fraction


def calculate_risk_metrics(
    proposed_size: float,
    entry_price: float,
    stop_loss: float,
    total_equity: float,
    max_risk_per_trade: float = 0.02,
) -> dict[str, float]:
    """Calculate risk metrics for a proposed trade.

    Args:
        proposed_size: Proposed position size in base asset
        entry_price: Entry price
        stop_loss: Stop loss price
        total_equity: Total portfolio equity
        max_risk_per_trade: Maximum risk per trade as fraction (default 2%)

    Returns:
        Dictionary with risk metrics
    """
    notional = proposed_size * entry_price
    risk_per_unit = abs(entry_price - stop_loss)
    total_risk = proposed_size * risk_per_unit
    risk_pct = total_risk / total_equity if total_equity > 0 else 0.0

    return {
        "notional": notional,
        "risk_per_unit": risk_per_unit,
        "total_risk": total_risk,
        "risk_pct": risk_pct,
        "risk_pct_of_max": risk_pct / max_risk_per_trade if max_risk_per_trade > 0 else 0.0,
        "exceeds_limit": risk_pct > max_risk_per_trade,
    }
