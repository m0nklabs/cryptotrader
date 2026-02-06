"""FastAPI application for candles, health, and paper trading endpoints.

This module provides a minimal HTTP API service for:
- GET /health - Database connectivity and schema check
- GET /candles/latest - Latest candles with query parameters
- GET /ingestion/status - Ingestion freshness for UI/ops tools
- POST /orders - Place paper order
- GET /orders - List open orders
- DELETE /orders/{order_id} - Cancel order
- GET /positions - List open positions
- GET /market-cap - Current market cap rankings from CoinGecko

Requirements:
- DATABASE_URL must be set in environment
- No authentication (local network only)
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Literal, Optional

from fastapi import FastAPI, HTTPException, Query, Path
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from api.candle_stream import get_candle_stream_service
from core.execution.paper import PaperExecutor, PaperOrder, PaperPosition
from core.fees.model import FeeModel
from core.market_cap.coingecko import CoinGeckoClient
from core.storage.postgres.config import PostgresConfig
from core.storage.postgres.stores import PostgresStores
from core.types import FeeBreakdown

# Import new route modules with aliases to avoid conflicts
from api.routes import (
    health as health_routes,
    ratelimit,
    notifications,
    export as export_routes,
    ws as ws_routes,
    arbitrage as arbitrage_routes,
)

# Import middleware for rate limit tracking
from core.ratelimit import RateLimitMiddleware

logger = logging.getLogger(__name__)

app = FastAPI(
    title="CryptoTrader API",
    description="API for candles, health checks, ingestion status, and paper trading",
    version="1.0.0",
)

# Add middleware for rate limit tracking
app.add_middleware(RateLimitMiddleware)

# Global store instance (initialized on startup)
_stores: PostgresStores | None = None

# Global paper executor instance (in-memory, no DB persistence)
_paper_executor: PaperExecutor | None = None

# Global CoinGecko client (singleton)
_coingecko_client: CoinGeckoClient | None = None

# Global market cap cache
_market_cap_cache: dict[str, int] = {}
_market_cap_cache_time: float = 0
_market_cap_cache_source: str = "fallback"  # Track actual source of cached data
_market_cap_cache_lock = threading.Lock()
MARKET_CAP_CACHE_TTL = 600  # 10 minutes in seconds

# Signal analysis cache (for LLM + historical analysis)
_signal_analysis_cache: dict[str, dict[str, Any]] = {}
_signal_analysis_cache_lock = threading.Lock()
ANALYSIS_CACHE_TTL = 300  # 5 minutes

# Global correlation cache
# Key format: "symbols:exchange:timeframe:lookback" -> (result, timestamp)
_correlation_cache: dict[str, tuple[dict[str, Any], float]] = {}
_correlation_cache_lock = threading.Lock()
CORRELATION_CACHE_TTL = 300  # 5 minutes in seconds (correlations change slowly)
MAX_CACHE_SIZE = 100  # Maximum number of cached correlation results
CACHE_EVICTION_SIZE = 50  # Number of entries to keep after eviction

# Shared thread pool for blocking operations (e.g., sync correlation calculation)
_executor = ThreadPoolExecutor(max_workers=4)

# Track application start time for uptime calculation
_app_start_time: float = time.time()

# Static fallback market cap rankings
FALLBACK_MARKET_CAP_RANK: dict[str, int] = {
    "BTC": 1,
    "ETH": 2,
    "XRP": 3,
    "SOL": 4,
    "ADA": 5,
    "DOGE": 6,
    "LTC": 7,
    "AVAX": 8,
    "LINK": 9,
    "DOT": 10,
}


def _get_coingecko_client() -> CoinGeckoClient:
    """Get or initialize the CoinGecko client singleton."""
    global _coingecko_client
    if _coingecko_client is None:
        _coingecko_client = CoinGeckoClient(timeout=10)
    return _coingecko_client


def _get_paper_executor() -> PaperExecutor:
    """Get or initialize the paper trading executor."""
    global _paper_executor
    if _paper_executor is None:
        _paper_executor = PaperExecutor(default_slippage_bps=Decimal("5"))
    return _paper_executor


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


def _analysis_cache_key(*, exchange: str, symbol: str, timeframe: str) -> str:
    return f"{exchange.lower()}:{symbol.upper()}:{timeframe}"


def _get_cached_analysis(key: str) -> dict[str, Any] | None:
    now = time.time()
    with _signal_analysis_cache_lock:
        entry = _signal_analysis_cache.get(key)
        if not entry:
            return None
        if now - entry.get("timestamp", 0) > ANALYSIS_CACHE_TTL:
            _signal_analysis_cache.pop(key, None)
            return None
        return entry


def _set_cached_analysis(key: str, payload: dict[str, Any]) -> None:
    with _signal_analysis_cache_lock:
        _signal_analysis_cache[key] = payload


def _as_utc(dt: datetime) -> datetime:
    """Convert datetime to UTC."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class FeesEstimateRequest(BaseModel):
    taker: bool = True
    gross_notional: Decimal = Field(..., gt=0)

    currency: str = Field("USD", min_length=1)
    maker_fee_rate: Decimal = Field(Decimal("0"), ge=0)
    taker_fee_rate: Decimal = Field(Decimal("0"), ge=0)
    assumed_spread_bps: int = Field(0, ge=0)
    assumed_slippage_bps: int = Field(0, ge=0)


class FeesEstimateResponse(BaseModel):
    fee_total: Decimal
    spread_cost: Decimal
    slippage_cost: Decimal
    minimum_edge_rate: Decimal
    minimum_edge_bps: Decimal


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


@app.get("/ingestion/status")
async def get_ingestion_status(
    exchange: str = Query("bitfinex", description="Exchange name"),
    symbol: str = Query(..., description="Trading symbol (e.g., BTCUSD)"),
    timeframe: str = Query(..., description="Timeframe (e.g., 1m, 1h)"),
) -> dict[str, Any]:
    """Get ingestion status for a specific exchange/symbol/timeframe.

    Returns:
        - latest_candle_open_time: Unix timestamp in milliseconds of the latest candle
        - candles_count: Total number of candles in the database
        - schema_ok: Boolean indicating if the candles table exists
        - db_ok: Boolean indicating if database connection is working
    """
    # Check DB connectivity and schema
    db_ok = False
    schema_ok = False
    latest_candle_open_time: int | None = None
    candles_count: int | None = None

    try:
        stores = _get_stores()
        engine = stores._get_engine()  # noqa: SLF001
        _, text = stores._require_sqlalchemy()  # noqa: SLF001

        # Test DB connection and check if candles table exists
        with engine.begin() as conn:
            # Check if candles table exists
            schema_check = text(
                """
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_schema = 'public'
                    AND table_name = 'candles'
                )
                """
            )
            schema_result = conn.execute(schema_check).scalar()
            schema_ok = bool(schema_result)

            if schema_ok:
                # Get latest candle and count
                stats_query = text(
                    """
                    SELECT
                        MAX(open_time) as latest_open_time,
                        COUNT(*) as total_count
                    FROM candles
                    WHERE exchange = :exchange
                      AND symbol = :symbol
                      AND timeframe = :timeframe
                    """
                )
                result = conn.execute(
                    stats_query,
                    {"exchange": exchange, "symbol": symbol, "timeframe": timeframe},
                ).fetchone()

                if result:
                    latest_open_time, total_count = result
                    candles_count = int(total_count) if total_count is not None else 0

                    if latest_open_time is not None:
                        dt = _as_utc(latest_open_time)
                        latest_candle_open_time = int(dt.timestamp() * 1000)

        db_ok = True

    except Exception as exc:
        # Return error response with db_ok=False
        return JSONResponse(
            status_code=200,  # Still return 200 with error flags
            content={
                "latest_candle_open_time": None,
                "candles_count": None,
                "schema_ok": False,
                "db_ok": False,
                "error": type(exc).__name__,
            },
        )

    return {
        "latest_candle_open_time": latest_candle_open_time,
        "candles_count": candles_count,
        "schema_ok": schema_ok,
        "db_ok": db_ok,
    }


@app.get("/gaps/summary")
@app.get("/api/gaps/summary")
async def get_gap_summary() -> dict[str, Any]:
    """Get candle gap summary stats.

    Returns:
        - open_gaps: Total unrepaired gaps
        - repaired_24h: Gaps repaired in the last 24 hours
        - oldest_open_gap: Oldest unrepaired gap timestamp (ms since epoch) or null
    """
    try:
        stores = _get_stores()
        engine = stores._get_engine()  # noqa: SLF001
        _, text = stores._require_sqlalchemy()  # noqa: SLF001

        stmt = text(
            """
            SELECT
                COUNT(*) FILTER (WHERE repaired_at IS NULL) AS open_gaps,
                COUNT(*) FILTER (WHERE repaired_at > NOW() - INTERVAL '24 hours') AS repaired_24h,
                MIN(expected_open_time) FILTER (WHERE repaired_at IS NULL) AS oldest_open_gap
            FROM candle_gaps
            """
        )

        with engine.begin() as conn:
            row = conn.execute(stmt).fetchone()

        if not row:
            return {"open_gaps": 0, "repaired_24h": 0, "oldest_open_gap": None}

        open_gaps, repaired_24h, oldest_open_gap = row
        oldest_ms = None
        if oldest_open_gap is not None:
            oldest_ms = int(_as_utc(oldest_open_gap).timestamp() * 1000)

        return {
            "open_gaps": int(open_gaps or 0),
            "repaired_24h": int(repaired_24h or 0),
            "oldest_open_gap": oldest_ms,
        }

    except Exception as exc:
        logger.error(f"Gap summary failed: {exc}")
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/system/status")
async def get_system_status() -> dict[str, Any]:
    """Get comprehensive system health status.

    Returns:
        JSON with health status for backend and database, plus a timestamp.

    Example response (JSON representation):
        {
            "backend": {
                "status": "ok",
                "uptime_seconds": 12345
            },
            "database": {
                "status": "ok",
                "connected": true,
                "latency_ms": 2.34
            },
            "timestamp": 1234567890000
        }

    Notes:
        - timestamp is in milliseconds since epoch (for JavaScript compatibility)
        - uptime_seconds is in seconds since application start
        - latency_ms is in milliseconds, rounded to 2 decimal places
        - Returns 200 status even on database errors (errors embedded in response)
    """
    status_response: dict[str, Any] = {
        "backend": {"status": "ok", "uptime_seconds": int(time.time() - _app_start_time)},
        "database": {"status": "error", "connected": False, "latency_ms": None},
        "timestamp": int(time.time() * 1000),
    }

    # Check database connectivity and measure latency
    try:
        stores = _get_stores()
        engine = stores._get_engine()  # noqa: SLF001
        _, text = stores._require_sqlalchemy()  # noqa: SLF001

        # Measure query latency
        start_time = time.perf_counter()
        with engine.begin() as conn:
            # Simple query to check connectivity
            conn.execute(text("SELECT 1")).scalar()
        latency_ms = (time.perf_counter() - start_time) * 1000

        status_response["database"] = {
            "status": "ok",
            "connected": True,
            "latency_ms": round(latency_ms, 2),
        }

    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        status_response["database"] = {
            "status": "error",
            "connected": False,
            "latency_ms": None,
            "error": str(e),
        }

    return status_response


@app.post("/fees/estimate", response_model=FeesEstimateResponse)
async def estimate_fees(payload: FeesEstimateRequest) -> FeesEstimateResponse:
    """Estimate trading costs for a gross notional amount.

    This is a read-only helper endpoint intended for local tools and UI.
    """
    model = FeeModel(
        FeeBreakdown(
            currency=payload.currency,
            maker_fee_rate=payload.maker_fee_rate,
            taker_fee_rate=payload.taker_fee_rate,
            assumed_spread_bps=payload.assumed_spread_bps,
            assumed_slippage_bps=payload.assumed_slippage_bps,
        )
    )

    try:
        estimate = model.estimate_cost(gross_notional=payload.gross_notional, taker=payload.taker)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return FeesEstimateResponse(
        fee_total=estimate.estimated_fees,
        spread_cost=estimate.estimated_spread_cost,
        slippage_cost=estimate.estimated_slippage_cost,
        minimum_edge_rate=estimate.minimum_edge_rate,
        minimum_edge_bps=estimate.minimum_edge_bps,
    )


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


# Alias for /candles/latest - frontend uses /candles
@app.get("/candles")
async def get_candles(
    exchange: str = Query(default="bitfinex", description="Exchange name"),
    symbol: str = Query(..., description="Trading symbol (e.g., BTCUSD)"),
    timeframe: str = Query(..., description="Timeframe (e.g., 1m, 5m, 1h)"),
    limit: int = Query(default=100, ge=1, le=5000, description="Number of candles to return"),
) -> dict[str, Any]:
    """Alias for /candles/latest endpoint."""
    return await get_latest_candles(exchange=exchange, symbol=symbol, timeframe=timeframe, limit=limit)


@app.get("/candles/available")
async def get_available_pairs(
    exchange: str = Query(default="bitfinex", description="Exchange name"),
) -> dict[str, Any]:
    """Get available symbol/timeframe pairs in the database.

    Args:
        exchange: Exchange name (default: bitfinex)

    Returns:
        JSON with list of available symbol/timeframe pairs.
    """
    try:
        stores = _get_stores()
        engine = stores._get_engine()  # noqa: SLF001
        _, text = stores._require_sqlalchemy()  # noqa: SLF001

        stmt = text(
            """
            SELECT DISTINCT symbol, timeframe
            FROM candles
            WHERE exchange = :exchange
            ORDER BY symbol, timeframe
            """
        )

        with engine.connect() as conn:
            result = conn.execute(stmt, {"exchange": exchange})
            pairs = [{"symbol": row[0], "timeframe": row[1]} for row in result]

        return {
            "exchange": exchange,
            "pairs": pairs,
            "count": len(pairs),
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={
                "error": "db_error",
                "detail": str(e),
            },
        ) from e


@app.get("/candles/stream")
async def stream_candles(
    symbol: str = Query(..., description="Trading symbol (e.g., BTCUSD)"),
    timeframe: str = Query(..., description="Timeframe (e.g., 1m, 5m, 1h)"),
) -> StreamingResponse:
    """Stream real-time candle updates via Server-Sent Events (SSE).

    Args:
        symbol: Trading symbol (e.g., BTCUSD)
        timeframe: Candle timeframe (e.g., 1m, 5m, 1h)

    Returns:
        SSE stream with real-time candle updates.

    Example:
        Connect using EventSource in JavaScript:
        ```
        const es = new EventSource('/candles/stream?symbol=BTCUSD&timeframe=1m');
        es.onmessage = (event) => {
            const data = JSON.parse(event.data);
            console.log('New candle:', data);
        };
        ```
    """
    service = get_candle_stream_service()

    async def event_generator():
        """Generate SSE events."""
        try:
            async for candle_data in service.subscribe(symbol, timeframe):
                # Format as SSE event
                yield f"data: {json.dumps(candle_data)}\n\n"
        except Exception as e:
            logger.error(f"Error in SSE stream for {symbol}:{timeframe}: {e}")
            # Send error event
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )


@app.get("/candles/stream/status")
async def get_stream_status() -> dict[str, Any]:
    """Get status of active candle streams.

    Returns:
        JSON with stream connection information.
    """
    service = get_candle_stream_service()
    return service.get_connection_status()


# =============================================================================
# Paper Trading Endpoints
# =============================================================================


class OrderRequest(BaseModel):
    """Request body for placing a paper order."""

    symbol: str = Field(..., min_length=1, description="Trading pair symbol (e.g., BTCUSD)")
    side: Literal["BUY", "SELL"] = Field(..., description="Order side")
    order_type: Literal["market", "limit"] = Field("market", description="Order type")
    qty: Decimal = Field(..., gt=0, description="Order quantity")
    limit_price: Optional[Decimal] = Field(None, gt=0, description="Limit price (required for limit orders)")
    market_price: Optional[Decimal] = Field(None, gt=0, description="Current market price (required for market orders)")


class OrderResponse(BaseModel):
    """Response for order operations."""

    order_id: int
    symbol: str
    side: str
    order_type: str
    qty: str
    limit_price: Optional[str] = None
    status: str
    fill_price: Optional[str] = None
    created_at: Optional[str] = None
    filled_at: Optional[str] = None


class PositionResponse(BaseModel):
    """Response for position queries."""

    symbol: str
    qty: str
    side: str
    avg_entry: str
    unrealized_pnl: str
    realized_pnl: str


def _order_to_response(order: PaperOrder) -> dict[str, Any]:
    """Convert PaperOrder to API response dict."""
    return {
        "order_id": order.order_id,
        "symbol": order.symbol,
        "side": order.side,
        "order_type": order.order_type,
        "qty": str(order.qty),
        "limit_price": str(order.limit_price) if order.limit_price else None,
        "status": order.status,
        "fill_price": str(order.fill_price) if order.fill_price else None,
        "created_at": order.created_at.isoformat() if order.created_at else None,
        "filled_at": order.filled_at.isoformat() if order.filled_at else None,
    }


def _position_to_response(position: PaperPosition, current_price: Decimal) -> dict[str, Any]:
    """Convert PaperPosition to API response dict."""
    executor = _get_paper_executor()
    unrealized = executor.get_unrealized_pnl(position.symbol, current_price)
    side = "LONG" if position.qty > 0 else "SHORT"
    return {
        "symbol": position.symbol,
        "qty": str(abs(position.qty)),
        "side": side,
        "avg_entry": str(position.avg_entry),
        "unrealized_pnl": str(unrealized),
        "realized_pnl": str(position.realized_pnl),
    }


@app.post("/orders")
async def place_order(request: OrderRequest) -> dict[str, Any]:
    """Place a paper trading order.

    Args:
        request: Order details including symbol, side, type, qty, and price.

    Returns:
        The created order details.

    Raises:
        HTTPException: If order validation fails.
    """
    executor = _get_paper_executor()

    try:
        if request.order_type == "market":
            if request.market_price is None:
                raise HTTPException(
                    status_code=400,
                    detail={"error": "validation_error", "message": "market_price required for market orders"},
                )
            order = executor.execute_paper_order(
                symbol=request.symbol,
                side=request.side,
                qty=request.qty,
                order_type="market",
                market_price=request.market_price,
            )
        else:  # limit order
            if request.limit_price is None:
                raise HTTPException(
                    status_code=400,
                    detail={"error": "validation_error", "message": "limit_price required for limit orders"},
                )
            order = executor.execute_paper_order(
                symbol=request.symbol,
                side=request.side,
                qty=request.qty,
                order_type="limit",
                limit_price=request.limit_price,
            )

        return {"success": True, "order": _order_to_response(order)}

    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail={"error": "validation_error", "message": str(e)},
        ) from e


@app.get("/orders")
async def list_orders(
    symbol: Optional[str] = Query(None, description="Filter by symbol"),
    status: Optional[Literal["PENDING", "FILLED", "CANCELLED"]] = Query(None, description="Filter by status"),
) -> dict[str, Any]:
    """List paper trading orders.

    Args:
        symbol: Optional symbol filter.
        status: Optional status filter.

    Returns:
        List of orders matching the filters.
    """
    executor = _get_paper_executor()
    orders = list(executor._orders.values())

    # Apply filters
    if symbol:
        orders = [o for o in orders if o.symbol == symbol]
    if status:
        orders = [o for o in orders if o.status == status]

    return {"orders": [_order_to_response(o) for o in orders]}


@app.delete("/orders/{order_id}")
async def cancel_order(
    order_id: int = Path(..., description="Order ID to cancel"),
) -> dict[str, Any]:
    """Cancel a pending paper order.

    Args:
        order_id: The order ID to cancel.

    Returns:
        Success status and cancelled order details.

    Raises:
        HTTPException: If order not found or already filled.
    """
    executor = _get_paper_executor()

    order = executor.get_order(order_id)
    if order is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "not_found", "message": f"Order {order_id} not found"},
        )

    if order.status != "PENDING":
        raise HTTPException(
            status_code=400,
            detail={"error": "cancel_failed", "message": f"Cannot cancel order with status {order.status}"},
        )

    success = executor.cancel_order(order_id)
    if not success:
        raise HTTPException(
            status_code=400,
            detail={"error": "cancel_failed", "message": "Order could not be cancelled"},
        )

    # Re-fetch order to get updated status
    order = executor.get_order(order_id)
    return {"success": True, "order": _order_to_response(order) if order else None}


@app.get("/positions")
async def list_positions(
    symbol: Optional[str] = Query(None, description="Filter by symbol"),
) -> dict[str, Any]:
    """List open paper trading positions.

    Args:
        symbol: Optional symbol filter.

    Returns:
        List of open positions with P&L calculations.

    Note:
        Unrealized P&L requires a current_price query parameter for accurate calculation.
        If not provided, unrealized P&L will show as 0.
    """
    executor = _get_paper_executor()
    positions = list(executor._positions.values())

    # Apply filter
    if symbol:
        positions = [p for p in positions if p.symbol == symbol]

    # Get current prices for P&L calculation
    result = []
    for pos in positions:
        # Use last known price from executor, or avg_entry as fallback
        current_price = executor.get_last_price(pos.symbol) or pos.avg_entry
        result.append(_position_to_response(pos, current_price))

    return {"positions": result}


@app.post("/positions/{symbol}/close")
async def close_position(
    symbol: str = Path(..., description="Symbol to close"),
    market_price: Decimal = Query(..., gt=0, description="Current market price for closing"),
) -> dict[str, Any]:
    """Close an open position at market price.

    Args:
        symbol: The symbol to close.
        market_price: Current market price for the closing order.

    Returns:
        The closing order details.

    Raises:
        HTTPException: If no position exists for the symbol.
    """
    executor = _get_paper_executor()
    position = executor.get_position(symbol)

    if position is None or position.qty == 0:
        raise HTTPException(
            status_code=404,
            detail={"error": "not_found", "message": f"No open position for {symbol}"},
        )

    # Close position with opposite order
    side: Literal["BUY", "SELL"] = "SELL" if position.qty > 0 else "BUY"
    qty = abs(position.qty)

    order = executor.execute_paper_order(
        symbol=symbol,
        side=side,
        qty=qty,
        order_type="market",
        market_price=market_price,
    )

    return {"success": True, "message": "Position closed", "close_order": _order_to_response(order)}


# =============================================================================
# Market Cap Rankings
# =============================================================================


def _refresh_market_cap_cache() -> dict[str, int]:
    """Fetch and cache market cap rankings from CoinGecko.

    Returns:
        Dictionary mapping symbol to market cap rank.
        Falls back to static rankings on error.
    """
    global _market_cap_cache, _market_cap_cache_time, _market_cap_cache_source

    # Check cache validity inside lock to prevent race conditions
    with _market_cap_cache_lock:
        current_time = time.time()
        if _market_cap_cache and (current_time - _market_cap_cache_time) < MARKET_CAP_CACHE_TTL:
            logger.debug("Using cached market cap data")
            return _market_cap_cache

    # Fetch fresh data
    try:
        logger.info("Fetching market cap data from CoinGecko")
        client = _get_coingecko_client()
        market_cap_map = client.get_market_cap_map(limit=100)

        if market_cap_map:
            with _market_cap_cache_lock:
                _market_cap_cache = market_cap_map
                _market_cap_cache_time = time.time()
                _market_cap_cache_source = "coingecko"
            logger.info(f"Updated market cap cache with {len(market_cap_map)} coins")
            return market_cap_map
        else:
            logger.warning("CoinGecko returned empty data, using fallback")
            with _market_cap_cache_lock:
                _market_cap_cache_source = "fallback"
            return FALLBACK_MARKET_CAP_RANK

    except Exception as e:
        logger.error(f"Failed to fetch market cap data: {e}")
        # Return cached data if available, otherwise fallback
        with _market_cap_cache_lock:
            if _market_cap_cache:
                logger.info("Using stale cache due to API error")
                return _market_cap_cache
            _market_cap_cache_source = "fallback"
        logger.info("Using static fallback rankings")
        return FALLBACK_MARKET_CAP_RANK


@app.get("/market-cap")
async def get_market_cap() -> dict[str, Any]:
    """Get current market cap rankings.

    Returns:
        JSON with market cap rankings and metadata.
        Example:
        {
            "rankings": {"BTC": 1, "ETH": 2, "XRP": 3, ...},
            "cached": true,
            "source": "coingecko",
            "last_updated": 1234567890
        }
    """
    # Get cache timestamp before refresh
    with _market_cap_cache_lock:
        cache_time_before = _market_cap_cache_time

    rankings = _refresh_market_cap_cache()

    # If cache timestamp didn't change, data was served from cache
    with _market_cap_cache_lock:
        using_cache = (_market_cap_cache_time == cache_time_before) and cache_time_before > 0
        source = _market_cap_cache_source

    return {
        "rankings": rankings,
        "cached": using_cache,
        "source": source,
        "last_updated": int(_market_cap_cache_time * 1000) if _market_cap_cache_time > 0 else None,
    }


# =====================================================================# Market Watch & Signals endpoints
# ============================================================================


def _calculate_indicators(closes: list[float]) -> dict[str, Any]:
    """Calculate technical indicators from price data."""
    result: dict[str, Any] = {}

    if len(closes) < 26:
        return result

    # RSI (14 period)
    gains = []
    losses = []
    for i in range(1, len(closes)):
        delta = closes[i] - closes[i - 1]
        gains.append(max(0, delta))
        losses.append(max(0, -delta))

    if len(gains) >= 14:
        avg_gain = sum(gains[-14:]) / 14
        avg_loss = sum(losses[-14:]) / 14
        if avg_loss > 0:
            rs = avg_gain / avg_loss
            result["rsi"] = round(100 - (100 / (1 + rs)), 1)
        else:
            result["rsi"] = 100.0

    # EMA calculations
    def ema(data: list[float], period: int) -> float:
        if len(data) < period:
            return data[-1]
        multiplier = 2 / (period + 1)
        ema_val = sum(data[:period]) / period
        for price in data[period:]:
            ema_val = (price * multiplier) + (ema_val * (1 - multiplier))
        return ema_val

    result["ema_9"] = round(ema(closes, 9), 2)
    result["ema_21"] = round(ema(closes, 21), 2)
    result["price"] = closes[-1]

    # Price change percentages
    if len(closes) >= 2:
        result["change_1"] = round((closes[-1] - closes[-2]) / closes[-2] * 100, 2)
    if len(closes) >= 24:
        result["change_24"] = round((closes[-1] - closes[-24]) / closes[-24] * 100, 2)

    # MACD (12, 26, 9)
    if len(closes) >= 26:
        ema_12 = ema(closes, 12)
        ema_26 = ema(closes, 26)
        macd_line = ema_12 - ema_26
        result["macd"] = round(macd_line, 2)

    return result


def _generate_signals_for_symbol(symbol: str, timeframe: str, indicators: dict[str, Any]) -> dict[str, Any] | None:
    """Generate trading signals from indicators."""
    signals_list: list[dict[str, Any]] = []
    total_score = 0
    side_votes = {"BUY": 0, "SELL": 0}
    score_breakdown: list[dict[str, Any]] = []

    rsi = indicators.get("rsi")
    ema_9 = indicators.get("ema_9")
    ema_21 = indicators.get("ema_21")
    macd = indicators.get("macd")
    price = indicators.get("price")

    # RSI signals
    if rsi is not None:
        if rsi < 30:
            strength = (30 - rsi) / 30
            contribution = strength * 40
            signals_list.append(
                {
                    "code": "RSI_OVERSOLD",
                    "side": "BUY",
                    "strength": round(strength, 2),
                    "value": f"{rsi}",
                    "reason": f"RSI {rsi} < 30 (oversold)",
                }
            )
            total_score += contribution
            side_votes["BUY"] += 2
            score_breakdown.append(
                {
                    "code": "RSI_OVERSOLD",
                    "contribution": round(contribution, 2),
                    "detail": "Oversold RSI adds momentum score",
                }
            )
        elif rsi > 70:
            strength = (rsi - 70) / 30
            contribution = strength * 40
            signals_list.append(
                {
                    "code": "RSI_OVERBOUGHT",
                    "side": "SELL",
                    "strength": round(strength, 2),
                    "value": f"{rsi}",
                    "reason": f"RSI {rsi} > 70 (overbought)",
                }
            )
            total_score += contribution
            side_votes["SELL"] += 2
            score_breakdown.append(
                {
                    "code": "RSI_OVERBOUGHT",
                    "contribution": round(contribution, 2),
                    "detail": "Overbought RSI adds momentum score",
                }
            )
        elif rsi < 40:
            contribution = 10
            signals_list.append(
                {
                    "code": "RSI_LOW",
                    "side": "BUY",
                    "strength": 0.3,
                    "value": f"{rsi}",
                    "reason": f"RSI {rsi} approaching oversold",
                }
            )
            total_score += contribution
            side_votes["BUY"] += 1
            score_breakdown.append(
                {
                    "code": "RSI_LOW",
                    "contribution": contribution,
                    "detail": "RSI trending lower adds mild score",
                }
            )
        elif rsi > 60:
            contribution = 10
            signals_list.append(
                {
                    "code": "RSI_HIGH",
                    "side": "SELL",
                    "strength": 0.3,
                    "value": f"{rsi}",
                    "reason": f"RSI {rsi} approaching overbought",
                }
            )
            total_score += contribution
            side_votes["SELL"] += 1
            score_breakdown.append(
                {
                    "code": "RSI_HIGH",
                    "contribution": contribution,
                    "detail": "RSI trending higher adds mild score",
                }
            )

    # EMA crossover signals
    if ema_9 is not None and ema_21 is not None and price is not None:
        ema_diff_pct = (ema_9 - ema_21) / ema_21 * 100
        if ema_9 > ema_21:
            if ema_diff_pct < 1:  # Recent crossover
                contribution = 25
                signals_list.append(
                    {
                        "code": "EMA_CROSS_UP",
                        "side": "BUY",
                        "strength": 0.6,
                        "value": f"{ema_diff_pct:.2f}%",
                        "reason": "EMA9 crossed above EMA21",
                    }
                )
                total_score += contribution
                side_votes["BUY"] += 2
                score_breakdown.append(
                    {
                        "code": "EMA_CROSS_UP",
                        "contribution": contribution,
                        "detail": "Bullish crossover adds trend score",
                    }
                )
            else:
                contribution = 15
                signals_list.append(
                    {
                        "code": "EMA_BULLISH",
                        "side": "BUY",
                        "strength": 0.4,
                        "value": f"{ema_diff_pct:.2f}%",
                        "reason": "EMA9 > EMA21 (bullish trend)",
                    }
                )
                total_score += contribution
                side_votes["BUY"] += 1
                score_breakdown.append(
                    {
                        "code": "EMA_BULLISH",
                        "contribution": contribution,
                        "detail": "Bullish EMA alignment adds trend score",
                    }
                )
        else:
            if ema_diff_pct > -1:  # Recent crossover
                contribution = 25
                signals_list.append(
                    {
                        "code": "EMA_CROSS_DOWN",
                        "side": "SELL",
                        "strength": 0.6,
                        "value": f"{ema_diff_pct:.2f}%",
                        "reason": "EMA9 crossed below EMA21",
                    }
                )
                total_score += contribution
                side_votes["SELL"] += 2
                score_breakdown.append(
                    {
                        "code": "EMA_CROSS_DOWN",
                        "contribution": contribution,
                        "detail": "Bearish crossover adds trend score",
                    }
                )
            else:
                contribution = 15
                signals_list.append(
                    {
                        "code": "EMA_BEARISH",
                        "side": "SELL",
                        "strength": 0.4,
                        "value": f"{ema_diff_pct:.2f}%",
                        "reason": "EMA9 < EMA21 (bearish trend)",
                    }
                )
                total_score += contribution
                side_votes["SELL"] += 1
                score_breakdown.append(
                    {
                        "code": "EMA_BEARISH",
                        "contribution": contribution,
                        "detail": "Bearish EMA alignment adds trend score",
                    }
                )

    # MACD signals
    if macd is not None:
        if macd > 0:
            contribution = 15
            signals_list.append(
                {
                    "code": "MACD_POSITIVE",
                    "side": "BUY",
                    "strength": min(0.5, abs(macd) / 100),
                    "value": f"{macd}",
                    "reason": f"MACD positive ({macd})",
                }
            )
            total_score += contribution
            side_votes["BUY"] += 1
            score_breakdown.append(
                {
                    "code": "MACD_POSITIVE",
                    "contribution": contribution,
                    "detail": "MACD momentum adds score",
                }
            )
        else:
            contribution = 15
            signals_list.append(
                {
                    "code": "MACD_NEGATIVE",
                    "side": "SELL",
                    "strength": min(0.5, abs(macd) / 100),
                    "value": f"{macd}",
                    "reason": f"MACD negative ({macd})",
                }
            )
            total_score += contribution
            side_votes["SELL"] += 1
            score_breakdown.append(
                {
                    "code": "MACD_NEGATIVE",
                    "contribution": contribution,
                    "detail": "MACD momentum adds score",
                }
            )

    if not signals_list:
        return None

    # Determine overall side
    if side_votes["BUY"] > side_votes["SELL"]:
        side = "BUY"
    elif side_votes["SELL"] > side_votes["BUY"]:
        side = "SELL"
    else:
        side = "HOLD"

    score_explanation = " + ".join(f"{item['code']} ({item['contribution']})" for item in score_breakdown)

    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "score": round(min(100, total_score), 1),
        "side": side,
        "signals": signals_list,
        "price": price,
        "change_24h": indicators.get("change_24"),
        "rsi": rsi,
        "created_at": int(time.time() * 1000),
        "score_breakdown": score_breakdown,
        "score_explanation": score_explanation,
    }


@app.get("/signals")
async def get_signals(
    exchange: str = Query("bitfinex", description="Exchange name"),
    timeframe: str = Query("1h", description="Timeframe for analysis"),
    limit: int = Query(10, ge=1, le=100, description="Max signals to return"),
    include_history: bool = Query(False, description="Include historical analysis details"),
    include_llm: bool = Query(False, description="Include LLM explanation"),
    analysis_limit: int = Query(5, ge=1, le=50, description="Max signals with analysis"),
) -> dict[str, Any]:
    """Get trading signals for all available symbols.

    Scans all symbols and generates signals based on:
    - RSI (oversold/overbought)
    - EMA crossovers (9/21)
    - MACD momentum
    """
    # Validate input parameters to ensure they only contain expected characters
    import re

    if not re.match(r"^[a-z0-9_-]+$", exchange.lower()):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid exchange '{exchange}': must contain only alphanumeric characters, hyphens, and underscores",
        )

    if not re.match(r"^[0-9]+[smhd]$", timeframe.lower()):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid timeframe '{timeframe}': must be a number followed by s/m/h/d (e.g., 1h, 4h, 1d)",
        )

    signals_list: list[dict[str, Any]] = []

    try:
        stores = _get_stores()
        engine = stores._get_engine()  # noqa: SLF001
        _, text = stores._require_sqlalchemy()  # noqa: SLF001

        # Get all available symbols
        symbols_query = text(
            """
            SELECT DISTINCT symbol FROM candles
            WHERE exchange = :exchange AND timeframe = :timeframe
            ORDER BY symbol
        """
        )

        with engine.begin() as conn:
            symbols = [
                row[0]
                for row in conn.execute(
                    symbols_query, {"exchange": exchange.lower(), "timeframe": timeframe}
                ).fetchall()
            ]

        # Analyze each symbol
        for symbol in symbols:
            candle_query = text(
                """
                SELECT EXTRACT(EPOCH FROM open_time) * 1000 as open_time_ms,
                       open, high, low, close, volume
                FROM candles
                WHERE exchange = :exchange AND symbol = :symbol AND timeframe = :timeframe
                ORDER BY open_time DESC
                LIMIT 50
            """
            )

            with engine.begin() as conn:
                rows = conn.execute(
                    candle_query,
                    {"exchange": exchange.lower(), "symbol": symbol, "timeframe": timeframe},
                ).fetchall()

            if len(rows) < 26:
                continue

            closes = [float(r[4]) for r in reversed(rows)]
            indicators = _calculate_indicators(closes)

            signal = _generate_signals_for_symbol(symbol, timeframe, indicators)
            if signal and signal["score"] >= 20:  # Only include signals with meaningful score
                signals_list.append(signal)

        # Sort by score descending
        signals_list.sort(key=lambda x: x["score"], reverse=True)

        if include_llm:
            include_history = True

        if include_history:
            from core.signals.reasoning import SignalReasoner

            reasoner = SignalReasoner(db_url=os.environ.get("DATABASE_URL"))
            llm_analyst = None
            llm_available = False
            if include_llm:
                try:
                    from core.signals.llm import OllamaAnalyst

                    llm_analyst = OllamaAnalyst()
                    llm_available = await llm_analyst.is_available()
                except Exception as e:
                    logger.warning(f"LLM availability check failed: {e}")

            for signal in signals_list[: min(analysis_limit, len(signals_list))]:
                cache_key = _analysis_cache_key(
                    exchange=exchange,
                    symbol=str(signal.get("symbol", "")),
                    timeframe=str(signal.get("timeframe", "")),
                )
                cached = _get_cached_analysis(cache_key)

                analysis_payload: dict[str, Any] | None = None
                if cached and "analysis" in cached:
                    analysis_payload = cached.get("analysis")
                    signal["analysis"] = analysis_payload
                    if include_llm and cached.get("llm"):
                        signal["llm"] = cached.get("llm")

                if analysis_payload is None or (include_llm and "llm" not in signal):
                    try:
                        analysis = await reasoner.analyze(
                            symbol=str(signal.get("symbol", "")),
                            timeframe=str(signal.get("timeframe", "")),
                        )
                        analysis_payload = {
                            "recommendation": analysis.recommendation.value,
                            "confidence": analysis.confidence,
                            "score": analysis.confidence,
                            "reasoning": analysis.reasoning,
                            "bullish_factors": analysis.bullish_factors,
                            "bearish_factors": analysis.bearish_factors,
                            "support_levels": [float(s) for s in analysis.support_levels],
                            "resistance_levels": [float(r) for r in analysis.resistance_levels],
                            "suggested_entry": float(analysis.suggested_entry)
                            if analysis.suggested_entry is not None
                            else None,
                            "suggested_stop": float(analysis.suggested_stop)
                            if analysis.suggested_stop is not None
                            else None,
                            "suggested_target": float(analysis.suggested_target)
                            if analysis.suggested_target is not None
                            else None,
                            "risk_reward_ratio": analysis.risk_reward_ratio,
                            "indicators": {
                                "rsi": analysis.indicators.get("rsi"),
                                "ema_20": analysis.indicators.get("ema_20"),
                                "ema_50": analysis.indicators.get("ema_50"),
                                "ema_200": analysis.indicators.get("ema_200"),
                                "macd": analysis.indicators.get("macd"),
                                "atr_percent": analysis.indicators.get("atr_percent"),
                                "volume_ratio": analysis.indicators.get("volume_ratio"),
                            },
                        }
                        signal["analysis"] = analysis_payload

                        llm_payload: dict[str, Any] | None = None
                        if include_llm:
                            if llm_analyst is not None and llm_available:
                                try:
                                    llm_response = await llm_analyst.explain(analysis)
                                    llm_payload = {
                                        "summary": llm_response.summary,
                                        "explanation": llm_response.detailed_explanation,
                                        "risks": llm_response.risk_assessment,
                                        "confidence": llm_response.confidence_note,
                                        "model": llm_response.model_used,
                                    }
                                except Exception as e:
                                    llm_payload = {
                                        "summary": f"LLM error: {e}",
                                        "explanation": "",
                                        "risks": "",
                                        "confidence": "",
                                        "model": "error",
                                    }
                            else:
                                llm_payload = {
                                    "summary": "LLM not available",
                                    "explanation": "",
                                    "risks": "",
                                    "confidence": "",
                                    "model": "unavailable",
                                }

                        cache_payload = {
                            "timestamp": time.time(),
                            "analysis": analysis_payload,
                        }
                        if llm_payload is not None:
                            cache_payload["llm"] = llm_payload
                        _set_cached_analysis(cache_key, cache_payload)

                        if llm_payload is not None:
                            signal["llm"] = llm_payload
                    except Exception as e:
                        logger.warning(f"Analysis failed for {signal.get('symbol')}: {e}")

    except Exception as e:
        logger.warning(f"Failed to generate signals: {e}")

    return {
        "exchange": exchange,
        "timeframe": timeframe,
        "signals": signals_list[:limit],
        "count": len(signals_list),
        "scanned": len(signals_list),
    }


@app.get("/market-watch")
async def get_market_watch(
    exchange: str = Query("bitfinex", description="Exchange name"),
    timeframe: str = Query("1h", description="Timeframe for analysis"),
) -> dict[str, Any]:
    """Get market watch data for all symbols.

    Returns current prices, 24h changes, and key indicators for each symbol.
    """
    watch_list: list[dict[str, Any]] = []

    try:
        stores = _get_stores()
        engine = stores._get_engine()  # noqa: SLF001
        _, text = stores._require_sqlalchemy()  # noqa: SLF001

        # Get all available symbols
        symbols_query = text(
            """
            SELECT DISTINCT symbol FROM candles
            WHERE exchange = :exchange AND timeframe = :timeframe
            ORDER BY symbol
        """
        )

        with engine.begin() as conn:
            symbols = [
                row[0]
                for row in conn.execute(
                    symbols_query, {"exchange": exchange.lower(), "timeframe": timeframe}
                ).fetchall()
            ]

        for symbol in symbols:
            candle_query = text(
                """
                SELECT EXTRACT(EPOCH FROM open_time) * 1000 as open_time_ms,
                       open, high, low, close, volume
                FROM candles
                WHERE exchange = :exchange AND symbol = :symbol AND timeframe = :timeframe
                ORDER BY open_time DESC
                LIMIT 50
            """
            )

            with engine.begin() as conn:
                rows = conn.execute(
                    candle_query,
                    {"exchange": exchange.lower(), "symbol": symbol, "timeframe": timeframe},
                ).fetchall()

            if len(rows) < 2:
                continue

            closes = [float(r[4]) for r in reversed(rows)]
            volumes = [float(r[5]) for r in reversed(rows)]
            highs = [float(r[3]) for r in reversed(rows)]
            lows = [float(r[2]) for r in reversed(rows)]

            indicators = _calculate_indicators(closes)

            # Calculate 24h high/low
            high_24h = max(highs[-24:]) if len(highs) >= 24 else max(highs)
            low_24h = min(lows[-24:]) if len(lows) >= 24 else min(lows)
            vol_24h = sum(volumes[-24:]) if len(volumes) >= 24 else sum(volumes)

            watch_list.append(
                {
                    "symbol": symbol,
                    "price": closes[-1],
                    "change_1h": indicators.get("change_1", 0),
                    "change_24h": indicators.get("change_24", 0),
                    "high_24h": high_24h,
                    "low_24h": low_24h,
                    "volume_24h": round(vol_24h, 2),
                    "rsi": indicators.get("rsi"),
                    "ema_trend": "bullish" if indicators.get("ema_9", 0) > indicators.get("ema_21", 0) else "bearish",
                    "updated_at": int(rows[0][0]),
                }
            )

        # Sort by 24h change (most volatile first)
        watch_list.sort(key=lambda x: abs(x.get("change_24h", 0)), reverse=True)

    except Exception as e:
        logger.warning(f"Failed to get market watch: {e}")

    return {
        "exchange": exchange,
        "timeframe": timeframe,
        "symbols": watch_list,
        "count": len(watch_list),
    }


@app.get("/gaps/summary")
async def get_gaps_summary(
    exchange: str = Query("bitfinex", description="Exchange name"),
) -> dict[str, Any]:
    """Get gap statistics from candles data.

    Detects gaps by checking for missing expected candles in 1m timeframe.
    """
    open_gaps = 0
    repaired_24h = 0
    oldest_gap: int | None = None

    try:
        stores = _get_stores()
        engine = stores._get_engine()  # noqa: SLF001
        _, text = stores._require_sqlalchemy()  # noqa: SLF001

        # Get gap count by checking for discontinuities in 1m candles
        # A gap exists if next candle timestamp > current + 60 seconds
        gap_query = text(
            """
            WITH candle_gaps AS (
                SELECT
                    open_time,
                    LEAD(open_time) OVER (PARTITION BY symbol ORDER BY open_time) as next_time
                FROM candles
                WHERE exchange = :exchange
                  AND timeframe = '1m'
                  AND open_time > :since
            )
            SELECT
                COUNT(*) as gap_count,
                MIN(EXTRACT(EPOCH FROM open_time) * 1000)::bigint as oldest_gap_time
            FROM candle_gaps
            WHERE EXTRACT(EPOCH FROM (next_time - open_time)) > 120
        """
        )

        # Timestamp for reference (unused currently)
        week_ago = datetime.fromtimestamp(time.time() - 7 * 24 * 60 * 60, tz=timezone.utc)
        day_ago = datetime.fromtimestamp(time.time() - 24 * 60 * 60, tz=timezone.utc)

        with engine.begin() as conn:
            # Count gaps in last 7 days
            result = conn.execute(
                gap_query,
                {
                    "exchange": exchange.lower(),
                    "since": week_ago,
                },
            ).fetchone()

            if result:
                open_gaps = int(result[0] or 0)
                oldest_gap = int(result[1]) if result[1] else None

            # Count "repaired" = candles added in last 24h that filled gaps
            # (simplified: just count new 1m candles in last 24h)
            repair_query = text(
                """
                SELECT COUNT(*) FROM candles
                WHERE exchange = :exchange
                  AND timeframe = '1m'
                  AND open_time BETWEEN :day_ago AND :now
            """
            )
            now_dt = datetime.fromtimestamp(time.time(), tz=timezone.utc)
            repair_result = conn.execute(
                repair_query,
                {
                    "exchange": exchange.lower(),
                    "day_ago": day_ago,
                    "now": now_dt,
                },
            ).fetchone()

            if repair_result:
                # Estimate repairs based on candle density
                expected_candles = 24 * 60  # 1440 candles per day
                actual_candles = int(repair_result[0] or 0)
                if actual_candles > expected_candles:
                    repaired_24h = actual_candles - expected_candles

    except Exception as e:
        logger.warning(f"Failed to get gap stats: {e}")

    return {
        "open_gaps": open_gaps,
        "repaired_24h": repaired_24h,
        "oldest_open_gap": oldest_gap,
    }


@app.get("/api/correlation", tags=["Analysis"])
async def get_correlation_matrix(
    symbols: str = Query(..., description="Comma-separated list of symbols (e.g., BTCUSD,ETHUSD,SOLUSD)"),
    exchange: str = Query("bitfinex", description="Exchange name"),
    timeframe: str = Query("1d", description="Timeframe (1d recommended)"),
    lookback: int = Query(30, ge=7, le=365, description="Lookback period in days (7, 30, 90, 365)"),
):
    """Calculate correlation matrix between assets.

    Returns correlation coefficients between -1 (negative correlation) and +1 (positive correlation).
    Useful for portfolio diversification analysis.

    Results are cached for 5 minutes to reduce computational load.
    Rate limiting should be handled by reverse proxy or API gateway (not implemented at app level).

    Maximum 15 symbols allowed to prevent server overload from expensive matrix calculations.
    """
    import asyncio
    from core.analysis.correlation import calculate_correlation_matrix

    stores = _get_stores()
    if stores is None:
        raise HTTPException(status_code=500, detail="Database not initialized")

    # Validate input parameters to ensure they only contain expected characters
    import re

    if not re.match(r"^[a-z0-9_-]+$", exchange.lower()):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid exchange '{exchange}': must contain only alphanumeric characters, hyphens, and underscores",
        )

    if not re.match(r"^[0-9]+[smhd]$", timeframe.lower()):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid timeframe '{timeframe}': must be a number followed by s/m/h/d (e.g., 1h, 4h, 1d)",
        )

    # Parse symbols and validate input
    symbol_list = [s.strip().upper() for s in symbols.split(",") if s.strip()]

    # Validate symbols contain only alphanumeric characters
    for sym in symbol_list:
        if not re.match(r"^[A-Z0-9]+$", sym):
            raise HTTPException(
                status_code=400, detail=f"Invalid symbol '{sym}': symbols must contain only alphanumeric characters"
            )

    if len(symbol_list) < 2:
        raise HTTPException(status_code=400, detail="Need at least 2 symbols for correlation analysis")

    # Maximum symbol limit to prevent server overload (matches frontend MAX_SYMBOLS=15)
    if len(symbol_list) > 15:
        raise HTTPException(
            status_code=400,
            detail=f"Too many symbols ({len(symbol_list)}): maximum 15 symbols allowed to prevent server overload",
        )

    # Create cache key
    cache_key = f"{','.join(sorted(symbol_list))}:{exchange}:{timeframe}:{lookback}"

    # Check cache
    with _correlation_cache_lock:
        if cache_key in _correlation_cache:
            cached_result, cached_time = _correlation_cache[cache_key]
            age = time.time() - cached_time
            if age < CORRELATION_CACHE_TTL:
                logger.debug(f"Returning cached correlation result (age: {age:.1f}s)")
                return cached_result

    # Calculate correlation (cache miss or expired)
    # Run in thread pool since calculate_correlation_matrix is now synchronous
    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            _executor,  # Use shared thread pool for efficiency
            calculate_correlation_matrix,
            stores,
            symbol_list,
            exchange,
            timeframe,
            lookback,
        )

        # Update cache
        with _correlation_cache_lock:
            _correlation_cache[cache_key] = (result, time.time())
            # Limit cache size to prevent memory issues
            if len(_correlation_cache) > MAX_CACHE_SIZE:
                # Remove oldest entries, keep only the most recent entries
                sorted_items = sorted(_correlation_cache.items(), key=lambda x: x[1][1])
                _correlation_cache.clear()
                _correlation_cache.update(dict(sorted_items[-CACHE_EVICTION_SIZE:]))

        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Correlation calculation failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to calculate correlation matrix")


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


# =============================================================================
# Research / Technical Analysis Endpoints
# =============================================================================


class ResearchRequest(BaseModel):
    """Request body for research endpoint."""

    symbol: str = Field(..., description="Trading symbol (e.g., BTCUSD)")
    timeframe: str = Field("4h", description="Analysis timeframe")
    question: str | None = Field(None, description="Specific question to answer")
    use_llm: bool = Field(False, description="Use LLM for natural language explanation")


class ResearchResponse(BaseModel):
    """Response from research endpoint."""

    symbol: str
    timeframe: str
    recommendation: str
    confidence: int
    current_price: str
    reasoning: list[str]
    bullish_factors: list[str]
    bearish_factors: list[str]
    support_levels: list[str]
    resistance_levels: list[str]
    suggested_entry: str | None
    suggested_stop: str | None
    suggested_target: str | None
    risk_reward_ratio: float | None
    llm_summary: str | None = None
    llm_explanation: str | None = None
    llm_risks: str | None = None


@app.get("/research/{symbol}")
async def get_research(
    symbol: str = Path(..., description="Trading symbol (e.g., BTCUSD)"),
    timeframe: str = Query("4h", description="Analysis timeframe"),
    question: str | None = Query(None, description="Specific question to answer"),
    use_llm: bool = Query(False, description="Use LLM for natural language explanation"),
) -> ResearchResponse:
    """Get comprehensive technical analysis and trading recommendation.

    Analyzes the symbol using:
    - RSI, MACD, Bollinger Bands
    - EMA trend analysis (20/50/200)
    - Support/resistance levels
    - Volume analysis

    Optionally uses Ollama LLM for natural language explanations.

    Args:
        symbol: Trading pair (e.g., BTCUSD)
        timeframe: Candle timeframe for analysis
        question: Optional specific question (e.g., "should I buy now?")
        use_llm: Whether to include LLM-powered explanation

    Returns:
        Comprehensive analysis with recommendation and reasoning
    """
    from core.signals.reasoning import SignalReasoner

    try:
        # Get database URL
        db_url = os.environ.get("DATABASE_URL", "postgresql://localhost/cryptotrader")

        # Run analysis
        reasoner = SignalReasoner(db_url=db_url)
        analysis = await reasoner.analyze(symbol.upper(), timeframe)

        # Prepare response
        response = ResearchResponse(
            symbol=analysis.symbol,
            timeframe=analysis.timeframe,
            recommendation=analysis.recommendation.value,
            confidence=analysis.confidence,
            current_price=f"{analysis.current_price:,.2f}",
            reasoning=analysis.reasoning,
            bullish_factors=analysis.bullish_factors,
            bearish_factors=analysis.bearish_factors,
            support_levels=[f"{s:,.2f}" for s in analysis.support_levels],
            resistance_levels=[f"{r:,.2f}" for r in analysis.resistance_levels],
            suggested_entry=f"{analysis.suggested_entry:,.2f}" if analysis.suggested_entry else None,
            suggested_stop=f"{analysis.suggested_stop:,.2f}" if analysis.suggested_stop else None,
            suggested_target=f"{analysis.suggested_target:,.2f}" if analysis.suggested_target else None,
            risk_reward_ratio=analysis.risk_reward_ratio,
        )

        # Add LLM explanation if requested
        if use_llm:
            try:
                from core.signals.llm import OllamaAnalyst

                analyst = OllamaAnalyst()
                if await analyst.is_available():
                    if question:
                        answer = await analyst.answer_question(analysis, question)
                        response.llm_summary = answer
                    else:
                        llm_response = await analyst.explain(analysis)
                        response.llm_summary = llm_response.summary
                        response.llm_explanation = llm_response.detailed_explanation
                        response.llm_risks = llm_response.risk_assessment
                else:
                    response.llm_summary = "Ollama not available. Install and run: ollama serve"
            except Exception as e:
                logger.warning(f"LLM analysis failed: {e}")
                response.llm_summary = f"LLM unavailable: {e}"

        return response

    except Exception as e:
        logger.exception(f"Research analysis failed for {symbol}")
        raise HTTPException(
            status_code=500,
            detail={"error": "analysis_failed", "message": str(e)},
        ) from e


@app.post("/research")
async def post_research(request: ResearchRequest) -> ResearchResponse:
    """POST version of research endpoint for complex queries.

    Same as GET /research/{symbol} but accepts JSON body.
    """
    return await get_research(
        symbol=request.symbol,
        timeframe=request.timeframe,
        question=request.question,
        use_llm=request.use_llm,
    )


@app.get("/research/llm/status")
async def get_llm_status() -> dict[str, Any]:
    """Check LLM (Ollama) availability and list models.

    Returns:
        Status of Ollama service and available models.
    """
    try:
        from core.signals.llm import check_ollama

        return await check_ollama()
    except Exception as e:
        return {
            "available": False,
            "error": str(e),
            "host": "http://localhost:11434",
        }


# Include new route modules
app.include_router(health_routes.router)
app.include_router(ratelimit.router)
app.include_router(notifications.router)
app.include_router(export_routes.router)
app.include_router(ws_routes.router)
app.include_router(arbitrage_routes.router)
