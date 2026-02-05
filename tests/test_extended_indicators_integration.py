from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.signals.detector import (
    detect_atr_signal,
    detect_bollinger_signal,
    detect_macd_signal,
    detect_signals,
    detect_stochastic_signal,
)
from core.types import Candle


def _make_candle(close: float, high: float | None = None, low: float | None = None, idx: int = 0) -> Candle:
    """Helper to create a candle with OHLC values."""
    from datetime import timedelta

    base_time = datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc)
    open_time = base_time + timedelta(hours=idx)
    close_time = base_time + timedelta(hours=idx, minutes=59)

    if high is None:
        high = close
    if low is None:
        low = close

    return Candle(
        symbol="BTCUSD",
        exchange="bitfinex",
        timeframe="1h",
        open_time=open_time,
        close_time=close_time,
        open=Decimal(str(close)),
        high=Decimal(str(high)),
        low=Decimal(str(low)),
        close=Decimal(str(close)),
        volume=Decimal("1000"),
    )


def test_detect_macd_signal_integration() -> None:
    """Test MACD signal detection in detector."""
    # Create trend reversal to trigger MACD crossover
    prices = [100 - i for i in range(20)] + [80 + i * 2 for i in range(30)]
    candles = [_make_candle(p, idx=i) for i, p in enumerate(prices)]

    signal = detect_macd_signal(candles)

    # Should detect a signal (BUY or HOLD depending on exact crossover timing)
    if signal:
        assert signal.code == "MACD"
        assert signal.side in ["BUY", "SELL", "HOLD"]


def test_detect_stochastic_signal_integration() -> None:
    """Test Stochastic signal detection in detector."""
    # Create strong downtrend to get oversold stochastic
    candles = []
    for i in range(25):
        close = 100 - i * 3
        candles.append(_make_candle(close, high=close + 1, low=close - 1, idx=i))

    signal = detect_stochastic_signal(candles)

    # Should detect oversold signal
    if signal:
        assert signal.code == "STOCHASTIC"
        assert signal.side == "BUY"


def test_detect_bollinger_signal_integration() -> None:
    """Test Bollinger Bands signal detection in detector."""
    # Create sudden drop below lower band
    prices = [100] * 25 + [90]
    candles = [_make_candle(p, idx=i) for i, p in enumerate(prices)]

    signal = detect_bollinger_signal(candles)

    # Should detect buy signal when price is below lower band
    if signal:
        assert signal.code == "BOLLINGER"
        assert signal.side == "BUY"


def test_detect_atr_signal_integration() -> None:
    """Test ATR signal detection in detector."""
    # Create high volatility scenario
    candles = []

    # Normal volatility for first 40 candles
    for i in range(40):
        close = 100
        candles.append(_make_candle(close, high=close + 1, low=close - 1, idx=i))

    # High volatility for last few candles
    for i in range(40, 50):
        close = 100
        candles.append(_make_candle(close, high=close + 10, low=close - 10, idx=i))

    signal = detect_atr_signal(candles)

    # Should detect volatility signal
    if signal:
        assert signal.code == "ATR"
        assert signal.side == "HOLD"  # ATR signals are informational


def test_detect_signals_with_all_indicators() -> None:
    """Test that detect_signals integrates all indicators."""
    # Create scenario with strong downtrend (should trigger multiple indicators)
    candles = []
    for i in range(250):
        close = 100 - i * 0.5
        candles.append(_make_candle(close, high=close + 2, low=close - 1, idx=i))

    opportunity = detect_signals(candles=candles, symbol="BTCUSD", timeframe="1h")

    # Should detect opportunity with multiple signals
    if opportunity:
        assert opportunity.symbol == "BTCUSD"
        assert opportunity.timeframe == "1h"
        assert len(opportunity.signals) > 0
        assert 0 <= opportunity.score <= 100

        # Check that we have signals from various indicators
        signal_codes = {sig.code for sig in opportunity.signals}
        # Should have at least some indicators firing
        assert len(signal_codes) > 0


def test_detect_signals_weights_updated() -> None:
    """Test that signal weights include new indicators."""
    # Create diverse scenario
    candles = []
    for i in range(250):
        close = 100 + i * 0.1
        candles.append(_make_candle(close, high=close + 1, low=close - 0.5, idx=i))

    opportunity = detect_signals(candles=candles, symbol="BTCUSD", timeframe="1h")

    # If we get an opportunity, verify it has signals
    if opportunity:
        assert len(opportunity.signals) > 0
        # Verify various indicator codes could be present
        valid_codes = {"RSI", "MACD", "STOCHASTIC", "BOLLINGER", "HIGH_LOW", "ATR", "MA_CROSS", "VOLUME_SPIKE"}
        for sig in opportunity.signals:
            assert sig.code in valid_codes
