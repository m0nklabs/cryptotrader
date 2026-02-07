"""Screener role — high-throughput bulk filtering.

Default provider: DeepSeek V3.2 (cheapest, fast)
Purpose: Quickly scan many symbols and discard obvious no-trades.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from core.ai.roles.base import AgentRole, serialize_indicators
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

    Features:
    - Quick-reject heuristics before LLM call (save costs)
    - Batch processing of multiple symbols
    - Indicator snapshot injection (RSI, MACD, volume, Bollinger Bands)
    - Output: STRONG_BUY / BUY / NEUTRAL / SKIP per symbol
    """

    def __init__(self, config: RoleConfig | None = None) -> None:
        super().__init__(config or DEFAULT_SCREENER_CONFIG)

    def _quick_reject(self, symbol: str, indicators: dict[str, Any]) -> tuple[bool, str]:
        """Apply quick-reject heuristics to filter obvious no-trades.

        Returns:
            Tuple of (should_reject, reason)
        """
        # Low volume filter
        volume = indicators.get("volume_24h", 0)
        if volume < 100000:  # Less than $100k daily volume
            return True, f"Low volume: ${volume:,.0f}"

        # Extreme RSI check
        rsi = indicators.get("rsi", 50)
        if rsi > 95:  # Extremely overbought
            return True, f"Extremely overbought: RSI {rsi:.1f}"
        if rsi < 5:  # Extremely oversold (might be dead coin)
            return True, f"Extremely oversold: RSI {rsi:.1f}"

        # Bollinger Band width check (very tight = low volatility)
        bb_upper = indicators.get("bb_upper")
        bb_lower = indicators.get("bb_lower")
        bb_middle = indicators.get("bb_middle")
        if bb_upper and bb_lower and bb_middle:
            bb_width = (bb_upper - bb_lower) / bb_middle if bb_middle > 0 else 0
            if bb_width < 0.01:  # Less than 1% width
                return True, f"Very low volatility: BB width {bb_width:.3%}"

        return False, ""

    def build_prompt(self, request: AIRequest) -> str:
        """Build a screening prompt from the request context.

        Supports batch processing and includes pre-filtered results.
        """
        # Context should contain: symbols, indicators, timeframe
        symbols = request.context.get("symbols", [])
        timeframe = request.context.get("timeframe", "1h")
        indicators_by_symbol = request.context.get("indicators", {})

        # Apply quick-reject heuristics
        filtered_symbols = []
        rejected_symbols = []

        for symbol in symbols:
            symbol_indicators = indicators_by_symbol.get(symbol, {})
            should_reject, reason = self._quick_reject(symbol, symbol_indicators)
            if should_reject:
                rejected_symbols.append({"symbol": symbol, "reason": reason})
            else:
                filtered_symbols.append(symbol)

        # Build prompt with filtered data
        prompt_parts = [
            f"Screen {len(filtered_symbols)} symbols on {timeframe} timeframe.",
            f"({len(rejected_symbols)} symbols pre-filtered for low volume/volatility)",
            "",
        ]

        if filtered_symbols:
            prompt_parts.extend(
                [
                    "Symbols to analyze:",
                    json.dumps(filtered_symbols, indent=2),
                    "",
                    "Indicator snapshots:",
                    json.dumps(
                        {sym: serialize_indicators(indicators_by_symbol.get(sym, {})) for sym in filtered_symbols},
                        indent=2,
                        default=str,
                    ),
                    "",
                ]
            )

        if rejected_symbols:
            prompt_parts.extend(
                [
                    "Pre-rejected symbols (for context only):",
                    json.dumps(rejected_symbols, indent=2),
                    "",
                ]
            )

        prompt_parts.extend(
            [
                request.user_prompt,
                "",
                "Return a JSON response with the following structure:",
                "{",
                '  "action": "BUY" | "SELL" | "NEUTRAL",',
                '  "confidence": 0.0-1.0,',
                '  "reasoning": "brief explanation",',
                '  "passed_symbols": ["SYMBOL1", "SYMBOL2", ...],',
                '  "skipped_symbols": ["SYMBOLX", "SYMBOLY", ...],',
                "}",
            ]
        )

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
        metrics: dict[str, float] = {}

        if response.parsed and isinstance(response.parsed, dict):
            action = response.parsed.get("action", "NEUTRAL")
            # Map invalid SKIP action to NEUTRAL (SKIP is not a valid SignalAction)
            if action == "SKIP":
                action = "NEUTRAL"
            confidence = float(response.parsed.get("confidence", 0.5))
            reasoning = response.parsed.get("reasoning", response.raw_text)

            # Extract filtered symbol counts (accept both key sets for compatibility)
            filtered = response.parsed.get("passed_symbols") or response.parsed.get("filtered_symbols", [])
            skipped = response.parsed.get("skipped_symbols", [])
            strong_buy = response.parsed.get("strong_buy_symbols", [])
            metrics = {
                "symbols_passed": float(len(filtered)),
                "symbols_skipped": float(len(skipped)),
                "strong_buy_count": float(len(strong_buy)),
            }

        return RoleVerdict(
            role=RoleName.SCREENER,
            action=action,
            confidence=confidence,
            reasoning=reasoning,
            metrics=metrics,
        )
