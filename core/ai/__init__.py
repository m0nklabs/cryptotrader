"""Multi-Brain AI module — Role-Based Mixture of Agents.

Architecture (from market-data/docs/research/07_implementation_roadmap.md):

    ┌─────────┐
    │  Router │  ← LLMRouter dispatches to roles
    └────┬────┘
         │
    ┌────┴──────────────────────────────────┐
    │    │           │           │          │
    ▼    ▼           ▼           ▼          ▼
  Screener   Tactical   Fundamental  Strategist
  (V3.2)     (R1)       (Grok 4)     (o3-mini)
    │         │           │           │
    └─────────┴───────────┴───────────┘
                    │
              ┌─────┴──────┐
              │  Consensus  │  ← Weighted voting + VETO
              └─────┬──────┘
                    │
              Final Decision

Submodules:
- providers: LLM provider adapters (DeepSeek, OpenAI, xAI, Ollama)
- roles:     Agent roles (Screener, Tactical, Fundamental, Strategist)
- prompts:   Versioned system prompt registry
- router:    LLMRouter — dispatches to roles and collects responses
- consensus: Weighted voting engine
- types:     Shared dataclasses and enums
"""

from core.ai.consensus import ConsensusEngine
from core.ai.router import LLMRouter
from core.ai.types import (
    AIRequest,
    AIResponse,
    ConsensusDecision,
    ProviderConfig,
    ProviderName,
    RoleConfig,
    RoleName,
    RoleVerdict,
    SignalAction,
    SystemPrompt,
    UsageRecord,
)

__all__ = [
    "ConsensusEngine",
    "LLMRouter",
    "AIRequest",
    "AIResponse",
    "ConsensusDecision",
    "ProviderConfig",
    "ProviderName",
    "RoleConfig",
    "RoleName",
    "RoleVerdict",
    "SignalAction",
    "SystemPrompt",
    "UsageRecord",
]
