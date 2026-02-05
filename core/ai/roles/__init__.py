"""Agent roles — Multi-Brain topology.

Each role wraps an LLM provider and applies a domain-specific system
prompt.  The router dispatches requests to roles and the consensus
engine aggregates their verdicts.
"""

from __future__ import annotations

from .base import AgentRole, RoleRegistry

__all__ = ["AgentRole", "RoleRegistry"]
