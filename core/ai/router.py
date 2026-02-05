"""LLM Router — dispatches AI requests to roles and collects responses.

The router is the main entry point for the Multi-Brain system.
It orchestrates:
1. Prompt lookup
2. Parallel role evaluation
3. Consensus aggregation
4. Usage tracking
"""

from __future__ import annotations

import asyncio
import logging

from core.ai.consensus import ConsensusEngine
from core.ai.prompts.registry import PromptRegistry
from core.ai.roles.base import AgentRole, RoleRegistry
from core.ai.types import (
    AIRequest,
    AIResponse,
    ConsensusDecision,
    RoleName,
    RoleVerdict,
    UsageRecord,
)

logger = logging.getLogger(__name__)


class LLMRouter:
    """Central router for the Multi-Brain agent topology.

    Usage::

        router = LLMRouter()
        decision = await router.evaluate_opportunity(
            symbol="BTC/USD",
            timeframe="1h",
            candles=candle_data,
            indicators=indicator_data,
        )

        if decision.final_action == "BUY":
            # proceed to execution
            ...
    """

    def __init__(
        self,
        consensus_engine: ConsensusEngine | None = None,
    ) -> None:
        self.consensus = consensus_engine or ConsensusEngine()
        self._usage_log: list[UsageRecord] = []

    async def evaluate_opportunity(
        self,
        symbol: str,
        timeframe: str,
        candles: list[dict] | None = None,
        indicators: dict | None = None,
        portfolio: dict | None = None,
        risk_limits: dict | None = None,
        roles: list[RoleName] | None = None,
    ) -> ConsensusDecision:
        """Run the full Multi-Brain evaluation pipeline.

        Args:
            symbol: Trading pair (e.g. "BTC/USD").
            timeframe: Candle timeframe (e.g. "1h").
            candles: OHLCV candle data.
            indicators: Computed indicator values.
            portfolio: Current portfolio state (for strategist).
            risk_limits: Risk parameters (for strategist).
            roles: Specific roles to query (default: all active).

        Returns:
            Aggregated ConsensusDecision from all queried roles.
        """
        active_roles = self._resolve_roles(roles)
        if not active_roles:
            logger.warning("No active roles configured — returning NEUTRAL")
            return ConsensusDecision(
                final_action="NEUTRAL",
                final_confidence=0.0,
                reasoning="No AI roles configured.",
            )

        # Build shared context
        context = {
            "symbol": symbol,
            "timeframe": timeframe,
            "candles": candles or [],
            "indicators": indicators or {},
            "portfolio": portfolio or {},
            "risk_limits": risk_limits or {},
        }

        # Dispatch to all roles in parallel
        tasks = []
        for role in active_roles:
            request = AIRequest(
                role=role.name,
                user_prompt=f"Evaluate {symbol} on {timeframe}.",
                context=context,
            )
            prompt = PromptRegistry.get_active(role.name)
            system_prompt = prompt.content if prompt else ""
            tasks.append(self._evaluate_role(role, request, system_prompt))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Collect successful verdicts
        verdicts: list[RoleVerdict] = []
        responses: list[AIResponse] = []
        total_cost = 0.0
        total_latency = 0.0

        for result in results:
            if isinstance(result, Exception):
                logger.error("Role evaluation failed: %s", result)
                continue
            response, verdict = result
            responses.append(response)
            verdicts.append(verdict)
            total_cost += response.cost_usd
            total_latency += response.latency_ms

            # Track usage
            self._usage_log.append(
                UsageRecord(
                    role=response.role,
                    provider=response.provider,
                    model=response.model,
                    tokens_in=response.tokens_in,
                    tokens_out=response.tokens_out,
                    cost_usd=response.cost_usd,
                    latency_ms=response.latency_ms,
                    symbol=symbol,
                    success=response.error is None,
                )
            )

        # Run consensus
        decision = self.consensus.aggregate(verdicts)
        decision.total_cost_usd = total_cost
        decision.total_latency_ms = total_latency

        logger.info(
            "Multi-Brain decision for %s: %s (confidence=%.2f, cost=$%.4f, latency=%.0fms)",
            symbol,
            decision.final_action,
            decision.final_confidence,
            decision.total_cost_usd,
            decision.total_latency_ms,
        )

        return decision

    async def evaluate_single_role(
        self,
        role_name: RoleName,
        symbol: str,
        timeframe: str,
        context: dict | None = None,
    ) -> tuple[AIResponse, RoleVerdict]:
        """Evaluate a single role (for testing / debugging)."""
        role = RoleRegistry.get(role_name)
        if role is None:
            raise ValueError(f"Role {role_name.value} not registered")

        request = AIRequest(
            role=role_name,
            user_prompt=f"Evaluate {symbol} on {timeframe}.",
            context=context or {"symbol": symbol, "timeframe": timeframe},
        )
        prompt = PromptRegistry.get_active(role_name)
        system_prompt = prompt.content if prompt else ""
        return await self._evaluate_role(role, request, system_prompt)

    def get_usage_log(self) -> list[UsageRecord]:
        """Return the usage log (for cost monitoring)."""
        return list(self._usage_log)

    def clear_usage_log(self) -> None:
        """Clear the in-memory usage log."""
        self._usage_log.clear()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _resolve_roles(self, names: list[RoleName] | None) -> list[AgentRole]:
        """Resolve role names to registered role instances."""
        if names:
            return [r for r in (RoleRegistry.get(n) for n in names) if r is not None and r.config.enabled]
        return RoleRegistry.active_roles()

    async def _evaluate_role(
        self,
        role: AgentRole,
        request: AIRequest,
        system_prompt: str,
    ) -> tuple[AIResponse, RoleVerdict]:
        """Evaluate a single role with error handling."""
        try:
            return await role.evaluate(request, system_prompt)
        except Exception as exc:
            logger.error("Role %s evaluation failed: %s", role.name.value, exc)
            raise
