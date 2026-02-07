"""Strategist role — portfolio-level risk management and veto power.

Default provider: o3-mini (strong reasoning, moderate cost)
Purpose: Evaluate proposed trades against portfolio exposure, risk
limits, correlation, and provide go/no-go + position sizing.
"""

from __future__ import annotations

import json
import logging

from core.ai.roles.base import (
    AgentRole,
    calculate_position_size_kelly,
    calculate_risk_metrics,
    format_portfolio_state,
)
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

    Features:
    - Portfolio state injection (current positions, exposure, P&L)
    - Position sizing calculations (Kelly criterion or fixed fraction)
    - Risk assessment against portfolio limits
    - VETO logic: automatic REJECT if risk thresholds exceeded
    - Correlation check with existing positions
    """

    def __init__(self, config: RoleConfig | None = None) -> None:
        super().__init__(config or DEFAULT_STRATEGIST_CONFIG)

    def _check_risk_limits(
        self,
        proposed_trade: dict,
        portfolio_state: dict,
        risk_limits: dict,
    ) -> tuple[bool, str]:
        """Check if proposed trade violates risk limits.

        Returns:
            Tuple of (should_veto, reason)
        """
        total_equity = portfolio_state.get("total_equity", 0)
        total_exposure = portfolio_state.get("total_exposure", 0)
        num_positions = portfolio_state.get("num_positions", 0)

        # Max positions check
        max_positions = risk_limits.get("max_positions", 10)
        if num_positions >= max_positions:
            return True, f"Max positions limit reached: {num_positions}/{max_positions}"

        # Max exposure check
        max_exposure_pct = risk_limits.get("max_exposure_pct", 0.95)
        if total_equity > 0:
            exposure_pct = total_exposure / total_equity
            if exposure_pct >= max_exposure_pct:
                return True, f"Max portfolio exposure: {exposure_pct:.1%} >= {max_exposure_pct:.1%}"

        # Per-trade risk check
        proposed_size = proposed_trade.get("size", 0)
        entry_price = proposed_trade.get("entry_price", 0)
        stop_loss = proposed_trade.get("stop_loss", 0)

        if proposed_size > 0 and entry_price > 0 and stop_loss > 0:
            max_risk_per_trade = risk_limits.get("max_risk_per_trade_pct", 0.02)
            risk_metrics = calculate_risk_metrics(
                proposed_size,
                entry_price,
                stop_loss,
                total_equity,
                max_risk_per_trade,
            )

            if risk_metrics["exceeds_limit"]:
                return (
                    True,
                    f"Trade risk {risk_metrics['risk_pct']:.2%} exceeds limit {max_risk_per_trade:.2%}",
                )

        return False, ""

    def _calculate_correlation_penalty(self, proposed_symbol: str, existing_positions: list[dict]) -> float:
        """Calculate correlation penalty for proposed trade.

        Note: This is a simplified correlation check based on base asset matching.
        It does not account for quote currency correlation or more sophisticated
        correlation metrics. Future improvements could include actual price
        correlation analysis or sector-based grouping.

        Returns:
            Correlation score 0.0-1.0 (1.0 = high correlation risk)
        """
        if not existing_positions:
            return 0.0

        # Simple heuristic: check for same base asset
        # Example: BTC/USD + BTC/EUR = high correlation
        proposed_base = proposed_symbol.split("/")[0] if "/" in proposed_symbol else proposed_symbol

        correlated_count = 0
        for pos in existing_positions:
            pos_symbol = pos.get("symbol", "")
            pos_base = pos_symbol.split("/")[0] if "/" in pos_symbol else pos_symbol
            if pos_base.upper() == proposed_base.upper():
                correlated_count += 1

        # Normalize: more correlated positions = higher penalty
        max_correlated = 3  # Allow up to 3 correlated positions
        return min(1.0, correlated_count / max_correlated)

    def _suggest_position_size(
        self,
        proposed_trade: dict,
        portfolio_state: dict,
        risk_limits: dict,
    ) -> dict[str, float]:
        """Suggest position size based on portfolio and risk parameters.

        Returns:
            Dictionary with position sizing recommendations
        """
        total_equity = portfolio_state.get("total_equity", 1.0)
        available_balance = portfolio_state.get("available_balance", 0)

        # Kelly criterion parameters (could be from backtests)
        win_rate = risk_limits.get("historical_win_rate", 0.55)
        avg_win = risk_limits.get("avg_win_pct", 0.05)
        avg_loss = risk_limits.get("avg_loss_pct", 0.02)

        kelly_fraction = calculate_position_size_kelly(win_rate, avg_win, avg_loss, max_kelly_fraction=0.25)

        # Fixed fraction fallback
        fixed_fraction = risk_limits.get("fixed_position_size_pct", 0.1)

        # Use more conservative of the two
        recommended_fraction = min(kelly_fraction, fixed_fraction)

        # Cap by available balance
        max_notional_by_balance = available_balance * 0.95  # Leave 5% buffer
        recommended_notional = total_equity * recommended_fraction

        entry_price = proposed_trade.get("entry_price", 0)
        if entry_price > 0:
            recommended_size = min(
                recommended_notional / entry_price,
                max_notional_by_balance / entry_price,
            )
        else:
            recommended_size = 0

        return {
            "kelly_fraction": kelly_fraction,
            "fixed_fraction": fixed_fraction,
            "recommended_fraction": recommended_fraction,
            "recommended_notional": recommended_notional,
            "recommended_size": recommended_size,
            "max_by_balance": max_notional_by_balance,
        }

    def build_prompt(self, request: AIRequest) -> str:
        """Build a risk-focused prompt with portfolio context.

        NOTE: If hard risk limits are violated, this stores the veto
        state so that parse_response() can enforce it regardless of
        what the LLM returns. See `_hard_veto_reason`.
        """
        symbol = request.context.get("symbol", "UNKNOWN")
        proposed_action = request.context.get("proposed_action", "UNKNOWN")
        proposed_trade = request.context.get("proposed_trade", {})
        positions = request.context.get("positions", [])
        portfolio_metrics = request.context.get("portfolio", {})
        risk_limits = request.context.get("risk_limits", {})

        # Format portfolio state
        total_equity = float(portfolio_metrics.get("total_equity", 0))
        available_balance = float(portfolio_metrics.get("available_balance", 0))
        portfolio_state = format_portfolio_state(positions, total_equity, available_balance)

        # Check hard risk limits — store for enforcement in parse_response()
        should_veto, veto_reason = self._check_risk_limits(proposed_trade, portfolio_state, risk_limits)
        self._hard_veto_reason: str | None = veto_reason if should_veto else None

        # Calculate correlation risk
        correlation_score = self._calculate_correlation_penalty(symbol, positions)

        # Suggest position size
        sizing_suggestion = self._suggest_position_size(proposed_trade, portfolio_state, risk_limits)

        prompt_parts = [
            f"Evaluate proposed {proposed_action} on {symbol}.",
            "",
        ]

        if should_veto:
            prompt_parts.extend(
                [
                    "=== AUTOMATIC VETO ===",
                    f"REASON: {veto_reason}",
                    "This trade violates hard risk limits and must be rejected.",
                    "",
                ]
            )

        prompt_parts.extend(
            [
                "=== CURRENT PORTFOLIO STATE ===",
                json.dumps(portfolio_state, indent=2, default=str),
                "",
                "=== PROPOSED TRADE ===",
                json.dumps(proposed_trade, indent=2, default=str),
                "",
                "=== RISK LIMITS ===",
                json.dumps(risk_limits, indent=2, default=str),
                "",
                "=== CORRELATION ANALYSIS ===",
                json.dumps(
                    {
                        "correlation_score": correlation_score,
                        "risk_level": "HIGH"
                        if correlation_score > 0.7
                        else "MODERATE"
                        if correlation_score > 0.3
                        else "LOW",
                    },
                    indent=2,
                ),
                "",
                "=== POSITION SIZING RECOMMENDATION ===",
                json.dumps(sizing_suggestion, indent=2, default=str),
                "",
                request.user_prompt,
                "",
                "RESPONSE FORMAT:",
                "Provide your analysis in JSON format with the following structure:",
                "{",
                '  "action": "BUY" | "SELL" | "NEUTRAL" | "VETO",',
                '  "confidence": 0.0-1.0,',
                '  "reasoning": "detailed risk analysis",',
                '  "position_size_pct": 0.0-1.0,  // Recommended position size as % of equity',
                '  "portfolio_risk_pct": 0.0-1.0,  // Estimated portfolio risk after trade',
                '  "correlation_score": 0.0-1.0,  // Correlation with existing positions',
                '  "veto_reason": "..." // Required if action is VETO',
                "}",
            ]
        )

        # If we already determined a veto, note it
        if should_veto:
            prompt_parts.extend(
                [
                    "",
                    'NOTE: action MUST be "VETO" due to hard risk limit violation.',
                ]
            )

        return "\n".join(prompt_parts)

    def parse_response(self, response: AIResponse) -> RoleVerdict:
        """Parse strategist response — can VETO trades.

        If build_prompt() detected a hard risk-limit breach, this method
        enforces a VETO regardless of LLM output (the LLM may hallucinate
        an approval even when told to VETO).
        """
        # Enforce hard VETO from risk-limit check (set by build_prompt)
        hard_veto = getattr(self, "_hard_veto_reason", None)
        if hard_veto:
            self._hard_veto_reason = None  # reset for next call
            return RoleVerdict(
                role=RoleName.STRATEGIST,
                action="VETO",
                confidence=1.0,
                reasoning=f"Hard risk limit breach: {hard_veto}",
                metrics={},
            )

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

            # Extract risk metrics — handle both 0-1 and 0-100 scales
            # (system prompt strategist_v1 uses 0-100, prompt template uses 0-1)
            for key in ("position_size_pct", "portfolio_risk_pct", "correlation_score"):
                if key in response.parsed:
                    try:
                        value = float(response.parsed[key])
                        # Auto-detect 0-100 scale and convert to 0-1
                        if key != "correlation_score" and value > 1.0:
                            value = value / 100.0
                        # Clamp to valid range
                        value = max(0.0, min(1.0, value))
                        metrics[key] = value
                    except (ValueError, TypeError):
                        continue

        return RoleVerdict(
            role=RoleName.STRATEGIST,
            action=action,
            confidence=confidence,
            reasoning=reasoning,
            metrics=metrics,
        )
