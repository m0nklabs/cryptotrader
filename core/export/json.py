"""JSON export utilities for market data and trades."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any


def export_ohlcv_to_json(
    candles: list[dict[str, Any]],
    symbol: str,
    exchange: str,
    timeframe: str,
) -> str:
    """Export OHLCV candles to JSON format.

    Args:
        candles: List of candle dicts
        symbol: Trading symbol
        exchange: Exchange name
        timeframe: Timeframe

    Returns:
        JSON string with metadata and data
    """
    output = {
        "metadata": {
            "symbol": symbol,
            "exchange": exchange,
            "timeframe": timeframe,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "row_count": len(candles),
        },
        "data": candles,
    }

    return json.dumps(output, indent=2)


def export_trades_to_json(trades: list[dict[str, Any]]) -> str:
    """Export trade history to JSON format.

    Args:
        trades: List of trade dicts

    Returns:
        JSON string with metadata and data
    """
    output = {
        "metadata": {
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "row_count": len(trades),
        },
        "data": trades,
    }

    return json.dumps(output, indent=2)


def export_portfolio_to_json(
    positions: list[dict[str, Any]], summary: dict[str, Any]
) -> str:
    """Export portfolio snapshot to JSON format.

    Args:
        positions: List of position dicts
        summary: Portfolio summary dict (total_value, pnl, etc.)

    Returns:
        JSON string with metadata, summary, and positions
    """
    output = {
        "metadata": {
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "position_count": len(positions),
        },
        "summary": summary,
        "positions": positions,
    }

    return json.dumps(output, indent=2)
