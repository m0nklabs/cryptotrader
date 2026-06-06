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

    # Mock walk-forward result with OOS data
    mock_wf_result = MagicMock()
    mock_wf_result.n_folds = 2
    mock_wf_result.mean_train_return = 0.08
    mock_wf_result.mean_test_return = 0.06
    mock_wf_result.mean_oos_decay = 0.75
    mock_wf_result.in_sample_consistency = 0.85
    mock_wf_result.oos_significant = True
    mock_wf_result.oos_sharpe = 1.2
    mock_wf_result.oos_max_dd = 0.04
    mock_wf_result.oos_win_rate = 0.65
    mock_wf_result.overfitting_risk = "low"
    mock_wf_result.oos_trades = [
        {"entry_price": 50000.0, "exit_price": 51000.0, "side": "BUY", "size": 1.0, "pnl": 1000.0},
        {"entry_price": 50200.0, "exit_price": 50800.0, "side": "BUY", "size": 0.5, "pnl": 300.0},
    ]
    mock_wf_result.oos_returns = [0.1, 0.06]
    mock_wf_result.total_oos_trades = 2
    mock_wf_result.folds = [
        MagicMock(
            train_start=now - timedelta(days=90),
            train_end=now - timedelta(days=60),
            test_start=now - timedelta(days=60),
            test_end=now - timedelta(days=30),
            train_return=0.08,
            test_return=0.06,
            test_sharpe=1.2,
            test_max_dd=0.04,
            test_win_rate=0.65,
            test_trades=3,
            oos_decay=0.75,
            oos_trades=[{"entry_price": 50000.0, "exit_price": 51000.0, "side": "BUY", "size": 1.0, "pnl": 1000.0}],
            oos_returns=[0.1],
        ),
        MagicMock(
            train_start=now - timedelta(days=60),
            train_end=now - timedelta(days=30),
            test_start=now - timedelta(days=30),
            test_end=now,
            train_return=0.07,
            test_return=0.05,
            test_sharpe=1.0,
            test_max_dd=0.03,
            test_win_rate=0.6,
            test_trades=2,
            oos_decay=0.71,
            oos_trades=[{"entry_price": 50200.0, "exit_price": 50800.0, "side": "BUY", "size": 0.5, "pnl": 300.0}],
            oos_returns=[0.06],
        ),
    ]

    with patch("api.routes.backtest.BacktestEngine.run", return_value=mock_result), \
         patch("api.routes.backtest.run_walk_forward", return_value=mock_wf_result):
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

    # Check OOS fields at aggregate level (walk_forward)
    wf = data["walk_forward"]
    assert "oos_trades" in wf
    assert "oos_returns" in wf
    assert "total_oos_trades" in wf
    assert isinstance(wf["oos_trades"], list)
    assert isinstance(wf["oos_returns"], list)
    assert wf["total_oos_trades"] == len(wf["oos_trades"])

    # Check OOS fields at fold level
    assert len(wf["folds"]) > 0
    for fold in wf["folds"]:
        assert "oos_trades" in fold
        assert "oos_returns" in fold
        assert isinstance(fold["oos_trades"], list)
        assert isinstance(fold["oos_returns"], list)


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


@patch("api.routes.backtest._get_stores")
def test_run_backtest_oos_fields(mock_get_stores):
    """Test OOS fields in backtest API response at aggregate and fold levels."""
    from core.types import Candle

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

    mock_wf_result = MagicMock()
    mock_wf_result.n_folds = 2
    mock_wf_result.mean_train_return = 0.08
    mock_wf_result.mean_test_return = 0.06
    mock_wf_result.mean_oos_decay = 0.75
    mock_wf_result.in_sample_consistency = 0.85
    mock_wf_result.oos_significant = True
    mock_wf_result.oos_sharpe = 1.2
    mock_wf_result.oos_max_dd = 0.04
    mock_wf_result.oos_win_rate = 0.65
    mock_wf_result.overfitting_risk = "low"
    mock_wf_result.oos_trades = [
        {"entry_price": 50000.0, "exit_price": 51000.0, "side": "BUY", "size": 1.0, "pnl": 1000.0},
        {"entry_price": 50200.0, "exit_price": 50800.0, "side": "BUY", "size": 0.5, "pnl": 300.0},
    ]
    mock_wf_result.oos_returns = [0.1, 0.06]
    mock_wf_result.total_oos_trades = 2
    mock_wf_result.folds = [
        MagicMock(
            train_start=now - timedelta(days=90),
            train_end=now - timedelta(days=60),
            test_start=now - timedelta(days=60),
            test_end=now - timedelta(days=30),
            train_return=0.08,
            test_return=0.06,
            test_sharpe=1.2,
            test_max_dd=0.04,
            test_win_rate=0.65,
            test_trades=3,
            oos_decay=0.75,
            oos_trades=[{"entry_price": 50000.0, "exit_price": 51000.0, "side": "BUY", "size": 1.0, "pnl": 1000.0}],
            oos_returns=[0.1],
        ),
        MagicMock(
            train_start=now - timedelta(days=60),
            train_end=now - timedelta(days=30),
            test_start=now - timedelta(days=30),
            test_end=now,
            train_return=0.07,
            test_return=0.05,
            test_sharpe=1.0,
            test_max_dd=0.03,
            test_win_rate=0.6,
            test_trades=2,
            oos_decay=0.71,
            oos_trades=[{"entry_price": 50200.0, "exit_price": 50800.0, "side": "BUY", "size": 0.5, "pnl": 300.0}],
            oos_returns=[0.06],
        ),
    ]

    with patch("api.routes.backtest.BacktestEngine.run", return_value=mock_result), \
         patch("api.routes.backtest.run_walk_forward", return_value=mock_wf_result):
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

    assert response.status_code == 200
    data = response.json()
    wf = data["walk_forward"]

    # Aggregate OOS assertions
    assert wf["oos_trades"] == mock_wf_result.oos_trades
    assert wf["oos_returns"] == mock_wf_result.oos_returns
    assert wf["total_oos_trades"] == 2
    assert wf["total_oos_trades"] == len(wf["oos_trades"])

    # Fold-level OOS assertions
    assert len(wf["folds"]) == 2
    for i, fold in enumerate(wf["folds"]):
        assert fold["oos_trades"] == mock_wf_result.folds[i].oos_trades
        assert fold["oos_returns"] == mock_wf_result.folds[i].oos_returns
        assert isinstance(fold["oos_trades"], list)
        assert isinstance(fold["oos_returns"], list)
        assert len(fold["oos_trades"]) > 0
        assert len(fold["oos_returns"]) > 0


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
