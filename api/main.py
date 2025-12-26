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

import logging
import os
import threading
import time
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Literal, Optional

from fastapi import FastAPI, HTTPException, Query, Path
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from core.execution.paper import PaperExecutor, PaperOrder, PaperPosition
from core.fees.model import FeeModel
from core.market_cap.coingecko import CoinGeckoClient
from core.storage.postgres.config import PostgresConfig
from core.storage.postgres.stores import PostgresStores
from core.types import FeeBreakdown

logger = logging.getLogger(__name__)

app = FastAPI(
    title="CryptoTrader API",
    description="API for candles, health checks, ingestion status, and paper trading",
    version="1.0.0",
)

# Global store instance (initialized on startup)
_stores: PostgresStores | None = None

# Global paper executor instance (in-memory, no DB persistence)
_paper_executor: PaperExecutor | None = None

# Global CoinGecko client (singleton)
_coingecko_client: CoinGeckoClient | None = None

# Global market cap cache
_market_cap_cache: dict[str, int] = {}
_market_cap_cache_time: float = 0
_market_cap_cache_lock = threading.Lock()
MARKET_CAP_CACHE_TTL = 600  # 10 minutes in seconds

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
    global _market_cap_cache, _market_cap_cache_time

    current_time = time.time()

    # Return cached data if still valid
    with _market_cap_cache_lock:
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
                _market_cap_cache_time = current_time
            logger.info(f"Updated market cap cache with {len(market_cap_map)} coins")
            return market_cap_map
        else:
            logger.warning("CoinGecko returned empty data, using fallback")
            return FALLBACK_MARKET_CAP_RANK

    except Exception as e:
        logger.error(f"Failed to fetch market cap data: {e}")
        # Return cached data if available, otherwise fallback
        with _market_cap_cache_lock:
            if _market_cap_cache:
                logger.info("Using stale cache due to API error")
                return _market_cap_cache
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

    # Determine source
    source = "coingecko" if rankings != FALLBACK_MARKET_CAP_RANK else "fallback"

    return {
        "rankings": rankings,
        "cached": using_cache,
        "source": source,
        "last_updated": int(_market_cap_cache_time * 1000) if _market_cap_cache_time > 0 else None,
    }


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
