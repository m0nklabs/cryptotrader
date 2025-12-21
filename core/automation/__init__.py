"""Automation engine skeleton.

This package defines policies, safety checks, and orchestration between signals,
fees, and execution.

Default must remain paper-trading / dry-run.
"""

from .policy import Policy, PolicyDecision
from .safety import SafetyCheck, SafetyResult
