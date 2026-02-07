"""Fundamental role — news, sentiment, and macro analysis.

Default provider: Grok 4 (real-time web search + X/Twitter)
Purpose: Assess news sentiment, social buzz, macro events, and
on-chain data for fundamental outlook.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta, timezone

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

    Features:
    - Integrates Grok 4's web search capability for real-time news
    - Parses and structures news items from search results
    - Sentiment scoring from news + social data
    - Market event detection (listings, delistings, regulatory)
    """

    def __init__(self, config: RoleConfig | None = None) -> None:
        super().__init__(config or DEFAULT_FUNDAMENTAL_CONFIG)

    def _parse_news_items(self, news_data: list[dict] | str) -> list[dict]:
        """Parse news items into structured format.

        Args:
            news_data: Either a list of news dicts or raw text to parse

        Returns:
            List of structured news items
        """
        if isinstance(news_data, list):
            # Already structured
            return news_data

        # Parse from text (fallback if web search returns unstructured data)
        # Look for patterns like: "Title: ... Source: ... Date: ..."
        items = []
        if isinstance(news_data, str):
            # Split by double newlines or numbered items
            chunks = re.split(r"\n\n+|\n\d+\.\s+", news_data)
            for chunk in chunks:
                if len(chunk.strip()) > 20:  # Skip very short chunks
                    items.append(
                        {
                            "title": chunk.strip()[:200],
                            "source": "unknown",
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        }
                    )

        return items[:10]  # Limit to 10 items

    def _calculate_sentiment_score(self, news_items: list[dict], response_text: str) -> dict[str, float]:
        """Calculate sentiment metrics from news and LLM analysis.

        Args:
            news_items: Structured news items
            response_text: LLM response text

        Returns:
            Dictionary with sentiment metrics
        """
        metrics = {
            "news_count": float(len(news_items)),
            "sentiment_score": 0.0,  # -1.0 (bearish) to 1.0 (bullish)
            "event_risk": 0.0,  # 0.0 (low) to 1.0 (high)
            "social_volume": 0.0,  # Relative social media activity
        }

        # Extract sentiment from LLM response
        text_lower = response_text.lower()

        # Simple keyword-based sentiment (refined by LLM structured output)
        bullish_words = ["bullish", "positive", "growth", "rally", "breakout", "adoption"]
        bearish_words = ["bearish", "negative", "decline", "crash", "concern", "risk"]

        bullish_count = sum(1 for word in bullish_words if word in text_lower)
        bearish_count = sum(1 for word in bearish_words if word in text_lower)

        if bullish_count + bearish_count > 0:
            metrics["sentiment_score"] = (bullish_count - bearish_count) / (bullish_count + bearish_count)

        # Event risk keywords
        risk_words = ["regulatory", "ban", "hack", "lawsuit", "investigation", "delisting"]
        risk_count = sum(1 for word in risk_words if word in text_lower)
        metrics["event_risk"] = min(1.0, risk_count / 3.0)  # Normalize to 0-1

        return metrics

    def build_prompt(self, request: AIRequest) -> str:
        """Build a fundamentals-focused prompt.

        Grok can search the web, so we structure the prompt to leverage that.
        """
        symbol = request.context.get("symbol", "UNKNOWN")
        timeframe = request.context.get("timeframe", "1h")
        news_data = request.context.get("news", [])
        social_data = request.context.get("social", {})
        onchain_metrics = request.context.get("onchain", {})

        # Parse news if provided
        news_items = self._parse_news_items(news_data)

        # Build time context for news search
        lookback_hours = {"1m": 6, "5m": 12, "15m": 24, "1h": 48, "4h": 168, "1d": 336}
        hours = lookback_hours.get(timeframe, 48)
        since_date = (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime("%Y-%m-%d")

        prompt_parts = [
            f"Provide a fundamental analysis for {symbol}.",
            f"Trading timeframe: {timeframe}.",
            "",
            "=== INSTRUCTIONS ===",
            f"1. Search for recent news about {symbol} (since {since_date})",
            "2. Analyze sentiment from news headlines and content",
            "3. Identify any major events: partnerships, listings, regulatory news, hacks, etc.",
            "4. Assess social media sentiment if available",
            "5. Consider on-chain metrics if relevant (for crypto assets)",
            "",
        ]

        if news_items:
            prompt_parts.extend(
                [
                    "=== PROVIDED NEWS CONTEXT ===",
                    json.dumps(news_items, indent=2, default=str),
                    "",
                ]
            )

        if social_data:
            prompt_parts.extend(
                [
                    "=== SOCIAL MEDIA DATA ===",
                    json.dumps(social_data, indent=2, default=str),
                    "",
                ]
            )

        if onchain_metrics:
            prompt_parts.extend(
                [
                    "=== ON-CHAIN METRICS ===",
                    json.dumps(onchain_metrics, indent=2, default=str),
                    "",
                ]
            )

        prompt_parts.extend(
            [
                request.user_prompt,
                "",
                "RESPONSE FORMAT:",
                "Provide your analysis in JSON format with the following structure:",
                "{",
                '  "action": "BUY" | "SELL" | "NEUTRAL",',
                '  "confidence": 0.0-1.0,',
                '  "reasoning": "detailed fundamental analysis",',
                '  "sentiment_score": -1.0 to 1.0,  // -1=bearish, 0=neutral, 1=bullish',
                '  "event_risk": 0.0-1.0,  // 0=low risk, 1=high risk',
                '  "social_volume": 0.0-1.0,  // Relative social activity',
                '  "key_events": ["event1", "event2", ...],  // Major news items',
                '  "news_summary": "brief summary of key news"',
                "}",
            ]
        )

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

            # Extract sentiment metrics
            for key in ("sentiment_score", "event_risk", "social_volume"):
                if key in response.parsed:
                    try:
                        value = float(response.parsed[key])
                        # Clamp to valid ranges
                        if key == "sentiment_score":
                            value = max(-1.0, min(1.0, value))
                        else:
                            value = max(0.0, min(1.0, value))
                        metrics[key] = value
                    except (ValueError, TypeError):
                        continue

            # Extract key events count (accept both key_events and major_news_items)
            key_events = response.parsed.get("key_events")
            if not isinstance(key_events, list):
                key_events = response.parsed.get("major_news_items", [])
            if isinstance(key_events, list):
                metrics["key_events_count"] = float(len(key_events))

        else:
            # Fallback: calculate sentiment from raw text
            news_items = self._parse_news_items([])  # Empty, will use response text
            fallback_metrics = self._calculate_sentiment_score(news_items, response.raw_text)
            metrics.update(fallback_metrics)

        return RoleVerdict(
            role=RoleName.FUNDAMENTAL,
            action=action,
            confidence=confidence,
            reasoning=reasoning,
            metrics=metrics,
        )
