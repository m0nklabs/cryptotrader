"""Automation engine skeleton.

This package defines policies, safety checks, and orchestration between signals,
fees, and execution.

Default must remain paper-trading / dry-run.
"""

from .audit import AuditEvent, AuditLogger
from .policy import Policy, PolicyDecision
from .rules import AutomationConfig, SymbolConfig, TradeHistory, TradeRecord
from .safety import (
    BalanceCheck,
    CooldownCheck,
    DailyLossCheck,
    DailyTradeCountCheck,
    KillSwitchCheck,
    PositionSizeCheck,
    SafetyCheck,
    SafetyResult,
    SlippageCheck,
    run_safety_checks,
)

__all__ = [
    # Policy
    "Policy",
    "PolicyDecision",
    # Rules
    "AutomationConfig",
    "SymbolConfig",
    "TradeHistory",
    "TradeRecord",
    # Safety
    "SafetyCheck",
    "SafetyResult",
    "run_safety_checks",
    "KillSwitchCheck",
    "PositionSizeCheck",
    "CooldownCheck",
    "DailyTradeCountCheck",
    "BalanceCheck",
    "DailyLossCheck",
    "SlippageCheck",
    # Audit
    "AuditEvent",
    "AuditLogger",
]
