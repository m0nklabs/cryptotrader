"""Tactical role — price-action and technical analysis specialist.

Default provider: DeepSeek-R1 (best reasoning for TA patterns)
Purpose: Analyze chart patterns, support/resistance, indicator
convergence and generate entry/exit signals.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Sequence

from core.ai.roles.base import AgentRole, serialize_candles, serialize_indicators
from core.ai.types import (
    AIRequest,
    AIResponse,
    ProviderName,
    RoleConfig,
    RoleName,
    RoleVerdict,
    SignalAction,
)
from core.types import Candle

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

    Features:
    - OHLCV candle serialization with configurable depth (100/500/2000+)
    - Two-stage prompting: internal reasoning → JSON-only output
    - Entry/exit level extraction from LLM response
    - Timeframe-aware context (inject multiple timeframes if configured)
    - Support/resistance level calculations
    """

    def __init__(self, config: RoleConfig | None = None) -> None:
        super().__init__(config or DEFAULT_TACTICAL_CONFIG)

    def _calculate_support_resistance(
        self, candles: Sequence[Candle], lookback: int = 50
    ) -> dict[str, float]:
        """Calculate support and resistance levels from recent price action.

        Args:
            candles: Recent candles
            lookback: Number of candles to analyze

        Returns:
            Dictionary with support/resistance levels
        """
        if len(candles) < lookback:
            lookback = len(candles)

        recent = candles[-lookback:]
        prices = [float(c.close) for c in recent]
        highs = [float(c.high) for c in recent]
        lows = [float(c.low) for c in recent]

        current_price = prices[-1]

        # Simple support/resistance: find recent significant high/low
        resistance = max(highs)
        support = min(lows)

        # Calculate distance to levels
        resistance_distance = (resistance - current_price) / current_price
        support_distance = (current_price - support) / current_price

        return {
            "current_price": current_price,
            "resistance": resistance,
            "support": support,
            "resistance_distance_pct": resistance_distance * 100,
            "support_distance_pct": support_distance * 100,
        }

    def _extract_price_levels(self, response_text: str) -> dict[str, float]:
        """Extract price levels from LLM response text.

        Looks for patterns like:
        - Entry: $50000
        - Stop Loss: 48500
        - Take Profit: 55000
        - entry at 50000
        """
        levels = {}

        # Patterns to match
        patterns = {
            "entry": r"entry[:\s]+\$?(\d+(?:\.\d+)?)",
            "stop_loss": r"stop[- ]?loss[:\s]+\$?(\d+(?:\.\d+)?)",
            "take_profit": r"take[- ]?profit[:\s]+\$?(\d+(?:\.\d+)?)",
            "target": r"target[:\s]+\$?(\d+(?:\.\d+)?)",
        }

        text_lower = response_text.lower()
        for key, pattern in patterns.items():
            match = re.search(pattern, text_lower)
            if match:
                try:
                    levels[key] = float(match.group(1))
                except ValueError:
                    continue

        return levels

    def build_prompt(self, request: AIRequest) -> str:
        """Build a TA-focused prompt from candle + indicator data."""
        symbol = request.context.get("symbol", "UNKNOWN")
        timeframe = request.context.get("timeframe", "1h")
        candles = request.context.get("candles", [])
        indicators = request.context.get("indicators", {})

        # Configure candle depth based on timeframe
        candle_depth_map = {
            "1m": 500,
            "5m": 500,
            "15m": 200,
            "1h": 200,
            "4h": 100,
            "1d": 50,
        }
        max_candles = candle_depth_map.get(timeframe, 200)

        # Serialize candles (full OHLCV for tactical analysis)
        serialized_candles = serialize_candles(
            candles, max_candles=max_candles, include_full_data=True
        )

        # Calculate support/resistance
        sr_levels = {}
        if candles:
            sr_levels = self._calculate_support_resistance(candles)

        # Check for multiple timeframes
        multi_tf = request.context.get("multi_timeframe", {})

        prompt_parts = [
            f"Perform technical analysis on {symbol} ({timeframe} timeframe).",
            f"Provided: {len(serialized_candles)} candles of OHLCV data.",
            "",
            "=== PRICE DATA ===",
            json.dumps(serialized_candles[-50:], indent=2),  # Show last 50 for brevity
            "",
            "=== INDICATOR VALUES ===",
            json.dumps(serialize_indicators(indicators), indent=2, default=str),
            "",
        ]

        if sr_levels:
            prompt_parts.extend([
                "=== SUPPORT/RESISTANCE LEVELS ===",
                json.dumps(sr_levels, indent=2),
                "",
            ])

        if multi_tf:
            prompt_parts.extend([
                "=== MULTI-TIMEFRAME CONTEXT ===",
                json.dumps(multi_tf, indent=2, default=str),
                "",
            ])

        prompt_parts.extend([
            request.user_prompt,
            "",
            "RESPONSE FORMAT:",
            "Provide your analysis in JSON format with the following structure:",
            "{",
            '  "action": "BUY" | "SELL" | "NEUTRAL",',
            '  "confidence": 0.0-1.0,',
            '  "reasoning": "detailed technical analysis",',
            '  "entry": <price>,  // Recommended entry price',
            '  "stop_loss": <price>,  // Stop loss level',
            '  "take_profit": <price>,  // Take profit target',
            '  "risk_reward": <ratio>,  // Risk:Reward ratio',
            '  "timeframe_alignment": "STRONG" | "WEAK" | "CONFLICTED",  // Multi-TF check',
            "}",
        ])

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

            # Extract price levels from structured response
            for key in ("entry", "stop_loss", "take_profit", "risk_reward"):
                if key in response.parsed:
                    try:
                        metrics[key] = float(response.parsed[key])
                    except (ValueError, TypeError):
                        continue

        else:
            # Fallback: try to extract levels from raw text
            extracted_levels = self._extract_price_levels(response.raw_text)
            metrics.update(extracted_levels)

        # Calculate risk/reward if we have the levels
        if "entry" in metrics and "stop_loss" in metrics and "take_profit" in metrics:
            entry = metrics["entry"]
            stop = metrics["stop_loss"]
            target = metrics["take_profit"]
            risk = abs(entry - stop)
            reward = abs(target - entry)
            if risk > 0:
                metrics["risk_reward"] = reward / risk

        return RoleVerdict(
            role=RoleName.TACTICAL,
            action=action,
            confidence=confidence,
            reasoning=reasoning,
            metrics=metrics,
        )
