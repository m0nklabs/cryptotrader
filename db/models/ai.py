"""SQLAlchemy models for Multi-Brain AI tables.

These models map to the tables created by db/migrations/001_ai_tables.sql:
- system_prompts
- ai_role_configs
- ai_usage_log
- ai_decisions
"""

from __future__ import annotations


from sqlalchemy import BigInteger, Boolean, Column, Float, Integer, Text, ForeignKey, Index, DateTime, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""

    pass


class SystemPrompt(Base):
    """Versioned system prompt storage per role.

    Table: system_prompts
    """

    __tablename__ = "system_prompts"

    id = Column(Text, primary_key=True)  # e.g. "tactical_v1"
    role = Column(Text, nullable=False)  # screener|tactical|fundamental|strategist
    version = Column(Integer, nullable=False, default=1)
    content = Column(Text, nullable=False)
    description = Column(Text, nullable=False, default="")
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (Index("idx_system_prompts_role", "role", "is_active"),)

    def __repr__(self) -> str:
        return f"<SystemPrompt(id={self.id}, role={self.role}, v{self.version}, active={self.is_active})>"


class AIRoleConfig(Base):
    """Provider/model assignment per role.

    Table: ai_role_configs
    """

    __tablename__ = "ai_role_configs"

    name = Column(Text, primary_key=True)  # screener|tactical|fundamental|strategist
    provider = Column(Text, nullable=False)  # deepseek|openai|xai|ollama|google
    model = Column(Text, nullable=False)
    system_prompt_id = Column(Text, ForeignKey("system_prompts.id"), nullable=True)
    temperature = Column(Float, nullable=False, default=0.0)
    max_tokens = Column(Integer, nullable=False, default=4096)
    weight = Column(Float, nullable=False, default=1.0)
    enabled = Column(Boolean, nullable=False, default=True)
    fallback_provider = Column(Text, nullable=True)
    fallback_model = Column(Text, nullable=True)
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    def __repr__(self) -> str:
        return f"<AIRoleConfig(name={self.name}, provider={self.provider}, model={self.model})>"


class AIUsageLog(Base):
    """Cost/token tracking per AI request.

    Table: ai_usage_log
    """

    __tablename__ = "ai_usage_log"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    role = Column(Text, nullable=False)
    provider = Column(Text, nullable=False)
    model = Column(Text, nullable=False)
    tokens_in = Column(Integer, nullable=False, default=0)
    tokens_out = Column(Integer, nullable=False, default=0)
    cost_usd = Column(Float, nullable=False, default=0.0)
    latency_ms = Column(Float, nullable=False, default=0.0)
    symbol = Column(Text, nullable=False, default="")
    success = Column(Boolean, nullable=False, default=True)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        Index("idx_ai_usage_log_created", "created_at"),
        Index("idx_ai_usage_log_role", "role"),
        Index("idx_ai_usage_log_symbol", "symbol"),
    )

    def __repr__(self) -> str:
        return f"<AIUsageLog(id={self.id}, role={self.role}, cost=${self.cost_usd:.4f})>"


class AIDecision(Base):
    """Consensus decisions audit trail.

    Table: ai_decisions
    """

    __tablename__ = "ai_decisions"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    symbol = Column(Text, nullable=False)
    timeframe = Column(Text, nullable=False)
    final_action = Column(Text, nullable=False)  # BUY|SELL|NEUTRAL|VETO
    final_confidence = Column(Float, nullable=False, default=0.0)
    verdicts = Column(JSONB, nullable=False, default=lambda: [])  # list of RoleVerdict dicts
    reasoning = Column(Text, nullable=False, default="")
    vetoed_by = Column(Text, nullable=True)
    total_cost_usd = Column(Float, nullable=False, default=0.0)
    total_latency_ms = Column(Float, nullable=False, default=0.0)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        Index("idx_ai_decisions_symbol", "symbol", "created_at"),
        Index("idx_ai_decisions_action", "final_action"),
    )

    def __repr__(self) -> str:
        return f"<AIDecision(id={self.id}, symbol={self.symbol}, action={self.final_action})>"
