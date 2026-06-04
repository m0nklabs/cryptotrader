"""Tests for JSON export utilities."""

import json
from core.export.json import export_ohlcv_to_json, export_trades_to_json, export_portfolio_to_json


def test_export_ohlcv_to_json():
    """Test exporting OHLCV candles to JSON."""
    candles = [
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

    result = export_ohlcv_to_json(candles, "BTCUSD", "bitfinex", "1h")
    data = json.loads(result)

    # Check metadata
    assert data["metadata"]["symbol"] == "BTCUSD"
    assert data["metadata"]["exchange"] == "bitfinex"
    assert data["metadata"]["timeframe"] == "1h"
    assert data["metadata"]["row_count"] == 2
    assert "exported_at" in data["metadata"]

    # Check data
    assert len(data["data"]) == 2
    assert data["data"][0]["open"] == 50000.0
    assert data["data"][1]["close"] == 50600.0


def test_export_trades_to_json():
    """Test exporting trades to JSON."""
    trades = [
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

    result = export_trades_to_json(trades)
    data = json.loads(result)

    # Check metadata
    assert data["metadata"]["row_count"] == 1
    assert "exported_at" in data["metadata"]

    # Check data
    assert len(data["data"]) == 1
    assert data["data"][0]["symbol"] == "BTCUSD"
    assert data["data"][0]["side"] == "buy"


def test_export_portfolio_to_json():
    """Test exporting portfolio to JSON."""
    positions = [
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

    summary = {
        "total_value": 5100.0,
        "total_pnl": 100.0,
        "total_pnl_percent": 2.0,
        "position_count": 1,
    }

    result = export_portfolio_to_json(positions, summary)
    data = json.loads(result)

    # Check metadata
    assert data["metadata"]["position_count"] == 1
    assert "exported_at" in data["metadata"]

    # Check summary
    assert data["summary"]["total_value"] == 5100.0
    assert data["summary"]["total_pnl"] == 100.0

    # Check positions
    assert len(data["positions"]) == 1
    assert data["positions"][0]["symbol"] == "BTCUSD"


def test_export_empty_candles_json():
    """Test exporting empty candles list to JSON."""
    result = export_ohlcv_to_json([], "BTCUSD", "bitfinex", "1h")
    data = json.loads(result)

    assert data["metadata"]["row_count"] == 0
    assert data["data"] == []
