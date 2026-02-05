"""Tactical role — price-action and technical analysis specialist.

Default provider: DeepSeek-R1 (best reasoning for TA patterns)
Purpose: Analyze chart patterns, support/resistance, indicator
convergence and generate entry/exit signals.
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

DEFAULT_TACTICAL_CONFIG = RoleConfig(
    name=RoleName.TACTICAL,
    provider=ProviderName.DEEPSEEK,
    model="deepseek-reasoner",  # R1
    system_prompt_id="tactical_v1",
    temperature=0.0,
    max_tokens=4096,
    weight=1.5,  # highest weight — core TA role
    fallback_provider=ProviderName.OPENAI,
    fallback_model="o3-mini",
)


class TacticalRole(AgentRole):
    """Tactical analyst — technical analysis and price action.

    Input:  OHLCV candles + computed indicators for a single symbol.
    Output: BUY/SELL/NEUTRAL with entry, stop-loss, take-profit levels.
    """

    def __init__(self, config: RoleConfig | None = None) -> None:
        super().__init__(config or DEFAULT_TACTICAL_CONFIG)

    def build_prompt(self, request: AIRequest) -> str:
        """Build a TA-focused prompt from candle + indicator data."""
        symbol = request.context.get("symbol", "UNKNOWN")
        timeframe = request.context.get("timeframe", "1h")
        candles = request.context.get("candles", [])
        indicators = request.context.get("indicators", {})

        prompt_parts = [
            f"Analyze {symbol} on {timeframe} timeframe.",
            f"Last {len(candles)} candles provided.",
            "",
            "Indicator values:",
            json.dumps(indicators, indent=2, default=str),
            "",
            request.user_prompt,
        ]
        return "\n".join(prompt_parts)

    def parse_response(self, response: AIResponse) -> RoleVerdict:
        """Parse tactical response into a verdict with price levels."""
        if response.error:
            return RoleVerdict(
                role=RoleName.TACTICAL,
                action="NEUTRAL",
                confidence=0.0,
                reasoning=f"Tactical error: {response.error}",
            )

        action: SignalAction = "NEUTRAL"
        confidence = 0.5
        reasoning = response.raw_text
        metrics: dict[str, float] = {}

        if response.parsed and isinstance(response.parsed, dict):
            action = response.parsed.get("action", "NEUTRAL")
            confidence = float(response.parsed.get("confidence", 0.5))
            reasoning = response.parsed.get("reasoning", response.raw_text)
            # Extract price levels if present
            for key in ("entry", "stop_loss", "take_profit", "risk_reward"):
                if key in response.parsed:
                    metrics[key] = float(response.parsed[key])

        return RoleVerdict(
            role=RoleName.TACTICAL,
            action=action,
            confidence=confidence,
            reasoning=reasoning,
            metrics=metrics,
        )
