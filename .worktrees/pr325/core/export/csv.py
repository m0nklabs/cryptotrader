"""CSV export utilities for market data and trades."""

from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from typing import Any


def export_ohlcv_to_csv(
    candles: list[dict[str, Any]],
    symbol: str,
    exchange: str,
    timeframe: str,
) -> str:
    """Export OHLCV candles to CSV format.

    Args:
        candles: List of candle dicts with keys: open_time, open, high, low, close, volume
        symbol: Trading symbol
        exchange: Exchange name
        timeframe: Timeframe (e.g., "1h", "1d")

    Returns:
        CSV string with headers
    """
    output = io.StringIO()
    writer = csv.writer(output)

    # Write metadata as comments
    output.write(f"# Symbol: {symbol}\n")
    output.write(f"# Exchange: {exchange}\n")
    output.write(f"# Timeframe: {timeframe}\n")
    output.write(f"# Exported: {datetime.now(timezone.utc).isoformat()}\n")
    output.write(f"# Rows: {len(candles)}\n")

    # Write header
    writer.writerow(["timestamp", "open", "high", "low", "close", "volume"])

    # Write data rows
    for candle in candles:
        writer.writerow(
            [
                candle.get("open_time", ""),
                candle.get("open", ""),
                candle.get("high", ""),
                candle.get("low", ""),
                candle.get("close", ""),
                candle.get("volume", ""),
            ]
        )

    return output.getvalue()


def export_trades_to_csv(trades: list[dict[str, Any]]) -> str:
    """Export trade history to CSV format.

    Args:
        trades: List of trade dicts

    Returns:
        CSV string with headers
    """
    output = io.StringIO()
    writer = csv.writer(output)

    # Write metadata
    output.write(f"# Exported: {datetime.now(timezone.utc).isoformat()}\n")
    output.write(f"# Rows: {len(trades)}\n")

    # Write header
    writer.writerow(["timestamp", "symbol", "side", "size", "price", "fee", "order_id"])

    # Write data rows
    for trade in trades:
        writer.writerow(
            [
                trade.get("timestamp", ""),
                trade.get("symbol", ""),
                trade.get("side", ""),
                trade.get("size", ""),
                trade.get("price", ""),
                trade.get("fee", ""),
                trade.get("order_id", ""),
            ]
        )

    return output.getvalue()


def export_positions_to_csv(positions: list[dict[str, Any]]) -> str:
    """Export portfolio positions to CSV format.

    Args:
        positions: List of position dicts

    Returns:
        CSV string with headers
    """
    output = io.StringIO()
    writer = csv.writer(output)

    # Write metadata
    output.write(f"# Exported: {datetime.now(timezone.utc).isoformat()}\n")
    output.write(f"# Rows: {len(positions)}\n")

    # Write header
    writer.writerow(["symbol", "side", "size", "entry_price", "current_price", "pnl", "pnl_percent"])

    # Write data rows
    for pos in positions:
        writer.writerow(
            [
                pos.get("symbol", ""),
                pos.get("side", ""),
                pos.get("size", ""),
                pos.get("entry_price", ""),
                pos.get("current_price", ""),
                pos.get("pnl", ""),
                pos.get("pnl_percent", ""),
            ]
        )

    return output.getvalue()
