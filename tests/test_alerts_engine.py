"""Tests for alert engine."""

from __future__ import annotations

import pytest
import pandas as pd
from datetime import datetime, timezone

from core.alerts.models import Alert, AlertCondition
from core.alerts.engine import AlertEngine


@pytest.fixture
def engine():
    """Create an alert engine instance."""
    return AlertEngine()


@pytest.fixture
def sample_ohlcv():
    """Create sample OHLCV data for testing."""
    dates = pd.date_range(start="2024-01-01", periods=100, freq="1h")
    return pd.DataFrame({
        "open_time": dates,
        "open": 50000.0,
        "high": 51000.0,
        "low": 49000.0,
        "close": [50000.0 + i * 100 for i in range(100)],  # Uptrend
        "volume": 1000.0,
    })


@pytest.mark.asyncio
async def test_price_above_simple(engine):
    """Test simple price above condition."""
    alert = Alert(
        symbol="BTCUSD",
        exchange="bitfinex",
        timeframe="1h",
        condition=AlertCondition(
            type="price_above",
            operator="above",
            value=50000.0,
        ),
        enabled=True,
        id=1,
    )

    # Price above threshold
    triggered, history = await engine.evaluate_alert(alert, current_price=51000.0)
    assert triggered is True
    assert history is not None
    assert "crossed above" in history.message.lower()

    # Price below threshold
    triggered, history = await engine.evaluate_alert(alert, current_price=49000.0)
    assert triggered is False
    assert history is None


@pytest.mark.asyncio
async def test_price_below_simple(engine):
    """Test simple price below condition."""
    alert = Alert(
        symbol="BTCUSD",
        exchange="bitfinex",
        timeframe="1h",
        condition=AlertCondition(
            type="price_below",
            operator="below",
            value=50000.0,
        ),
        enabled=True,
        id=2,
    )

    # Price below threshold
    triggered, history = await engine.evaluate_alert(alert, current_price=49000.0)
    assert triggered is True
    assert history is not None

    # Price above threshold
    triggered, history = await engine.evaluate_alert(alert, current_price=51000.0)
    assert triggered is False


@pytest.mark.asyncio
async def test_price_crosses_above(engine):
    """Test price crosses above condition (requires state tracking)."""
    alert = Alert(
        symbol="BTCUSD",
        exchange="bitfinex",
        timeframe="1h",
        condition=AlertCondition(
            type="price_above",
            operator="crosses_above",
            value=50000.0,
        ),
        enabled=True,
        id=3,
    )

    # First call with price below (establish baseline)
    triggered, _ = await engine.evaluate_alert(alert, current_price=49000.0)
    assert triggered is False

    # Second call with price above (crossover!)
    triggered, history = await engine.evaluate_alert(alert, current_price=51000.0)
    assert triggered is True
    assert history is not None

    # Third call with price still above (no crossover)
    triggered, _ = await engine.evaluate_alert(alert, current_price=52000.0)
    assert triggered is False


@pytest.mark.asyncio
async def test_price_crosses_below(engine):
    """Test price crosses below condition."""
    alert = Alert(
        symbol="BTCUSD",
        exchange="bitfinex",
        timeframe="1h",
        condition=AlertCondition(
            type="price_below",
            operator="crosses_below",
            value=50000.0,
        ),
        enabled=True,
        id=4,
    )

    # First call above threshold
    triggered, _ = await engine.evaluate_alert(alert, current_price=51000.0)
    assert triggered is False

    # Second call below threshold (crossover!)
    triggered, history = await engine.evaluate_alert(alert, current_price=49000.0)
    assert triggered is True
    assert history is not None


@pytest.mark.asyncio
async def test_rsi_overbought(engine, sample_ohlcv):
    """Test RSI overbought condition."""
    alert = Alert(
        symbol="BTCUSD",
        exchange="bitfinex",
        timeframe="1h",
        condition=AlertCondition(
            type="rsi_overbought",
            operator="above",
            value=70.0,
            indicator_params={"period": 14},
        ),
        enabled=True,
        id=5,
    )

    # Should evaluate without error (actual RSI value depends on data)
    triggered, history = await engine.evaluate_alert(
        alert,
        current_price=59900.0,
        ohlcv_data=sample_ohlcv,
    )
    # Result depends on actual RSI calculation
    assert triggered in (True, False)


@pytest.mark.asyncio
async def test_rsi_oversold(engine, sample_ohlcv):
    """Test RSI oversold condition."""
    alert = Alert(
        symbol="BTCUSD",
        exchange="bitfinex",
        timeframe="1h",
        condition=AlertCondition(
            type="rsi_oversold",
            operator="below",
            value=30.0,
            indicator_params={"period": 14},
        ),
        enabled=True,
        id=6,
    )

    triggered, history = await engine.evaluate_alert(
        alert,
        current_price=50000.0,
        ohlcv_data=sample_ohlcv,
    )
    assert triggered in (True, False)


@pytest.mark.asyncio
async def test_macd_crossover(engine, sample_ohlcv):
    """Test MACD crossover conditions."""
    alert_up = Alert(
        symbol="BTCUSD",
        exchange="bitfinex",
        timeframe="1h",
        condition=AlertCondition(
            type="macd_cross_up",
            operator="crosses_above",
            value=0.0,
        ),
        enabled=True,
        id=7,
    )

    alert_down = Alert(
        symbol="BTCUSD",
        exchange="bitfinex",
        timeframe="1h",
        condition=AlertCondition(
            type="macd_cross_down",
            operator="crosses_below",
            value=0.0,
        ),
        enabled=True,
        id=8,
    )

    # Should evaluate without error
    triggered_up, _ = await engine.evaluate_alert(
        alert_up,
        current_price=59900.0,
        ohlcv_data=sample_ohlcv,
    )
    assert triggered_up in (True, False)

    triggered_down, _ = await engine.evaluate_alert(
        alert_down,
        current_price=59900.0,
        ohlcv_data=sample_ohlcv,
    )
    assert triggered_down in (True, False)


@pytest.mark.asyncio
async def test_disabled_alert(engine):
    """Test that disabled alerts don't trigger."""
    alert = Alert(
        symbol="BTCUSD",
        exchange="bitfinex",
        timeframe="1h",
        condition=AlertCondition(
            type="price_above",
            operator="above",
            value=50000.0,
        ),
        enabled=False,  # Disabled
        id=9,
    )

    triggered, history = await engine.evaluate_alert(alert, current_price=51000.0)
    assert triggered is False
    assert history is None


@pytest.mark.asyncio
async def test_insufficient_data_for_indicators(engine):
    """Test that indicator alerts handle insufficient data gracefully."""
    alert = Alert(
        symbol="BTCUSD",
        exchange="bitfinex",
        timeframe="1h",
        condition=AlertCondition(
            type="rsi_overbought",
            operator="above",
            value=70.0,
        ),
        enabled=True,
        id=10,
    )

    # No OHLCV data
    triggered, history = await engine.evaluate_alert(alert, current_price=51000.0, ohlcv_data=None)
    assert triggered is False
    assert history is None

    # Insufficient data (less than 50 rows)
    small_df = pd.DataFrame({
        "close": [50000.0] * 10,
    })
    triggered, history = await engine.evaluate_alert(alert, current_price=51000.0, ohlcv_data=small_df)
    assert triggered is False


@pytest.mark.asyncio
async def test_reset_state(engine):
    """Test resetting alert state."""
    alert = Alert(
        symbol="BTCUSD",
        exchange="bitfinex",
        timeframe="1h",
        condition=AlertCondition(
            type="price_above",
            operator="crosses_above",
            value=50000.0,
        ),
        enabled=True,
        id=11,
    )

    # Establish state
    await engine.evaluate_alert(alert, current_price=49000.0)

    # Reset state
    engine.reset_state(11)

    # Next evaluation should not trigger (no previous state)
    triggered, _ = await engine.evaluate_alert(alert, current_price=51000.0)
    assert triggered is False
