"""Tests for the /export API endpoints."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """Create a test client."""
    from api.main import app

    return TestClient(app)


def test_export_candles_csv(client):
    """Test /export/candles with CSV format."""
    response = client.get(
        "/export/candles",
        params={
            "symbol": "BTCUSD",
            "exchange": "bitfinex",
            "timeframe": "1h",
            "format": "csv",
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "text/csv; charset=utf-8"

    # Check Content-Disposition header for filename
    content_disposition = response.headers.get("content-disposition", "")
    assert "attachment" in content_disposition
    assert "BTCUSD_bitfinex_1h" in content_disposition
    assert ".csv" in content_disposition

    # Check that response contains CSV data
    content = response.text
    assert "timestamp" in content  # CSV header uses "timestamp", not "open_time"
    assert "open,high,low,close,volume" in content
    assert "50000" in content  # Sample data value


def test_export_candles_json(client):
    """Test /export/candles with JSON format."""
    response = client.get(
        "/export/candles",
        params={
            "symbol": "ETHUSD",
            "exchange": "kraken",
            "timeframe": "15m",
            "format": "json",
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"

    # Check Content-Disposition header
    content_disposition = response.headers.get("content-disposition", "")
    assert "attachment" in content_disposition
    assert "ETHUSD_kraken_15m" in content_disposition
    assert ".json" in content_disposition

    # Check that response contains valid JSON
    data = response.json()
    assert "metadata" in data
    assert "data" in data
    assert data["metadata"]["symbol"] == "ETHUSD"
    assert data["metadata"]["exchange"] == "kraken"
    assert data["metadata"]["timeframe"] == "15m"
    assert isinstance(data["data"], list)
    assert len(data["data"]) > 0


def test_export_candles_requires_symbol(client):
    """Test that symbol parameter is required."""
    response = client.get(
        "/export/candles",
        params={
            "exchange": "bitfinex",
            "format": "csv",
        },
    )

    # Should return 422 for missing required parameter
    assert response.status_code == 422


def test_export_candles_with_date_params(client):
    """Test /export/candles returns 501 when date parameters are provided."""
    response = client.get(
        "/export/candles",
        params={
            "symbol": "BTCUSD",
            "exchange": "bitfinex",
            "timeframe": "1h",
            "format": "csv",
            "start": "2024-01-01T00:00:00Z",
            "end": "2024-01-31T23:59:59Z",
        },
    )

    # Should return 501 Not Implemented since date filtering is not yet implemented
    assert response.status_code == 501
    data = response.json()
    assert "not yet implemented" in data["detail"].lower()


def test_export_trades_csv(client):
    """Test /export/trades with CSV format."""
    response = client.get(
        "/export/trades",
        params={"format": "csv"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "text/csv; charset=utf-8"

    # Check filename
    content_disposition = response.headers.get("content-disposition", "")
    assert "attachment" in content_disposition
    assert "trades_" in content_disposition
    assert ".csv" in content_disposition

    # Check CSV content
    content = response.text
    assert "timestamp" in content
    assert "symbol,side,size,price" in content


def test_export_trades_json(client):
    """Test /export/trades with JSON format."""
    response = client.get(
        "/export/trades",
        params={"format": "json"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"

    # Check filename
    content_disposition = response.headers.get("content-disposition", "")
    assert "trades_" in content_disposition
    assert ".json" in content_disposition

    # Check JSON structure
    data = response.json()
    assert "metadata" in data
    assert "data" in data
    assert "exported_at" in data["metadata"]
    assert "row_count" in data["metadata"]
    assert isinstance(data["data"], list)


def test_export_trades_with_date_params(client):
    """Test /export/trades returns 501 when date parameters are provided."""
    response = client.get(
        "/export/trades",
        params={
            "format": "csv",
            "start": "2024-01-01T00:00:00Z",
            "end": "2024-01-31T23:59:59Z",
        },
    )

    # Should return 501 Not Implemented
    assert response.status_code == 501
    data = response.json()
    assert "not yet implemented" in data["detail"].lower()


def test_export_portfolio_csv(client):
    """Test /export/portfolio with CSV format."""
    response = client.get(
        "/export/portfolio",
        params={"format": "csv"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "text/csv; charset=utf-8"

    # Check filename
    content_disposition = response.headers.get("content-disposition", "")
    assert "attachment" in content_disposition
    assert "portfolio_" in content_disposition
    assert ".csv" in content_disposition

    # Check CSV content
    content = response.text
    assert "symbol" in content
    assert "side" in content


def test_export_portfolio_json(client):
    """Test /export/portfolio with JSON format."""
    response = client.get(
        "/export/portfolio",
        params={"format": "json"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"

    # Check filename
    content_disposition = response.headers.get("content-disposition", "")
    assert "portfolio_" in content_disposition
    assert ".json" in content_disposition

    # Check JSON structure
    data = response.json()
    assert "metadata" in data
    assert "positions" in data
    assert "summary" in data
    assert "exported_at" in data["metadata"]
    assert "position_count" in data["metadata"]
    assert isinstance(data["positions"], list)
    assert isinstance(data["summary"], dict)


def test_export_format_validation(client):
    """Test that invalid format parameter is rejected."""
    response = client.get(
        "/export/candles",
        params={
            "symbol": "BTCUSD",
            "format": "xml",  # Invalid format
        },
    )

    # Should return 422 for invalid enum value
    assert response.status_code == 422


def test_export_candles_default_values(client):
    """Test that default values work for optional parameters."""
    response = client.get(
        "/export/candles",
        params={
            "symbol": "BTCUSD",
            # exchange defaults to "bitfinex"
            # timeframe defaults to "1h"
            # format defaults to "csv"
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "text/csv; charset=utf-8"

    # Check that default values are used in filename
    content_disposition = response.headers.get("content-disposition", "")
    assert "bitfinex" in content_disposition
    assert "1h" in content_disposition


def test_export_trades_default_format(client):
    """Test that format defaults to CSV."""
    response = client.get("/export/trades")

    assert response.status_code == 200
    assert response.headers["content-type"] == "text/csv; charset=utf-8"


def test_export_portfolio_default_format(client):
    """Test that format defaults to CSV."""
    response = client.get("/export/portfolio")

    assert response.status_code == 200
    assert response.headers["content-type"] == "text/csv; charset=utf-8"
