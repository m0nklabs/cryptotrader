"""Fundamental role — news, sentiment, and macro analysis.

Default provider: Grok 4 (real-time web search + X/Twitter)
Purpose: Assess news sentiment, social buzz, macro events, and
on-chain data for fundamental outlook.
"""

from __future__ import annotations

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

DEFAULT_FUNDAMENTAL_CONFIG = RoleConfig(
    name=RoleName.FUNDAMENTAL,
    provider=ProviderName.XAI,
    model="grok-4",
    system_prompt_id="fundamental_v1",
    temperature=0.0,
    max_tokens=4096,
    weight=1.0,
    fallback_provider=ProviderName.DEEPSEEK,
    fallback_model="deepseek-chat",
)


class FundamentalRole(AgentRole):
    """Fundamental analyst — news and sentiment.

    Input:  Symbol + recent news/social snippets + on-chain metrics.
    Output: Bullish/bearish/neutral sentiment with event risk flags.
    """

    def __init__(self, config: RoleConfig | None = None) -> None:
        super().__init__(config or DEFAULT_FUNDAMENTAL_CONFIG)

    def build_prompt(self, request: AIRequest) -> str:
        """Build a fundamentals-focused prompt."""
        symbol = request.context.get("symbol", "UNKNOWN")
        timeframe = request.context.get("timeframe", "1h")
        # Grok can search the web, so the prompt can be simpler
        prompt_parts = [
            f"Provide a fundamental analysis for {symbol}.",
            f"Trading timeframe: {timeframe}.",
            "",
            "Consider: recent news, social media sentiment, macro events,",
            "regulatory developments, and on-chain metrics if available.",
            "",
            request.user_prompt,
        ]
        return "\n".join(prompt_parts)

    def parse_response(self, response: AIResponse) -> RoleVerdict:
        """Parse fundamental response into a verdict."""
        if response.error:
            return RoleVerdict(
                role=RoleName.FUNDAMENTAL,
                action="NEUTRAL",
                confidence=0.0,
                reasoning=f"Fundamental error: {response.error}",
            )

        action: SignalAction = "NEUTRAL"
        confidence = 0.5
        reasoning = response.raw_text
        metrics: dict[str, float] = {}

        if response.parsed and isinstance(response.parsed, dict):
            action = response.parsed.get("action", "NEUTRAL")
            confidence = float(response.parsed.get("confidence", 0.5))
            reasoning = response.parsed.get("reasoning", response.raw_text)
            for key in ("sentiment_score", "event_risk", "social_volume"):
                if key in response.parsed:
                    metrics[key] = float(response.parsed[key])

        return RoleVerdict(
            role=RoleName.FUNDAMENTAL,
            action=action,
            confidence=confidence,
            reasoning=reasoning,
            metrics=metrics,
        )
