"""API routes for data export."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional
from fastapi import APIRouter, Query
from fastapi.responses import Response

from core.export import (
    export_ohlcv_to_csv,
    export_ohlcv_to_json,
    export_trades_to_csv,
    export_trades_to_json,
    export_positions_to_csv,
    export_portfolio_to_json,
)

router = APIRouter(prefix="/export", tags=["export"])


@router.get("/candles")
async def export_candles(
    symbol: str = Query(..., description="Trading symbol"),
    exchange: str = Query("bitfinex", description="Exchange name"),
    timeframe: str = Query("1h", description="Timeframe"),
    format: Literal["csv", "json"] = Query("csv", description="Export format"),
    start: Optional[str] = Query(None, description="Start date (ISO format)"),
    end: Optional[str] = Query(None, description="End date (ISO format)"),
):
    """Export OHLCV candles to CSV or JSON.

    Downloads candles for the specified symbol, exchange, and timeframe.
    Optionally filter by date range.
    """
    # TODO: Query database for candles
    # For now, return sample data
    sample_candles = [
        {
            "open_time": "2024-01-01T00:00:00Z",
            "open": 50000.0,
            "high": 50500.0,
            "low": 49500.0,
            "close": 50200.0,
            "volume": 1000.0,
        },
        {
            "open_time": "2024-01-01T01:00:00Z",
            "open": 50200.0,
            "high": 50800.0,
            "low": 50000.0,
            "close": 50600.0,
            "volume": 1200.0,
        },
    ]

    # Generate export
    if format == "csv":
        content = export_ohlcv_to_csv(
            candles=sample_candles,
            symbol=symbol,
            exchange=exchange,
            timeframe=timeframe,
        )
        media_type = "text/csv"
        extension = "csv"
    else:
        content = export_ohlcv_to_json(
            candles=sample_candles,
            symbol=symbol,
            exchange=exchange,
            timeframe=timeframe,
        )
        media_type = "application/json"
        extension = "json"

    # Generate filename
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = f"{symbol}_{exchange}_{timeframe}_{timestamp}.{extension}"

    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/trades")
async def export_trades(
    format: Literal["csv", "json"] = Query("csv", description="Export format"),
    start: Optional[str] = Query(None, description="Start date (ISO format)"),
    end: Optional[str] = Query(None, description="End date (ISO format)"),
):
    """Export trade history to CSV or JSON.

    Downloads all trades, optionally filtered by date range.
    """
    # TODO: Query database for trades
    # For now, return sample data
    sample_trades = [
        {
            "timestamp": "2024-01-01T12:00:00Z",
            "symbol": "BTCUSD",
            "side": "buy",
            "size": 0.1,
            "price": 50000.0,
            "fee": 5.0,
            "order_id": "order_123",
        },
    ]

    # Generate export
    if format == "csv":
        content = export_trades_to_csv(trades=sample_trades)
        media_type = "text/csv"
        extension = "csv"
    else:
        content = export_trades_to_json(trades=sample_trades)
        media_type = "application/json"
        extension = "json"

    # Generate filename
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = f"trades_{timestamp}.{extension}"

    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/portfolio")
async def export_portfolio(
    format: Literal["csv", "json"] = Query("csv", description="Export format"),
):
    """Export current portfolio snapshot to CSV or JSON.

    Downloads current positions and portfolio summary.
    """
    # TODO: Get actual portfolio data
    # For now, return sample data
    sample_positions = [
        {
            "symbol": "BTCUSD",
            "side": "long",
            "size": 0.1,
            "entry_price": 50000.0,
            "current_price": 51000.0,
            "pnl": 100.0,
            "pnl_percent": 2.0,
        },
    ]

    sample_summary = {
        "total_value": 5100.0,
        "total_pnl": 100.0,
        "total_pnl_percent": 2.0,
        "position_count": 1,
    }

    # Generate export
    if format == "csv":
        content = export_positions_to_csv(positions=sample_positions)
        media_type = "text/csv"
        extension = "csv"
    else:
        content = export_portfolio_to_json(positions=sample_positions, summary=sample_summary)
        media_type = "application/json"
        extension = "json"

    # Generate filename
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = f"portfolio_{timestamp}.{extension}"

    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
