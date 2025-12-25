"""Audit logging for automation engine.

Provides structured event format for logging all automation decisions,
rule violations, and rejections with full context for replay and debugging.

All timestamps use timezone-aware UTC datetimes for consistency.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal, Optional


EventType = Literal[
    "decision",
    "safety_check",
    "rule_violation",
    "trade_executed",
    "trade_rejected",
    "kill_switch",
    "error",
]

Severity = Literal["debug", "info", "warning", "error"]


@dataclass
class AuditEvent:
    """Structured audit event for automation decisions and actions."""

    event_type: EventType
    message: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    severity: Severity = "info"
    context: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dictionary."""
        result = asdict(self)
        # Convert datetime to ISO format string
        result["timestamp"] = self.timestamp.isoformat()
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AuditEvent:
        """Create from dictionary."""
        # Convert timestamp string back to datetime
        timestamp_value = data.get("timestamp")
        if isinstance(timestamp_value, str):
            ts = timestamp_value
            # Normalize common ISO 8601 variant with trailing 'Z' (UTC)
            if ts.endswith("Z"):
                ts = ts[:-1] + "+00:00"
            try:
                data["timestamp"] = datetime.fromisoformat(ts)
            except ValueError:
                # On parse failure, fall back to default by removing invalid value
                data.pop("timestamp", None)
        return cls(**data)


class AuditLogger:
    """In-memory audit logger for automation events."""

    def __init__(self) -> None:
        self.events: list[AuditEvent] = []

    def log(self, event: AuditEvent) -> None:
        """Log an audit event."""
        self.events.append(event)

    def log_decision(
        self,
        decision: str,
        reason: str,
        symbol: str,
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        """Log a policy decision."""
        event = AuditEvent(
            event_type="decision",
            message=f"Decision '{decision}' for {symbol}: {reason}",
            severity="info",
            context={"decision": decision, "symbol": symbol, "reason": reason, **(context or {})},
        )
        self.log(event)

    def log_safety_check(
        self,
        check_name: str,
        passed: bool,
        reason: str,
        symbol: str,
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        """Log a safety check result."""
        severity: Severity = "info" if passed else "warning"
        event = AuditEvent(
            event_type="safety_check",
            message=f"Safety check '{check_name}' for {symbol}: {'PASS' if passed else 'FAIL'} - {reason}",
            severity=severity,
            context={
                "check_name": check_name,
                "passed": passed,
                "symbol": symbol,
                "reason": reason,
                **(context or {}),
            },
        )
        self.log(event)

    def log_rule_violation(
        self,
        rule_name: str,
        violation: str,
        symbol: str,
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        """Log a rule violation."""
        event = AuditEvent(
            event_type="rule_violation",
            message=f"Rule violation '{rule_name}' for {symbol}: {violation}",
            severity="warning",
            context={"rule_name": rule_name, "symbol": symbol, "violation": violation, **(context or {})},
        )
        self.log(event)

    def log_trade_executed(
        self,
        symbol: str,
        side: str,
        amount: str,
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        """Log a trade execution (dry-run or live)."""
        event = AuditEvent(
            event_type="trade_executed",
            message=f"Trade executed: {side} {amount} {symbol}",
            severity="info",
            context={"symbol": symbol, "side": side, "amount": amount, **(context or {})},
        )
        self.log(event)

    def log_trade_rejected(
        self,
        symbol: str,
        reason: str,
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        """Log a trade rejection."""
        event = AuditEvent(
            event_type="trade_rejected",
            message=f"Trade rejected for {symbol}: {reason}",
            severity="warning",
            context={"symbol": symbol, "reason": reason, **(context or {})},
        )
        self.log(event)

    def log_kill_switch(self, reason: str, context: Optional[dict[str, Any]] = None) -> None:
        """Log kill switch activation."""
        event = AuditEvent(
            event_type="kill_switch",
            message=f"Kill switch activated: {reason}",
            severity="error",
            context={"reason": reason, **(context or {})},
        )
        self.log(event)

    def log_error(self, error_message: str, context: Optional[dict[str, Any]] = None) -> None:
        """Log an error."""
        event = AuditEvent(
            event_type="error",
            message=error_message,
            severity="error",
            context=context or {},
        )
        self.log(event)

    def get_events(
        self,
        event_type: Optional[EventType] = None,
        severity: Optional[Severity] = None,
        symbol: Optional[str] = None,
    ) -> list[AuditEvent]:
        """Get filtered audit events."""
        return [
            e
            for e in self.events
            if (event_type is None or e.event_type == event_type)
            and (severity is None or e.severity == severity)
            and (symbol is None or e.context.get("symbol") == symbol)
        ]

    def clear(self) -> None:
        """Clear all events (for testing)."""
        self.events.clear()

    def to_json_list(self) -> list[dict[str, Any]]:
        """Export all events as JSON-serializable list."""
        return [event.to_dict() for event in self.events]
