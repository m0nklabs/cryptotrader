"""FastAPI application for read-only candles and health endpoints.

This module provides a minimal HTTP API service for:
- GET /health - Database connectivity and schema check
- GET /candles/latest - Latest candles with query parameters

Requirements:
- DATABASE_URL must be set in environment
- No authentication (local network only)
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse

from core.storage.postgres.config import PostgresConfig
from core.storage.postgres.stores import PostgresStores

app = FastAPI(
    title="CryptoTrader Read-Only API",
    description="Minimal API for candles and health checks",
    version="1.0.0",
)

# Global store instance (initialized on startup)
_stores: PostgresStores | None = None


def _get_stores() -> PostgresStores:
    """Get or initialize the database stores."""
    global _stores
    if _stores is None:
        database_url = os.environ.get("DATABASE_URL")
        if not database_url:
            raise RuntimeError("DATABASE_URL environment variable is required")
        _stores = PostgresStores(config=PostgresConfig(database_url=database_url))
    return _stores


def _as_utc(dt: datetime) -> datetime:
    """Convert datetime to UTC."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


@app.get("/health")
async def health() -> dict[str, Any]:
    """Health check endpoint.

    Returns:
        JSON with database connectivity status and schema information.

    Raises:
        HTTPException: If database connection fails.
    """
    try:
        stores = _get_stores()
        engine = stores._get_engine()  # noqa: SLF001
        _, text = stores._require_sqlalchemy()  # noqa: SLF001

        # Check database connectivity and candles table
        with engine.begin() as conn:
            # Verify candles table exists
            result = conn.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM information_schema.tables
                    WHERE table_name = 'candles'
                    """
                )
            ).scalar()

            candles_table_exists = result > 0

            # Get total candle count if table exists
            total_candles = 0
            if candles_table_exists:
                total_candles = conn.execute(text("SELECT COUNT(*) FROM candles")).scalar() or 0

        return {
            "status": "ok",
            "database": {
                "connected": True,
                "candles_table_exists": candles_table_exists,
                "total_candles": total_candles,
            },
        }

    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail={
                "status": "error",
                "database": {
                    "connected": False,
                    "error": str(e),
                },
            },
        ) from e


@app.get("/candles/latest")
async def get_latest_candles(
    exchange: str = Query(default="bitfinex", description="Exchange name"),
    symbol: str = Query(..., description="Trading symbol (e.g., BTCUSD)"),
    timeframe: str = Query(..., description="Timeframe (e.g., 1m, 5m, 1h)"),
    limit: int = Query(default=100, ge=1, le=5000, description="Number of candles to return"),
) -> dict[str, Any]:
    """Get latest candles for a specific exchange, symbol, and timeframe.

    Args:
        exchange: Exchange name (default: bitfinex)
        symbol: Trading symbol (e.g., BTCUSD)
        timeframe: Candle timeframe (e.g., 1m, 5m, 1h)
        limit: Maximum number of candles to return (1-5000)

    Returns:
        JSON with candles data and metadata.

    Raises:
        HTTPException: If database query fails or no data found.
    """
    try:
        stores = _get_stores()
        engine = stores._get_engine()  # noqa: SLF001
        _, text = stores._require_sqlalchemy()  # noqa: SLF001

        # Query latest candles
        stmt = text(
            """
            SELECT open_time, open, high, low, close, volume
            FROM candles
            WHERE exchange = :exchange
              AND symbol = :symbol
              AND timeframe = :timeframe
            ORDER BY open_time DESC
            LIMIT :limit
            """
        )

        with engine.begin() as conn:
            rows = conn.execute(
                stmt,
                {
                    "exchange": exchange,
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "limit": limit,
                },
            ).fetchall()

        if not rows:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": "no_data",
                    "message": f"No candles found for {exchange}:{symbol}:{timeframe}",
                },
            )

        # Convert to ascending time order for charting
        rows = list(reversed(rows))

        candles = []
        for open_time, open_, high, low, close, volume in rows:
            dt = _as_utc(open_time)
            candles.append(
                {
                    "open_time": dt.isoformat(),
                    "open_time_ms": int(dt.timestamp() * 1000),
                    "open": float(open_),
                    "high": float(high),
                    "low": float(low),
                    "close": float(close),
                    "volume": float(volume),
                }
            )

        # Get the latest candle timestamp for metadata
        latest_candle = candles[-1] if candles else None
        latest_open_time = latest_candle["open_time"] if latest_candle else None
        latest_open_time_ms = latest_candle["open_time_ms"] if latest_candle else None

        return {
            "exchange": exchange,
            "symbol": symbol,
            "timeframe": timeframe,
            "count": len(candles),
            "latest_open_time": latest_open_time,
            "latest_open_time_ms": latest_open_time_ms,
            "candles": candles,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={
                "error": "database_error",
                "message": str(e),
            },
        ) from e


@app.exception_handler(Exception)
async def global_exception_handler(_request, exc):
    """Global exception handler to ensure consistent error responses."""
    return JSONResponse(
        status_code=500,
        content={
            "error": "internal_server_error",
            "message": "An unexpected error occurred",
        },
    )
