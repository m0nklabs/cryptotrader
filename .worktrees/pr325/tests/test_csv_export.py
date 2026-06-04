"""Tests for CSV export utilities."""

from core.export.csv import export_ohlcv_to_csv, export_trades_to_csv, export_positions_to_csv


def test_export_ohlcv_to_csv():
    """Test exporting OHLCV candles to CSV."""
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

    result = export_ohlcv_to_csv(candles, "BTCUSD", "bitfinex", "1h")

    # Check metadata comments
    assert "# Symbol: BTCUSD" in result
    assert "# Exchange: bitfinex" in result
    assert "# Timeframe: 1h" in result
    assert "# Rows: 2" in result

    # Check header
    assert "timestamp,open,high,low,close,volume" in result

    # Check data rows
    assert "2024-01-01T00:00:00Z,50000.0,50500.0,49500.0,50200.0,1000.0" in result
    assert "2024-01-01T01:00:00Z,50200.0,50800.0,50000.0,50600.0,1200.0" in result


def test_export_trades_to_csv():
    """Test exporting trades to CSV."""
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

    result = export_trades_to_csv(trades)

    # Check metadata
    assert "# Rows: 1" in result

    # Check header
    assert "timestamp,symbol,side,size,price,fee,order_id" in result

    # Check data
    assert "2024-01-01T12:00:00Z,BTCUSD,buy,0.1,50000.0,5.0,order_123" in result


def test_export_positions_to_csv():
    """Test exporting positions to CSV."""
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

    result = export_positions_to_csv(positions)

    # Check metadata
    assert "# Rows: 1" in result

    # Check header
    assert "symbol,side,size,entry_price,current_price,pnl,pnl_percent" in result

    # Check data
    assert "BTCUSD,long,0.1,50000.0,51000.0,100.0,2.0" in result


def test_export_empty_candles():
    """Test exporting empty candles list."""
    result = export_ohlcv_to_csv([], "BTCUSD", "bitfinex", "1h")

    assert "# Rows: 0" in result
    assert "timestamp,open,high,low,close,volume" in result
