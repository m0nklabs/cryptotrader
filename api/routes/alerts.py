"""API routes for alert management."""

from __future__ import annotations

import logging
import os
from typing import Literal, Optional

import asyncpg
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.alerts.models import Alert, AlertHistory
from db.crud import alerts as alerts_crud

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/alerts", tags=["alerts"])


# ---------------------------------------------------------------------------
# Request/Response Models
# ---------------------------------------------------------------------------


class AlertConditionRequest(BaseModel):
    """Request model for alert condition."""

    type: Literal[
        "price_above",
        "price_below",
        "rsi_overbought",
        "rsi_oversold",
        "macd_cross_up",
        "macd_cross_down",
    ]
    operator: Literal["above", "below", "crosses_above", "crosses_below"]
    value: float
    indicator_params: Optional[dict] = None


class CreateAlertRequest(BaseModel):
    """Request to create a new alert."""

    symbol: str
    exchange: str
    timeframe: str
    condition: AlertConditionRequest
    enabled: bool = True


class UpdateAlertRequest(BaseModel):
    """Request to update an alert."""

    enabled: Optional[bool] = None
    threshold_value: Optional[float] = None
    indicator_params: Optional[dict] = None


class AlertResponse(BaseModel):
    """Response model for alert."""

    id: int
    symbol: str
    exchange: str
    timeframe: str
    condition_type: str
    operator: str
    threshold_value: float
    indicator_params: Optional[dict]
    enabled: bool
    created_at: str
    triggered_at: Optional[str]
    trigger_count: int


class AlertHistoryResponse(BaseModel):
    """Response model for alert history."""

    id: int
    alert_id: int
    triggered_at: str
    trigger_value: float
    price: float
    message: str


class ListAlertsResponse(BaseModel):
    """Response with list of alerts."""

    alerts: list[AlertResponse]
    count: int


class AlertHistoryListResponse(BaseModel):
    """Response with alert history."""

    history: list[AlertHistoryResponse]
    count: int


# ---------------------------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------------------------


def _get_db_url() -> str:
    """Get database URL from environment."""
    db_url = os.getenv("DATABASE_URL", "postgresql://crypto:crypto@localhost:5432/cryptotrader")
    # Normalize to plain postgresql:// for asyncpg
    if db_url.startswith("postgresql+asyncpg://"):
        db_url = db_url.replace("postgresql+asyncpg://", "postgresql://")
    return db_url


async def _get_db_connection() -> asyncpg.Connection:
    """Get database connection."""
    return await asyncpg.connect(_get_db_url())


def _alert_to_response(alert: Alert) -> AlertResponse:
    """Convert Alert to AlertResponse."""
    return AlertResponse(
        id=alert.id or 0,
        symbol=alert.symbol,
        exchange=alert.exchange,
        timeframe=alert.timeframe,
        condition_type=alert.condition.type,
        operator=alert.condition.operator,
        threshold_value=alert.condition.value,
        indicator_params=alert.condition.indicator_params,
        enabled=alert.enabled,
        created_at=alert.created_at.isoformat() if alert.created_at else "",
        triggered_at=alert.triggered_at.isoformat() if alert.triggered_at else None,
        trigger_count=alert.trigger_count,
    )


def _history_to_response(history: AlertHistory) -> AlertHistoryResponse:
    """Convert AlertHistory to AlertHistoryResponse."""
    return AlertHistoryResponse(
        id=history.id or 0,
        alert_id=history.alert_id,
        triggered_at=history.triggered_at.isoformat(),
        trigger_value=history.trigger_value,
        price=history.price,
        message=history.message,
    )


# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------


@router.post("/", response_model=AlertResponse, status_code=201)
async def create_alert(request: CreateAlertRequest):
    """Create a new alert.

    Args:
        request: Alert creation request

    Returns:
        Created alert
    """
    conn = await _get_db_connection()
    try:
        alert = await alerts_crud.create_alert(
            conn,
            symbol=request.symbol,
            exchange=request.exchange,
            timeframe=request.timeframe,
            condition_type=request.condition.type,
            operator=request.condition.operator,
            threshold_value=request.condition.value,
            indicator_params=request.condition.indicator_params,
            enabled=request.enabled,
        )
        logger.info(f"Created alert {alert.id} for {request.symbol} on {request.exchange}")
        return _alert_to_response(alert)
    finally:
        await conn.close()


@router.get("/", response_model=ListAlertsResponse)
async def list_alerts(
    symbol: Optional[str] = None,
    exchange: Optional[str] = None,
    enabled_only: bool = False,
):
    """List alerts with optional filtering.

    Args:
        symbol: Optional symbol filter
        exchange: Optional exchange filter
        enabled_only: Only return enabled alerts

    Returns:
        List of alerts
    """
    conn = await _get_db_connection()
    try:
        alerts = await alerts_crud.list_alerts(
            conn,
            symbol=symbol,
            exchange=exchange,
            enabled_only=enabled_only,
        )
        return ListAlertsResponse(
            alerts=[_alert_to_response(alert) for alert in alerts],
            count=len(alerts),
        )
    finally:
        await conn.close()


@router.get("/{alert_id}", response_model=AlertResponse)
async def get_alert(alert_id: int):
    """Get a specific alert by ID.

    Args:
        alert_id: Alert ID

    Returns:
        Alert details

    Raises:
        HTTPException: If alert not found
    """
    conn = await _get_db_connection()
    try:
        alert = await alerts_crud.get_alert(conn, alert_id)
        if not alert:
            raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")
        return _alert_to_response(alert)
    finally:
        await conn.close()


@router.patch("/{alert_id}", response_model=AlertResponse)
async def update_alert(alert_id: int, request: UpdateAlertRequest):
    """Update an alert.

    Args:
        alert_id: Alert ID
        request: Update request

    Returns:
        Updated alert

    Raises:
        HTTPException: If alert not found
    """
    conn = await _get_db_connection()
    try:
        alert = await alerts_crud.update_alert(
            conn,
            alert_id,
            enabled=request.enabled,
            threshold_value=request.threshold_value,
            indicator_params=request.indicator_params,
        )
        if not alert:
            raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")
        logger.info(f"Updated alert {alert_id}")
        return _alert_to_response(alert)
    finally:
        await conn.close()


@router.delete("/{alert_id}", status_code=204)
async def delete_alert(alert_id: int):
    """Delete an alert.

    Args:
        alert_id: Alert ID

    Raises:
        HTTPException: If alert not found
    """
    conn = await _get_db_connection()
    try:
        success = await alerts_crud.delete_alert(conn, alert_id)
        if not success:
            raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")
        logger.info(f"Deleted alert {alert_id}")
    finally:
        await conn.close()


@router.get("/{alert_id}/history", response_model=AlertHistoryListResponse)
async def get_alert_history(alert_id: int, limit: int = 100):
    """Get history for a specific alert.

    Args:
        alert_id: Alert ID
        limit: Maximum number of records to return

    Returns:
        Alert history
    """
    conn = await _get_db_connection()
    try:
        history = await alerts_crud.get_alert_history(conn, alert_id=alert_id, limit=limit)
        return AlertHistoryListResponse(
            history=[_history_to_response(h) for h in history],
            count=len(history),
        )
    finally:
        await conn.close()


@router.get("/history/all", response_model=AlertHistoryListResponse)
async def get_all_alert_history(limit: int = 100):
    """Get history for all alerts.

    Args:
        limit: Maximum number of records to return

    Returns:
        Alert history across all alerts
    """
    conn = await _get_db_connection()
    try:
        history = await alerts_crud.get_alert_history(conn, limit=limit)
        return AlertHistoryListResponse(
            history=[_history_to_response(h) for h in history],
            count=len(history),
        )
    finally:
        await conn.close()
