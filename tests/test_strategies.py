"""Tests for example trading strategies."""

from pathlib import Path
import sys
from decimal import Decimal

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from datetime import datetime, timezone

from core.types import Candle
from strategies.rsi_mean_reversion import RSIMeanReversionStrategy
from strategies.sma_crossover import SMACrossoverStrategy


# ========== RSI Mean Reversion Tests ==========


def test_rsi_strategy_buy_signal():
    """Test RSI strategy generates BUY signal when oversold."""
    strategy = RSIMeanReversionStrategy(oversold=30.0, overbought=70.0)

    candle = Candle(
        exchange="test",
        symbol="BTCUSD",
        timeframe="1h",
        open_time=datetime.now(timezone.utc),
        open=Decimal("50000"),
        high=Decimal("51000"),
        low=Decimal("49000"),
        close=Decimal("50000"),
        volume=Decimal("100"),
    )

    indicators = {"rsi": 25.0}  # Oversold
    signal = strategy.on_candle(candle, indicators)

    assert signal is not None
    assert signal.side == "BUY"
    assert signal.strength > 0


def test_rsi_strategy_sell_signal():
    """Test RSI strategy generates SELL signal when overbought."""
    strategy = RSIMeanReversionStrategy(oversold=30.0, overbought=70.0)

    candle = Candle(
        exchange="test",
        symbol="BTCUSD",
        timeframe="1h",
        open_time=datetime.now(timezone.utc),
        open=Decimal("50000"),
        high=Decimal("51000"),
        low=Decimal("49000"),
        close=Decimal("50000"),
        volume=Decimal("100"),
    )

    indicators = {"rsi": 75.0}  # Overbought
    signal = strategy.on_candle(candle, indicators)

    assert signal is not None
    assert signal.side == "SELL"
    assert signal.strength > 0


def test_rsi_strategy_hold_signal():
    """Test RSI strategy generates HOLD signal in neutral zone."""
    strategy = RSIMeanReversionStrategy(oversold=30.0, overbought=70.0)

    candle = Candle(
        exchange="test",
        symbol="BTCUSD",
        timeframe="1h",
        open_time=datetime.now(timezone.utc),
        open=Decimal("50000"),
        high=Decimal("51000"),
        low=Decimal("49000"),
        close=Decimal("50000"),
        volume=Decimal("100"),
    )

    indicators = {"rsi": 50.0}  # Neutral
    signal = strategy.on_candle(candle, indicators)

    assert signal is not None
    assert signal.side == "HOLD"
    assert signal.strength == 0


def test_rsi_strategy_no_rsi():
    """Test RSI strategy returns None when RSI not available."""
    strategy = RSIMeanReversionStrategy()

    candle = Candle(
        exchange="test",
        symbol="BTCUSD",
        timeframe="1h",
        open_time=datetime.now(timezone.utc),
        open=Decimal("50000"),
        high=Decimal("51000"),
        low=Decimal("49000"),
        close=Decimal("50000"),
        volume=Decimal("100"),
    )

    indicators = {}  # No RSI
    signal = strategy.on_candle(candle, indicators)

    assert signal is None


# ========== SMA Crossover Tests ==========


def test_sma_crossover_initialization():
    """Test SMA crossover strategy initialization."""
    strategy = SMACrossoverStrategy(fast_period=10, slow_period=30)
    assert strategy.fast_period == 10
    assert strategy.slow_period == 30


def test_sma_crossover_invalid_periods():
    """Test SMA crossover rejects invalid periods."""
    try:
        SMACrossoverStrategy(fast_period=30, slow_period=10)
        assert False, "Should raise ValueError"
    except ValueError as e:
        assert "fast_period must be less than slow_period" in str(e)


def test_sma_crossover_golden_cross():
    """Test SMA crossover generates BUY on golden cross."""
    strategy = SMACrossoverStrategy(fast_period=10, slow_period=30)

    candle = Candle(
        exchange="test",
        symbol="BTCUSD",
        timeframe="1h",
        open_time=datetime.now(timezone.utc),
        open=Decimal("50000"),
        high=Decimal("51000"),
        low=Decimal("49000"),
        close=Decimal("50000"),
        volume=Decimal("100"),
    )

    # First call - establish baseline
    indicators = {"sma_10": 100.0, "sma_30": 105.0}  # Fast below slow
    signal = strategy.on_candle(candle, indicators)
    assert signal is not None
    assert signal.side == "HOLD"

    # Second call - golden cross (fast crosses above slow)
    indicators = {"sma_10": 106.0, "sma_30": 105.0}  # Fast above slow
    signal = strategy.on_candle(candle, indicators)
    assert signal is not None
    assert signal.side == "BUY"
    assert signal.strength > 0


def test_sma_crossover_death_cross():
    """Test SMA crossover generates SELL on death cross."""
    strategy = SMACrossoverStrategy(fast_period=10, slow_period=30)

    candle = Candle(
        exchange="test",
        symbol="BTCUSD",
        timeframe="1h",
        open_time=datetime.now(timezone.utc),
        open=Decimal("50000"),
        high=Decimal("51000"),
        low=Decimal("49000"),
        close=Decimal("50000"),
        volume=Decimal("100"),
    )

    # First call - establish baseline
    indicators = {"sma_10": 105.0, "sma_30": 100.0}  # Fast above slow
    signal = strategy.on_candle(candle, indicators)
    assert signal is not None
    assert signal.side == "HOLD"

    # Second call - death cross (fast crosses below slow)
    indicators = {"sma_10": 99.0, "sma_30": 100.0}  # Fast below slow
    signal = strategy.on_candle(candle, indicators)
    assert signal is not None
    assert signal.side == "SELL"
    assert signal.strength > 0


def test_sma_crossover_no_indicators():
    """Test SMA crossover returns None when SMAs not available."""
    strategy = SMACrossoverStrategy(fast_period=10, slow_period=30)

    candle = Candle(
        exchange="test",
        symbol="BTCUSD",
        timeframe="1h",
        open_time=datetime.now(timezone.utc),
        open=Decimal("50000"),
        high=Decimal("51000"),
        low=Decimal("49000"),
        close=Decimal("50000"),
        volume=Decimal("100"),
    )

    indicators = {}  # No SMAs
    signal = strategy.on_candle(candle, indicators)

    assert signal is None


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
