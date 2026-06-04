"""CRUD operations for alerts system."""

from __future__ import annotations

import json
import logging
from typing import Optional, Sequence

import asyncpg

from core.alerts.models import Alert, AlertCondition, AlertHistory

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Alert CRUD Operations
# ---------------------------------------------------------------------------


async def create_alert(
    conn: asyncpg.Connection,
    symbol: str,
    exchange: str,
    timeframe: str,
    condition_type: str,
    operator: str,
    threshold_value: float,
    indicator_params: Optional[dict] = None,
    user_id: Optional[str] = None,
    enabled: bool = True,
) -> Alert:
    """Create a new alert.

    Args:
        conn: Database connection
        symbol: Trading symbol
        exchange: Exchange name
        timeframe: Timeframe (e.g., "1m", "5m", "1h")
        condition_type: Type of alert condition
        operator: Comparison operator
        threshold_value: Threshold value
        indicator_params: Optional indicator parameters
        user_id: Optional user ID for multi-user support
        enabled: Whether alert is enabled

    Returns:
        Created Alert object
    """
    row = await conn.fetchrow(
        """
        INSERT INTO alerts (
            user_id, symbol, exchange, timeframe,
            condition_type, operator, threshold_value, indicator_params,
            enabled
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
        RETURNING id, user_id, symbol, exchange, timeframe,
                  condition_type, operator, threshold_value, indicator_params,
                  enabled, created_at, triggered_at, trigger_count
        """,
        user_id,
        symbol,
        exchange,
        timeframe,
        condition_type,
        operator,
        threshold_value,
        json.dumps(indicator_params) if indicator_params else None,
        enabled,
    )

    return _row_to_alert(row)


async def get_alert(conn: asyncpg.Connection, alert_id: int) -> Optional[Alert]:
    """Get an alert by ID.

    Args:
        conn: Database connection
        alert_id: Alert ID

    Returns:
        Alert object or None if not found
    """
    row = await conn.fetchrow(
        """
        SELECT id, user_id, symbol, exchange, timeframe,
               condition_type, operator, threshold_value, indicator_params,
               enabled, created_at, triggered_at, trigger_count
        FROM alerts
        WHERE id = $1
        """,
        alert_id,
    )

    return _row_to_alert(row) if row else None


async def list_alerts(
    conn: asyncpg.Connection,
    symbol: Optional[str] = None,
    exchange: Optional[str] = None,
    enabled_only: bool = False,
    user_id: Optional[str] = None,
) -> Sequence[Alert]:
    """List alerts with optional filtering.

    Args:
        conn: Database connection
        symbol: Optional symbol filter
        exchange: Optional exchange filter
        enabled_only: Only return enabled alerts
        user_id: Optional user ID filter

    Returns:
        List of Alert objects
    """
    conditions = []
    params = []
    param_idx = 1

    if symbol:
        conditions.append(f"symbol = ${param_idx}")
        params.append(symbol)
        param_idx += 1

    if exchange:
        conditions.append(f"exchange = ${param_idx}")
        params.append(exchange)
        param_idx += 1

    if enabled_only:
        conditions.append("enabled = true")

    if user_id is not None:
        conditions.append(f"user_id = ${param_idx}")
        params.append(user_id)
        param_idx += 1

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    rows = await conn.fetch(
        f"""
        SELECT id, user_id, symbol, exchange, timeframe,
               condition_type, operator, threshold_value, indicator_params,
               enabled, created_at, triggered_at, trigger_count
        FROM alerts
        {where_clause}
        ORDER BY created_at DESC
        """,
        *params,
    )

    return [_row_to_alert(row) for row in rows]


async def update_alert(
    conn: asyncpg.Connection,
    alert_id: int,
    enabled: Optional[bool] = None,
    threshold_value: Optional[float] = None,
    indicator_params: Optional[dict] = None,
) -> Optional[Alert]:
    """Update an alert.

    Args:
        conn: Database connection
        alert_id: Alert ID
        enabled: Optional new enabled state
        threshold_value: Optional new threshold value
        indicator_params: Optional new indicator parameters

    Returns:
        Updated Alert object or None if not found
    """
    updates = []
    params = []
    param_idx = 1

    if enabled is not None:
        updates.append(f"enabled = ${param_idx}")
        params.append(enabled)
        param_idx += 1

    if threshold_value is not None:
        updates.append(f"threshold_value = ${param_idx}")
        params.append(threshold_value)
        param_idx += 1

    if indicator_params is not None:
        updates.append(f"indicator_params = ${param_idx}")
        params.append(json.dumps(indicator_params))
        param_idx += 1

    if not updates:
        return await get_alert(conn, alert_id)

    params.append(alert_id)
    row = await conn.fetchrow(
        f"""
        UPDATE alerts
        SET {", ".join(updates)}
        WHERE id = ${param_idx}
        RETURNING id, user_id, symbol, exchange, timeframe,
                  condition_type, operator, threshold_value, indicator_params,
                  enabled, created_at, triggered_at, trigger_count
        """,
        *params,
    )

    return _row_to_alert(row) if row else None


async def delete_alert(conn: asyncpg.Connection, alert_id: int) -> bool:
    """Delete an alert.

    Args:
        conn: Database connection
        alert_id: Alert ID

    Returns:
        True if deleted, False if not found
    """
    result = await conn.execute(
        "DELETE FROM alerts WHERE id = $1",
        alert_id,
    )
    return result.endswith("1")


async def mark_alert_triggered(
    conn: asyncpg.Connection,
    alert_id: int,
) -> None:
    """Mark an alert as triggered.

    Args:
        conn: Database connection
        alert_id: Alert ID
    """
    await conn.execute(
        """
        UPDATE alerts
        SET triggered_at = NOW(), trigger_count = trigger_count + 1
        WHERE id = $1
        """,
        alert_id,
    )


# ---------------------------------------------------------------------------
# Alert History CRUD Operations
# ---------------------------------------------------------------------------


async def create_alert_history(
    conn: asyncpg.Connection,
    alert_id: int,
    trigger_value: float,
    price: float,
    message: str,
) -> AlertHistory:
    """Create an alert history entry.

    Args:
        conn: Database connection
        alert_id: Alert ID
        trigger_value: Value that triggered the alert
        price: Price at trigger time
        message: Human-readable message

    Returns:
        Created AlertHistory object
    """
    row = await conn.fetchrow(
        """
        INSERT INTO alert_history (alert_id, trigger_value, price, message)
        VALUES ($1, $2, $3, $4)
        RETURNING id, alert_id, triggered_at, trigger_value, price, message
        """,
        alert_id,
        trigger_value,
        price,
        message,
    )

    return _row_to_alert_history(row)


async def get_alert_history(
    conn: asyncpg.Connection,
    alert_id: Optional[int] = None,
    limit: int = 100,
) -> Sequence[AlertHistory]:
    """Get alert history.

    Args:
        conn: Database connection
        alert_id: Optional alert ID filter
        limit: Maximum number of records to return

    Returns:
        List of AlertHistory objects
    """
    if alert_id is not None:
        rows = await conn.fetch(
            """
            SELECT id, alert_id, triggered_at, trigger_value, price, message
            FROM alert_history
            WHERE alert_id = $1
            ORDER BY triggered_at DESC
            LIMIT $2
            """,
            alert_id,
            limit,
        )
    else:
        rows = await conn.fetch(
            """
            SELECT id, alert_id, triggered_at, trigger_value, price, message
            FROM alert_history
            ORDER BY triggered_at DESC
            LIMIT $1
            """,
            limit,
        )

    return [_row_to_alert_history(row) for row in rows]


# ---------------------------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------------------------


def _row_to_alert(row: asyncpg.Record) -> Alert:
    """Convert database row to Alert object."""
    indicator_params = None
    if row["indicator_params"]:
        if isinstance(row["indicator_params"], str):
            indicator_params = json.loads(row["indicator_params"])
        else:
            indicator_params = row["indicator_params"]

    condition = AlertCondition(
        type=row["condition_type"],
        operator=row["operator"],
        value=row["threshold_value"],
        indicator_params=indicator_params,
    )

    return Alert(
        id=row["id"],
        user_id=row["user_id"],
        symbol=row["symbol"],
        exchange=row["exchange"],
        timeframe=row["timeframe"],
        condition=condition,
        enabled=row["enabled"],
        created_at=row["created_at"],
        triggered_at=row["triggered_at"],
        trigger_count=row["trigger_count"],
    )


def _row_to_alert_history(row: asyncpg.Record) -> AlertHistory:
    """Convert database row to AlertHistory object."""
    return AlertHistory(
        id=row["id"],
        alert_id=row["alert_id"],
        triggered_at=row["triggered_at"],
        trigger_value=row["trigger_value"],
        price=row["price"],
        message=row["message"],
    )
