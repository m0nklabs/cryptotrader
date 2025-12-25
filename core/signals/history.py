"""Signal history logging for backtesting and optimization.

Stores signal scores with indicator contributions to the database
for later analysis, backtesting, and strategy optimization.

Usage:
    from core.signals.history import log_signal_history

    # Log signal to database (silent failure if DB unavailable)
    await log_signal_history(
        symbol="BTCUSD",
        timeframe="1h",
        score=75,
        indicator_contributions={"RSI": 20.0, "MACD": 30.0, "STOCH": 25.0},
        db_pool=pool,
    )
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


async def log_signal_history(
    *,
    symbol: str,
    timeframe: str,
    score: float,
    indicator_contributions: dict[str, float],
    db_pool: Any | None = None,
) -> bool:
    """Log signal score and indicator contributions to database.

    Args:
        symbol: Trading symbol (e.g., "BTCUSD")
        timeframe: Timeframe (e.g., "1h", "15m")
        score: Final signal score (0-100)
        indicator_contributions: Dict mapping indicator codes to their contributions
        db_pool: Optional database connection pool

    Returns:
        True if successfully logged, False otherwise

    Note:
        - Fails silently if DB unavailable (logs debug message)
        - Stores contributions as JSONB for efficient querying
        - Auto-timestamps with UTC
    """
    if db_pool is None:
        logger.debug("No DB pool provided, skipping signal history logging")
        return False

    try:
        # Prepare JSONB-compatible contributions
        contributions_json = json.dumps(indicator_contributions)
        timestamp = datetime.now(timezone.utc)

        # Insert query (supports both asyncpg and SQLAlchemy)
        query = """
            INSERT INTO signal_history (symbol, timeframe, score, indicator_contributions, created_at)
            VALUES ($1, $2, $3, $4, $5)
        """

        # Try asyncpg-style query (has 'fetch' method)
        if hasattr(db_pool, "fetch"):
            await db_pool.execute(
                query,
                symbol,
                timeframe,
                score,
                contributions_json,
                timestamp,
            )
            logger.debug(f"Logged signal history: {symbol} {timeframe} score={score}")
            return True

        # Try SQLAlchemy async session (has 'commit' method but not 'fetch')
        elif hasattr(db_pool, "commit"):
            from sqlalchemy import text

            await db_pool.execute(
                text(
                    """
                    INSERT INTO signal_history (symbol, timeframe, score, indicator_contributions, created_at)
                    VALUES (:symbol, :timeframe, :score, :contributions, :created_at)
                    """
                ),
                {
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "score": score,
                    "contributions": contributions_json,
                    "created_at": timestamp,
                },
            )
            await db_pool.commit()
            logger.debug(f"Logged signal history: {symbol} {timeframe} score={score}")
            return True

    except Exception as exc:
        # Log error but don't raise - signal detection should continue
        logger.debug(f"Failed to log signal history for {symbol} {timeframe}: {exc}")
        return False

    return False


async def get_signal_history(
    *,
    symbol: str | None = None,
    timeframe: str | None = None,
    limit: int = 100,
    db_pool: Any | None = None,
) -> list[dict[str, Any]]:
    """Retrieve signal history from database.

    Args:
        symbol: Optional symbol filter
        timeframe: Optional timeframe filter
        limit: Maximum number of records to return (default: 100)
        db_pool: Database connection pool

    Returns:
        List of signal history records as dictionaries

    Example:
        >>> history = await get_signal_history(symbol="BTCUSD", timeframe="1h", limit=50, db_pool=pool)
        >>> for record in history:
        ...     print(f"{record['created_at']}: score={record['score']}")
    """
    if db_pool is None:
        logger.debug("No DB pool provided, returning empty history")
        return []

    try:
        # Try asyncpg-style query (has 'fetch' method)
        if hasattr(db_pool, "fetch"):
            return await _get_signal_history_asyncpg(db_pool=db_pool, symbol=symbol, timeframe=timeframe, limit=limit)

        # Try SQLAlchemy async session (has 'commit' method but not 'fetch')
        elif hasattr(db_pool, "commit"):
            return await _get_signal_history_sqlalchemy(
                db_pool=db_pool, symbol=symbol, timeframe=timeframe, limit=limit
            )

    except Exception as exc:
        logger.warning(f"Failed to retrieve signal history: {exc}")
        return []

    return []


async def _get_signal_history_asyncpg(
    *,
    db_pool: Any,
    symbol: str | None = None,
    timeframe: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Retrieve signal history using asyncpg-style pool."""
    # Build query with positional parameters
    conditions = []
    params = []

    if symbol:
        params.append(symbol)
        conditions.append(f"symbol = ${len(params)}")

    if timeframe:
        params.append(timeframe)
        conditions.append(f"timeframe = ${len(params)}")

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    params.append(limit)
    query = f"""
        SELECT id, symbol, timeframe, score, indicator_contributions, created_at
        FROM signal_history
        {where_clause}
        ORDER BY created_at DESC
        LIMIT ${len(params)}
    """

    rows = await db_pool.fetch(query, *params)
    return [dict(row) for row in rows]


async def _get_signal_history_sqlalchemy(
    *,
    db_pool: Any,
    symbol: str | None = None,
    timeframe: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Retrieve signal history using SQLAlchemy-style session."""
    from sqlalchemy import text

    # Build query with named parameters
    conditions = []
    params: dict[str, Any] = {"limit": limit}

    if symbol:
        conditions.append("symbol = :symbol")
        params["symbol"] = symbol

    if timeframe:
        conditions.append("timeframe = :timeframe")
        params["timeframe"] = timeframe

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    query = f"""
        SELECT id, symbol, timeframe, score, indicator_contributions, created_at
        FROM signal_history
        {where_clause}
        ORDER BY created_at DESC
        LIMIT :limit
    """

    result = await db_pool.execute(text(query), params)
    rows = result.fetchall()
    return [
        {
            "id": row[0],
            "symbol": row[1],
            "timeframe": row[2],
            "score": float(row[3]),
            "indicator_contributions": json.loads(row[4]) if row[4] else {},
            "created_at": row[5],
        }
        for row in rows
    ]
