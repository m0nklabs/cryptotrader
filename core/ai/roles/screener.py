"""Screener role — high-throughput bulk filtering.

Default provider: DeepSeek V3.2 (cheapest, fast)
Purpose: Quickly scan many symbols and discard obvious no-trades.
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

DEFAULT_SCREENER_CONFIG = RoleConfig(
    name=RoleName.SCREENER,
    provider=ProviderName.DEEPSEEK,
    model="deepseek-chat",  # V3.2
    system_prompt_id="screener_v1",
    temperature=0.0,
    max_tokens=1024,  # short answers
    weight=0.5,  # lowest weight — filtering only
    fallback_provider=ProviderName.OLLAMA,
    fallback_model="llama3.2",
)


class ScreenerRole(AgentRole):
    """Bulk screener — filters symbols for further analysis.

    Input:  list of symbols + their latest indicator snapshots.
    Output: pass/fail per symbol with brief reasoning.
    """

    def __init__(self, config: RoleConfig | None = None) -> None:
        super().__init__(config or DEFAULT_SCREENER_CONFIG)

    def build_prompt(self, request: AIRequest) -> str:
        """Build a screening prompt from the request context."""
        # Context should contain: symbols, indicators, timeframe
        symbols = request.context.get("symbols", [])
        timeframe = request.context.get("timeframe", "1h")
        indicators = request.context.get("indicators", {})

        prompt_parts = [
            f"Screen the following {len(symbols)} symbols on {timeframe} timeframe.",
            f"Symbols: {', '.join(symbols)}",
            "",
            "Indicator data:",
            json.dumps(indicators, indent=2, default=str),
            "",
            request.user_prompt,
        ]
        return "\n".join(prompt_parts)

    def parse_response(self, response: AIResponse) -> RoleVerdict:
        """Parse screener response into a verdict."""
        if response.error:
            return RoleVerdict(
                role=RoleName.SCREENER,
                action="NEUTRAL",
                confidence=0.0,
                reasoning=f"Screener error: {response.error}",
            )

        # Try to extract structured data
        action: SignalAction = "NEUTRAL"
        confidence = 0.5
        reasoning = response.raw_text

        if response.parsed and isinstance(response.parsed, dict):
            action = response.parsed.get("action", "NEUTRAL")
            confidence = float(response.parsed.get("confidence", 0.5))
            reasoning = response.parsed.get("reasoning", response.raw_text)

        return RoleVerdict(
            role=RoleName.SCREENER,
            action=action,
            confidence=confidence,
            reasoning=reasoning,
        )
