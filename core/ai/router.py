"""LLM Router — dispatches AI requests to roles and collects responses.

The router is the main entry point for the Multi-Brain system.
It orchestrates:
1. Prompt lookup
2. Parallel role evaluation with timeouts
3. Circuit breaker per provider
4. Consensus aggregation
5. Usage tracking and database persistence
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

from core.ai.consensus import ConsensusEngine
from core.ai.prompts.registry import PromptRegistry
from core.ai.roles.base import AgentRole, RoleRegistry
from core.ai.types import (
    AIRequest,
    AIResponse,
    ConsensusDecision,
    ProviderName,
    RoleName,
    RoleVerdict,
    UsageRecord,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Default timeout per role (seconds)
DEFAULT_ROLE_TIMEOUT = 30.0
TACTICAL_TIMEOUT = 60.0  # Tactical needs more time for reasoning

# Circuit breaker configuration
CIRCUIT_FAILURE_THRESHOLD = 5  # Consecutive failures to open circuit
CIRCUIT_COOLDOWN_SECONDS = 300  # 5 minutes
CIRCUIT_HALF_OPEN_LIMIT = 1  # Number of test requests in half-open state


class CircuitState(str, Enum):
    """Circuit breaker state."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Blocking requests (cooldown)
    HALF_OPEN = "half_open"  # Testing recovery


@dataclass
class CircuitBreaker:
    """Circuit breaker for a provider to prevent cascading failures.

    State transitions:
    - CLOSED → OPEN: After N consecutive failures
    - OPEN → HALF_OPEN: After cooldown period
    - HALF_OPEN → CLOSED: After successful request
    - HALF_OPEN → OPEN: After failed request
    """

    provider: ProviderName
    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    last_failure_time: float = 0.0
    half_open_successes: int = 0

    def should_allow_request(self) -> bool:
        """Check if request should be allowed through.

        Note: Under concurrent load, multiple tasks may pass the HALF_OPEN
        check simultaneously before any complete. This is acceptable - the
        limit is a guideline, not a hard gate. The worst case is a few extra
        test requests during recovery.
        """
        if self.state == CircuitState.CLOSED:
            return True

        if self.state == CircuitState.OPEN:
            # Check if cooldown period has elapsed
            if time.monotonic() - self.last_failure_time >= CIRCUIT_COOLDOWN_SECONDS:
                logger.info("Circuit breaker for %s entering HALF_OPEN state", self.provider.value)
                self.state = CircuitState.HALF_OPEN
                self.half_open_successes = 0
                return True
            return False

        # HALF_OPEN: Allow limited requests to test recovery
        # NOTE: This check is not atomic - under concurrency, multiple
        # requests may pass before half_open_successes is incremented.
        # For simplicity, we accept this (a few extra test requests won't
        # hurt). If strict limiting is needed, use an asyncio.Lock.
        return self.half_open_successes < CIRCUIT_HALF_OPEN_LIMIT

    def record_success(self) -> None:
        """Record a successful request."""
        if self.state == CircuitState.HALF_OPEN:
            self.half_open_successes += 1
            if self.half_open_successes >= CIRCUIT_HALF_OPEN_LIMIT:
                logger.info("Circuit breaker for %s closing (recovered)", self.provider.value)
                self.state = CircuitState.CLOSED
                self.failure_count = 0
        elif self.state == CircuitState.CLOSED:
            # Reset failure count on success
            self.failure_count = 0

    def record_failure(self) -> None:
        """Record a failed request."""
        self.failure_count += 1
        self.last_failure_time = time.monotonic()

        if self.state == CircuitState.CLOSED:
            if self.failure_count >= CIRCUIT_FAILURE_THRESHOLD:
                logger.error(
                    "Circuit breaker for %s OPENING after %d consecutive failures",
                    self.provider.value,
                    self.failure_count,
                )
                self.state = CircuitState.OPEN
        elif self.state == CircuitState.HALF_OPEN:
            logger.warning("Circuit breaker for %s reopening (failed during recovery)", self.provider.value)
            self.state = CircuitState.OPEN
            self.half_open_successes = 0


class LLMRouter:
    """Central router for the Multi-Brain agent topology.

    Features:
    - Parallel role evaluation with per-role timeouts
    - Circuit breaker per provider to prevent cascading failures
    - Database persistence for usage tracking
    - Partial evaluation (graceful degradation)

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
        min_roles_required: int = 2,
        enable_circuit_breaker: bool = True,
    ) -> None:
        self.consensus = consensus_engine or ConsensusEngine()
        self.min_roles_required = min_roles_required
        self.enable_circuit_breaker = enable_circuit_breaker
        self._usage_log: list[UsageRecord] = []

        # Circuit breakers per provider (instance-level state)
        # NOTE: Breaker state is stored on this router instance. To persist
        # circuit breaker state across multiple requests, reuse the same
        # router instance (e.g., via singleton or dependency injection).
        self._circuit_breakers: dict[ProviderName, CircuitBreaker] = {}

        # Role-specific timeouts
        self._role_timeouts: dict[RoleName, float] = {
            RoleName.SCREENER: DEFAULT_ROLE_TIMEOUT,
            RoleName.TACTICAL: TACTICAL_TIMEOUT,  # Longer for reasoning models
            RoleName.FUNDAMENTAL: DEFAULT_ROLE_TIMEOUT,
            RoleName.STRATEGIST: DEFAULT_ROLE_TIMEOUT,
        }

    async def evaluate_opportunity(
        self,
        symbol: str,
        timeframe: str,
        candles: list[dict] | None = None,
        indicators: dict | None = None,
        portfolio: dict | None = None,
        risk_limits: dict | None = None,
        roles: list[RoleName] | None = None,
        db_session: AsyncSession | None = None,
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
            db_session: Optional database session for usage logging.

        Returns:
            Aggregated ConsensusDecision from all queried roles.
            Uses partial evaluation if some roles fail/timeout.
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

        # Dispatch to all roles in parallel with timeouts
        tasks = []
        for role in active_roles:
            request = AIRequest(
                role=role.name,
                user_prompt=f"Evaluate {symbol} on {timeframe}.",
                context=context,
            )
            prompt = PromptRegistry.get_active(role.name)
            system_prompt = prompt.content if prompt else ""

            # Wrap evaluation with timeout
            timeout = self._role_timeouts.get(role.name, DEFAULT_ROLE_TIMEOUT)
            tasks.append(self._evaluate_role_with_timeout(role, request, system_prompt, timeout))

        # Track wall-clock time for end-to-end latency (roles run in parallel)
        start_time = time.monotonic()
        results = await asyncio.gather(*tasks, return_exceptions=True)
        wall_clock_ms = (time.monotonic() - start_time) * 1000

        # Collect verdicts and responses (partial evaluation)
        verdicts: list[RoleVerdict] = []
        responses: list[AIResponse] = []
        total_cost = 0.0
        failed_roles = []

        for role, result in zip(active_roles, results):
            # Handle BaseException (includes asyncio.CancelledError in Python 3.12+)
            if isinstance(result, BaseException):
                # Re-raise cancellation/interrupt signals to propagate properly
                if isinstance(result, (asyncio.CancelledError, KeyboardInterrupt, SystemExit)):
                    raise result
                logger.error("Role %s evaluation failed: %s", role.name.value, result)
                failed_roles.append(role.name.value)
                continue

            response, verdict = result
            responses.append(response)

            # Track usage in memory (including error responses for audit trail)
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
                    error=response.error,  # Include error details for audit trail
                )
            )

            # Only include non-error verdicts in consensus
            # Error responses (timeout/exception) return NEUTRAL with conf=0.0
            # but we still want to track them in the decision log
            if response.error is not None:
                logger.info(
                    "Role %s returned error response: %s",
                    role.name.value,
                    response.error,
                )
                failed_roles.append(role.name.value)
            else:
                # Only successful responses contribute to consensus
                verdicts.append(verdict)

            total_cost += response.cost_usd

        # Partial evaluation: check if we have minimum required roles
        if len(verdicts) < self.min_roles_required:
            logger.warning(
                "Only %d/%d roles responded (need %d) — returning low-confidence NEUTRAL",
                len(verdicts),
                len(active_roles),
                self.min_roles_required,
            )
            decision = ConsensusDecision(
                final_action="NEUTRAL",
                final_confidence=0.0,
                verdicts=verdicts,
                reasoning=f"Insufficient roles responded: {len(verdicts)}/{len(active_roles)}. Failed: {', '.join(failed_roles)}",
            )
        else:
            # Run consensus with available verdicts
            decision = self.consensus.aggregate(verdicts)

            # Surface partial evaluation when some roles failed but enough succeeded
            if failed_roles:
                partial_note = f"Partial evaluation: {len(failed_roles)} role(s) failed: {', '.join(failed_roles)}"
                if decision.reasoning:
                    decision.reasoning = decision.reasoning.rstrip() + ". " + partial_note
                else:
                    decision.reasoning = partial_note

        decision.total_cost_usd = total_cost
        decision.total_latency_ms = wall_clock_ms

        logger.info(
            "Multi-Brain decision for %s: %s (confidence=%.2f, %d/%d roles, cost=$%.4f, latency=%.0fms)",
            symbol,
            decision.final_action,
            decision.final_confidence,
            len(verdicts),
            len(active_roles),
            decision.total_cost_usd,
            decision.total_latency_ms,
        )

        # Persist to database if session provided
        if db_session is not None:
            await self._persist_decision(db_session, symbol, timeframe, decision, responses)

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

    async def _evaluate_role_with_timeout(
        self,
        role: AgentRole,
        request: AIRequest,
        system_prompt: str,
        timeout: float,
    ) -> tuple[AIResponse, RoleVerdict]:
        """Evaluate a role with timeout and circuit breaker.

        Returns:
            (response, verdict) tuple on success
            (synthetic error response, NEUTRAL verdict) on timeout/exception/circuit breaker open
        """
        # Check circuit breaker
        provider = role.config.provider
        if self.enable_circuit_breaker:
            breaker = self._get_circuit_breaker(provider)
            if not breaker.should_allow_request():
                logger.warning(
                    "Circuit breaker OPEN for %s, skipping role %s",
                    provider.value,
                    role.name.value,
                )
                # Return synthetic AIResponse for audit trail consistency
                error_response = AIResponse(
                    role=role.name,
                    provider=provider,
                    model=role.config.model,
                    raw_text="",
                    error="circuit breaker open",
                    tokens_in=0,
                    tokens_out=0,
                    cost_usd=0.0,
                    latency_ms=0.0,
                )
                # Return NEUTRAL verdict (circuit breaker skip)
                neutral_verdict = RoleVerdict(
                    role=role.name,
                    action="NEUTRAL",
                    confidence=0.0,
                    reasoning="Circuit breaker OPEN - role skipped",
                )
                return (error_response, neutral_verdict)

        try:
            # Execute with timeout
            result = await asyncio.wait_for(
                self._evaluate_role(role, request, system_prompt),
                timeout=timeout,
            )

            # Record success or failure in circuit breaker based on response.error
            if self.enable_circuit_breaker:
                response, _verdict = result
                if getattr(response, "error", None) is None:
                    breaker.record_success()
                else:
                    breaker.record_failure()

            return result

        except asyncio.TimeoutError:
            logger.error(
                "Role %s timed out after %.1fs",
                role.name.value,
                timeout,
            )
            # Timeout is a failure for circuit breaker
            if self.enable_circuit_breaker:
                breaker.record_failure()

            # Return synthetic AIResponse with error for audit trail
            error_response = AIResponse(
                role=role.name,
                provider=provider,
                model=role.config.model,
                raw_text="",
                error=f"timeout after {timeout}s",
                tokens_in=0,
                tokens_out=0,
                cost_usd=0.0,
                latency_ms=timeout * 1000,
            )
            neutral_verdict = RoleVerdict(
                role=role.name,
                action="NEUTRAL",
                confidence=0.0,
                reasoning=f"Role timed out after {timeout}s",
            )
            return (error_response, neutral_verdict)

        except (asyncio.CancelledError, KeyboardInterrupt, SystemExit):
            # Propagate cancellation/interrupt signals immediately
            raise

        except Exception as exc:
            logger.error("Role %s evaluation failed: %s", role.name.value, exc)
            # Record failure in circuit breaker
            if self.enable_circuit_breaker:
                breaker.record_failure()

            # Return synthetic AIResponse with error details for audit trail
            error_response = AIResponse(
                role=role.name,
                provider=provider,
                model=role.config.model,
                raw_text="",
                error=str(exc),
                tokens_in=0,
                tokens_out=0,
                cost_usd=0.0,
                latency_ms=0.0,
            )
            neutral_verdict = RoleVerdict(
                role=role.name,
                action="NEUTRAL",
                confidence=0.0,
                reasoning=f"Role evaluation failed: {exc}",
            )
            return (error_response, neutral_verdict)

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
            # Let _evaluate_role_with_timeout handle logging to avoid duplicates
            logger.debug("Role %s evaluation failed: %s", role.name.value, exc)
            raise

    def _get_circuit_breaker(self, provider: ProviderName) -> CircuitBreaker:
        """Get or create circuit breaker for provider."""
        if provider not in self._circuit_breakers:
            self._circuit_breakers[provider] = CircuitBreaker(provider=provider)
        return self._circuit_breakers[provider]

    async def _persist_decision(
        self,
        db_session: "AsyncSession",
        symbol: str,
        timeframe: str,
        decision: ConsensusDecision,
        responses: list[AIResponse],
    ) -> None:
        """Persist decision and usage logs to database.

        Uses log_decision_with_usage for atomic transaction.
        """
        try:
            from db.crud.ai import log_decision_with_usage

            # Convert verdicts to dict for JSON storage
            verdicts_dict = [
                {
                    "role": v.role.value,
                    "action": v.action,
                    "confidence": v.confidence,
                    "reasoning": v.reasoning,
                    "metrics": v.metrics,
                }
                for v in decision.verdicts
            ]

            # Convert usage records
            usage_records = [
                {
                    "role": r.role.value,
                    "provider": r.provider.value,
                    "model": r.model,
                    "tokens_in": r.tokens_in,
                    "tokens_out": r.tokens_out,
                    "cost_usd": r.cost_usd,
                    "latency_ms": r.latency_ms,
                    "symbol": symbol,
                    "success": r.error is None,
                    "error": r.error,
                }
                for r in responses
            ]

            await log_decision_with_usage(
                db=db_session,
                symbol=symbol,
                timeframe=timeframe,
                final_action=decision.final_action,
                final_confidence=decision.final_confidence,
                verdicts=verdicts_dict,
                reasoning=decision.reasoning,
                vetoed_by=decision.vetoed_by.value if decision.vetoed_by else None,
                total_cost_usd=decision.total_cost_usd,
                total_latency_ms=decision.total_latency_ms,
                usage_records=usage_records,
            )

            logger.debug("Persisted decision and %d usage records to database", len(usage_records))

        except Exception as exc:
            logger.error("Failed to persist decision to database: %s", exc)
            # Don't raise - database errors shouldn't block trading decisions

    def get_circuit_breaker_status(self) -> dict[str, dict]:
        """Get status of all circuit breakers.

        Returns:
            Dict mapping provider name to status dict with keys:
            state, failure_count, last_failure_time
        """
        return {
            provider.value: {
                "state": breaker.state.value,
                "failure_count": breaker.failure_count,
                "last_failure_time": breaker.last_failure_time,
            }
            for provider, breaker in self._circuit_breakers.items()
        }

    def reset_circuit_breaker(self, provider: ProviderName) -> None:
        """Manually reset a circuit breaker (admin operation)."""
        if provider in self._circuit_breakers:
            breaker = self._circuit_breakers[provider]
            breaker.state = CircuitState.CLOSED
            breaker.failure_count = 0
            breaker.last_failure_time = 0.0
            breaker.half_open_successes = 0
            logger.info("Circuit breaker for %s manually reset", provider.value)
