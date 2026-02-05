"""Strategist role — portfolio-level risk management and veto power.

Default provider: o3-mini (strong reasoning, moderate cost)
Purpose: Evaluate proposed trades against portfolio exposure, risk
limits, correlation, and provide go/no-go + position sizing.
"""

from __future__ import annotations

import json
import logging

from core.ai.roles.base import AgentRole
from core.ai.types import (
    AIRequest,
    AIResponse,
    ProviderName,
    RoleConfig,
    RoleName,
    RoleVerdict,
    SignalAction,
)

logger = logging.getLogger(__name__)

DEFAULT_STRATEGIST_CONFIG = RoleConfig(
    name=RoleName.STRATEGIST,
    provider=ProviderName.OPENAI,
    model="o3-mini",
    system_prompt_id="strategist_v1",
    temperature=0.0,
    max_tokens=4096,
    weight=1.2,  # high weight — risk veto
    fallback_provider=ProviderName.DEEPSEEK,
    fallback_model="deepseek-reasoner",
)


class StrategistRole(AgentRole):
    """Strategist — portfolio risk and position sizing.

    Input:  Proposed trade + current portfolio state + risk limits.
    Output: APPROVE/VETO with position size recommendation.
    """

    def __init__(self, config: RoleConfig | None = None) -> None:
        super().__init__(config or DEFAULT_STRATEGIST_CONFIG)

    def build_prompt(self, request: AIRequest) -> str:
        """Build a risk-focused prompt with portfolio context."""
        symbol = request.context.get("symbol", "UNKNOWN")
        proposed_action = request.context.get("proposed_action", "UNKNOWN")
        portfolio = request.context.get("portfolio", {})
        risk_limits = request.context.get("risk_limits", {})

        prompt_parts = [
            f"Evaluate proposed {proposed_action} on {symbol}.",
            "",
            "Current portfolio state:",
            json.dumps(portfolio, indent=2, default=str),
            "",
            "Risk limits:",
            json.dumps(risk_limits, indent=2, default=str),
            "",
            request.user_prompt,
        ]
        return "\n".join(prompt_parts)

    def parse_response(self, response: AIResponse) -> RoleVerdict:
        """Parse strategist response — can VETO trades."""
        if response.error:
            # On error, default to VETO for safety
            return RoleVerdict(
                role=RoleName.STRATEGIST,
                action="VETO",
                confidence=1.0,
                reasoning=f"Strategist error (defaulting to VETO): {response.error}",
            )

        action: SignalAction = "NEUTRAL"
        confidence = 0.5
        reasoning = response.raw_text
        metrics: dict[str, float] = {}

        if response.parsed and isinstance(response.parsed, dict):
            action = response.parsed.get("action", "NEUTRAL")
            confidence = float(response.parsed.get("confidence", 0.5))
            reasoning = response.parsed.get("reasoning", response.raw_text)
            for key in ("position_size_pct", "portfolio_risk_pct", "correlation_score"):
                if key in response.parsed:
                    metrics[key] = float(response.parsed[key])

        return RoleVerdict(
            role=RoleName.STRATEGIST,
            action=action,
            confidence=confidence,
            reasoning=reasoning,
            metrics=metrics,
        )
