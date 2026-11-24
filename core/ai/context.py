"""Authoritative evaluation context for Multi-Brain decisions (issue #432).

The AI contract always accepted ``candles`` / ``indicators`` / ``portfolio`` /
``risk_limits``, but nothing assembled them, so the evaluation panel drove the
whole pipeline with a symbol and a timeframe. Role output could then look
actionable while carrying no market structure, holdings, exposure or risk
limits. Confidence is not evidence.

This module turns "whatever the caller happened to attach" into a versioned,
timestamped snapshot with an explicit verdict on whether that snapshot may
produce an executable recommendation. It is deliberately pure: the transport
layer (``api/routes/ai.py``) fetches the data from the authoritative sources
and hands it in, which keeps this logic testable without a database.

Two failure tiers, because "no market data" and "no risk limits" are not the
same problem:

``blocking``
    The market series is absent or stale. There is nothing to reason about, so
    the evaluation must not run at all: neutral, zero confidence, no provider
    call, no cost.
``degraded``
    The market series is usable but the portfolio and/or risk limits are
    absent or stale. Roles may still be queried for information, but the
    consensus may not become executable: the caller clamps the final action to
    ``NEUTRAL``.

Either way an executable (``BUY``/``SELL``) recommendation is impossible
without current, timestamped evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

CONTEXT_VERSION = 2
"""Snapshot schema version. Version 1 was :mod:`core.ai.router`'s implicit
"whatever the caller sent" dictionary."""

DEFAULT_MAX_CONTEXT_AGE_SECONDS = 3600.0
"""Default freshness budget for every context input, in seconds."""

CLOCK_SKEW_TOLERANCE_SECONDS = 60.0
"""A timestamp this far in the future is treated as unusable evidence."""


@dataclass(frozen=True)
class ContextInput:
    """One input of an evaluation snapshot, with its provenance.

    Attributes:
        name: Input name (``candles``, ``portfolio``, ``risk_limits``, ...).
        provided: Whether any payload was supplied at all.
        as_of: Authoritative timestamp of the payload, if known.
        age_seconds: Age of the payload at snapshot time, if computable.
        missing_reason: Why the input is unusable, or ``None``.
        required: Whether the evaluation may proceed without it.
    """

    name: str
    provided: bool
    as_of: datetime | None = None
    age_seconds: float | None = None
    missing_reason: str | None = None
    required: bool = True

    @property
    def usable(self) -> bool:
        """Whether the input carries current, timestamped evidence."""
        return self.provided and self.missing_reason is None

    def to_dict(self) -> dict[str, Any]:
        """Serialize the provenance for the HTTP response."""
        return {
            "name": self.name,
            "provided": self.provided,
            "required": self.required,
            "usable": self.usable,
            "as_of": self.as_of.isoformat() if self.as_of else None,
            "age_seconds": round(self.age_seconds, 3) if self.age_seconds is not None else None,
            "missing_reason": self.missing_reason,
        }


@dataclass(frozen=True)
class EvaluationContext:
    """Versioned snapshot of the evidence an evaluation was built from."""

    version: int
    built_at: datetime
    max_age_seconds: float
    inputs: tuple[ContextInput, ...]
    candles: tuple[Mapping[str, Any], ...]
    indicators: Mapping[str, Any]
    portfolio: Mapping[str, Any]
    risk_limits: Mapping[str, Any]
    market_symbol: str = ""
    exchange: str = ""

    @property
    def blocking_inputs(self) -> list[ContextInput]:
        """Inputs whose absence or staleness forbids running the evaluation."""
        return [item for item in self.inputs if item.name == "candles" and not item.usable]

    @property
    def degraded_inputs(self) -> list[ContextInput]:
        """Inputs whose absence only forbids an *executable* decision."""
        return [item for item in self.inputs if item.name != "candles" and not item.usable]

    @property
    def missing(self) -> list[str]:
        """Names of inputs that were not supplied at all."""
        return [item.name for item in self.inputs if item.provided is False]

    @property
    def stale(self) -> list[str]:
        """Names of supplied inputs that are too old (or undated) to trust."""
        return [item.name for item in self.inputs if item.provided and item.missing_reason]

    @property
    def can_run(self) -> bool:
        """Whether the roles may be queried at all."""
        return not self.blocking_inputs

    @property
    def executable_ready(self) -> bool:
        """Whether the consensus may yield an executable recommendation."""
        return self.can_run and not self.degraded_inputs

    @property
    def abstain_reasons(self) -> list[str]:
        """Human-readable reasons the snapshot is not executable."""
        reasons = [f"{item.name}: {item.missing_reason}" for item in self.blocking_inputs]
        reasons.extend(f"{item.name}: {item.missing_reason}" for item in self.degraded_inputs)
        return reasons

    @property
    def data_age_seconds(self) -> float:
        """Age of the oldest usable input, in seconds (0.0 when unknown)."""
        ages = [item.age_seconds for item in self.inputs if item.usable and item.age_seconds is not None]
        return max(ages) if ages else 0.0

    def to_dict(self) -> dict[str, Any]:
        """Serialize the snapshot for the HTTP response and the audit trail."""
        return {
            "version": self.version,
            "built_at": self.built_at.isoformat(),
            "max_age_seconds": self.max_age_seconds,
            "market_symbol": self.market_symbol,
            "exchange": self.exchange,
            "data_age_seconds": round(self.data_age_seconds, 3),
            "can_run": self.can_run,
            "executable_ready": self.executable_ready,
            "missing": self.missing,
            "stale": self.stale,
            "inputs": [item.to_dict() for item in self.inputs],
        }


def _describe_age(as_of: datetime | None, now: datetime) -> tuple[float | None, str | None]:
    """Return ``(age_seconds, reason_if_unusable_timestamp)``."""
    if as_of is None:
        return None, None
    age = (now - as_of).total_seconds()
    if age < -CLOCK_SKEW_TOLERANCE_SECONDS:
        return age, f"timestamp is {-age:.0f}s in the future"
    return age, None


def _make_input(
    *,
    name: str,
    payload: Any,
    as_of: datetime | None,
    now: datetime,
    max_age_seconds: float,
    empty_reason: str,
    required: bool = True,
    timestamp_required: bool = True,
) -> ContextInput:
    """Classify one input as usable, missing or stale.

    ``timestamp_required=False`` is for configuration (risk limits): it carries
    no observation time, so its presence is what matters, not its age.
    """
    provided = _has_payload(payload)
    age, reason = _describe_age(as_of, now)

    if not provided:
        return ContextInput(
            name=name,
            provided=False,
            as_of=as_of,
            age_seconds=age,
            missing_reason=empty_reason,
            required=required,
        )
    if timestamp_required and reason is None and age is None:
        reason = "no authoritative timestamp, freshness cannot be verified"
    elif timestamp_required and reason is None and age is not None and age > max_age_seconds:
        reason = f"stale: {age:.0f}s old (limit {max_age_seconds:.0f}s)"

    return ContextInput(
        name=name,
        provided=True,
        as_of=as_of,
        age_seconds=age,
        missing_reason=reason,
        required=required,
    )


def _has_payload(payload: Any) -> bool:
    """Whether a payload carries anything at all."""
    if payload is None:
        return False
    if isinstance(payload, (str, bytes)):
        return bool(payload.strip())
    try:
        return len(payload) > 0
    except TypeError:  # pragma: no cover - defensive, scalars carry no evidence
        return True


def build_evaluation_context(
    *,
    symbol: str,
    timeframe: str,
    exchange: str = "bitfinex",
    now: datetime | None = None,
    max_age_seconds: float = DEFAULT_MAX_CONTEXT_AGE_SECONDS,
    candles: Sequence[Mapping[str, Any]] | None = None,
    candles_as_of: datetime | None = None,
    indicators: Mapping[str, Any] | None = None,
    portfolio: Mapping[str, Any] | None = None,
    portfolio_as_of: datetime | None = None,
    risk_limits: Mapping[str, Any] | None = None,
    risk_limits_as_of: datetime | None = None,
    market_symbol: str | None = None,
) -> EvaluationContext:
    """Assemble the snapshot the Multi-Brain pipeline is allowed to reason from.

    Only the market series is blocking: without candles there is nothing to
    evaluate, so the caller must not query the providers. A missing portfolio
    or risk limits keep the roles queryable but forbid an executable verdict.

    Args:
        symbol: Symbol as requested by the caller (``BTC/USD``).
        timeframe: Candle timeframe (``1h``).
        exchange: Exchange the market data came from.
        now: Snapshot time; defaults to ``datetime.now(timezone.utc)``.
        max_age_seconds: Freshness budget applied to every input.
        candles: Closed candles, oldest first.
        candles_as_of: Close time of the last closed candle.
        indicators: Pre-computed indicator values (optional, derived from candles).
        portfolio: Holdings / exposure payload.
        portfolio_as_of: Timestamp of that payload.
        risk_limits: Risk limits payload.
        risk_limits_as_of: Timestamp of those limits.
        market_symbol: Symbol as stored in the candle store, when it differs.

    Returns:
        An :class:`EvaluationContext` describing exactly what may be claimed.
    """
    if now is None:
        now = datetime.now(timezone.utc)

    store_symbol = market_symbol or symbol
    inputs = (
        _make_input(
            name="candles",
            payload=candles,
            as_of=candles_as_of,
            now=now,
            max_age_seconds=max_age_seconds,
            empty_reason=f"no closed candles for {store_symbol} on {exchange}/{timeframe}",
        ),
        _make_input(
            name="portfolio",
            payload=portfolio,
            as_of=portfolio_as_of,
            now=now,
            max_age_seconds=max_age_seconds,
            empty_reason="no portfolio snapshot available",
        ),
        _make_input(
            name="risk_limits",
            payload=risk_limits,
            as_of=risk_limits_as_of,
            now=now,
            max_age_seconds=max_age_seconds,
            empty_reason="no risk limits supplied",
            timestamp_required=False,
        ),
    )

    return EvaluationContext(
        version=CONTEXT_VERSION,
        built_at=now,
        max_age_seconds=max_age_seconds,
        inputs=inputs,
        candles=tuple(candles or ()),
        indicators=dict(indicators or {}),
        portfolio=dict(portfolio or {}),
        risk_limits=dict(risk_limits or {}),
        market_symbol=store_symbol,
        exchange=exchange,
    )
