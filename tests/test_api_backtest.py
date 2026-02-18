"""Tests for backtest API endpoints."""

from pathlib import Path
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient

from api.main import app
from core.backtest.engine import BacktestResult
from core.backtest.metrics import Trade

client = TestClient(app, raise_server_exceptions=True)


def test_list_strategies():
    """Test listing available strategies."""
    response = client.get("/backtest/strategies")
    assert response.status_code == 200

    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0

    # Check RSI strategy is present
    rsi_strategy = next((s for s in data if s["name"] == "rsi"), None)
    assert rsi_strategy is not None
    assert "description" in rsi_strategy
    assert "parameters" in rsi_strategy


@patch("api.routes.backtest._get_stores")
def test_run_backtest_no_data(mock_get_stores):
    """Test backtest with no historical data returns 404."""
    # Mock empty candles
    mock_stores = MagicMock()
    mock_stores.get_candles.return_value = []
    mock_get_stores.return_value = mock_stores

    response = client.post(
        "/backtest/run",
        json={
            "symbol": "BTCUSD",
            "exchange": "bitfinex",
            "strategy": "rsi",
        },
    )

    assert response.status_code == 404
    data = response.json()
    assert "error" in data["detail"]
    assert data["detail"]["error"] == "no_data"


@patch("api.routes.backtest._get_stores")
def test_run_backtest_success(mock_get_stores):
    """Test successful backtest execution."""
    from core.types import Candle

    # Mock candles data
    now = datetime.now(timezone.utc)
    candles = [
        Candle(
            exchange="bitfinex",
            symbol="BTCUSD",
            timeframe="1h",
            open_time=now - timedelta(hours=i),
            close_time=now - timedelta(hours=i - 1),
            open=Decimal("50000"),
            high=Decimal("51000"),
            low=Decimal("49000"),
            close=Decimal("50500"),
            volume=Decimal("100"),
        )
        for i in range(100, 0, -1)
    ]

    mock_stores = MagicMock()
    mock_stores.get_candles.return_value = candles
    mock_get_stores.return_value = mock_stores

    # Mock backtest result
    mock_result = BacktestResult(
        trades=[
            Trade(
                entry_price=Decimal("50000"),
                exit_price=Decimal("51000"),
                side="BUY",
                size=Decimal("1.0"),
            ),
        ],
        equity_curve=[10000.0, 11000.0],
        total_pnl=1000.0,
        total_return=0.1,
        sharpe_ratio=1.5,
        max_drawdown=0.05,
        win_rate=1.0,
        profit_factor=2.0,
    )

    with patch("api.routes.backtest.BacktestEngine.run", return_value=mock_result):
        response = client.post(
            "/backtest/run",
            json={
                "symbol": "BTCUSD",
                "exchange": "bitfinex",
                "strategy": "rsi",
                "initial_capital": 10000.0,
                "rsi_oversold": 30.0,
                "rsi_overbought": 70.0,
            },
        )

    if response.status_code != 200:
        print(f"Error response: {response.json()}")

    assert response.status_code == 200
    data = response.json()

    # Check response structure
    assert data["symbol"] == "BTCUSD"
    assert data["exchange"] == "bitfinex"
    assert data["strategy"] == "rsi"
    assert data["initial_capital"] == 10000.0

    # Check metrics
    assert data["total_pnl"] == 1000.0
    assert data["total_return"] == 0.1
    assert data["sharpe_ratio"] == 1.5
    assert data["max_drawdown"] == 0.05
    assert data["win_rate"] == 1.0
    assert data["profit_factor"] == 2.0

    # Check trades
    assert data["num_trades"] == 1
    assert len(data["trades"]) == 1
    assert data["trades"][0]["side"] == "BUY"

    # Check equity curve
    assert len(data["equity_curve"]) == 2


def test_run_backtest_invalid_strategy():
    """Test backtest with invalid strategy name."""
    response = client.post(
        "/backtest/run",
        json={
            "symbol": "BTCUSD",
            "exchange": "bitfinex",
            "strategy": "invalid_strategy",
        },
    )

    assert response.status_code == 422  # Validation error from Pydantic


def test_run_backtest_with_date_range():
    """Test backtest with custom date range."""
    start_date = "2024-01-01T00:00:00Z"
    end_date = "2024-01-31T23:59:59Z"

    with patch("api.routes.backtest._get_stores") as mock_get_stores:
        mock_stores = MagicMock()
        mock_stores.get_candles.return_value = []
        mock_get_stores.return_value = mock_stores

        response = client.post(
            "/backtest/run",
            json={
                "symbol": "BTCUSD",
                "exchange": "bitfinex",
                "strategy": "rsi",
                "start_date": start_date,
                "end_date": end_date,
            },
        )

        # Should fail with no data, but date parsing should work
        assert response.status_code == 404


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
