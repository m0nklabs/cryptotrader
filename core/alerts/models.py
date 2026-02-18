"""Data models for the alert system."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Optional

# Alert types that can be monitored
AlertType = Literal[
    "price_above",      # Price crosses above threshold
    "price_below",      # Price crosses below threshold
    "rsi_overbought",   # RSI above threshold (default 70)
    "rsi_oversold",     # RSI below threshold (default 30)
    "macd_cross_up",    # MACD line crosses above signal
    "macd_cross_down",  # MACD line crosses below signal
]

# Comparison operators for conditions
ComparisonOperator = Literal["above", "below", "crosses_above", "crosses_below"]


@dataclass
class AlertCondition:
    """Condition that triggers an alert."""

    type: AlertType
    operator: ComparisonOperator
    value: float
    indicator_params: Optional[dict] = None  # Additional params for indicators (e.g., RSI period)


@dataclass
class Alert:
    """User-defined alert configuration."""

    symbol: str
    exchange: str
    timeframe: str
    condition: AlertCondition
    enabled: bool = True
    id: Optional[int] = None
    user_id: Optional[str] = None  # For future multi-user support
    created_at: Optional[datetime] = None
    triggered_at: Optional[datetime] = None
    trigger_count: int = 0


@dataclass
class AlertHistory:
    """Record of when an alert was triggered."""

    alert_id: int
    triggered_at: datetime
    trigger_value: float
    price: float
    message: str
    id: Optional[int] = None
