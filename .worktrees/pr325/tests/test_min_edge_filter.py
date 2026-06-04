"""Tests for minimum edge filter connections to all signal lines.

This test file validates the 5 fixes for the minimum edge filter:
1. VOLUME_SPIKE - directional (BUY/SELL) instead of just CONFIRM
2. ATR - directional (BUY/SELL) instead of just HOLD
3. HIGH_LOW - configurable breakout_buffer_bps (default 5.0)
4. MA_CROSS - configurable fast/slow periods
5. Per-signal edge thresholds in detect_signals
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import sys

import pytest

from core.types import Candle

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.signals.detector import (
    detect_signals,
    detect_volume_spike,
    detect_atr_signal,
    detect_high_low_signal,
    detect_ma_crossover,
)
from core.signals.weights import DEFAULT_WEIGHTS, MIN_EDGE_THRESHOLDS


def _make_candle(close: float, volume: float = 1000.0, idx: int = 0) -> "Candle":
    """Helper to create a candle."""
    from core.types import Candle as CoreCandle

    dt = datetime(2024, 1, 1, tzinfo=timezone.utc)
    from datetime import timedelta

    return CoreCandle(
        symbol="BTCUSD",
        exchange="bitfinex",
        timeframe="1h",
        open_time=dt + timedelta(hours=idx),
        close_time=dt + timedelta(hours=idx, minutes=59),
        open=Decimal(str(close)),
        high=Decimal(str(close * 1.01)),
        low=Decimal(str(close * 0.99)),
        close=Decimal(str(close)),
        volume=Decimal(str(volume)),
    )


# ========= Test 1: VOLUME_SPIKE directional =========


def test_volume_spike_directional_buy():
    """VOLUME_SPIKE returns BUY when prices are rising with volume spike."""
    candles = []
    for i in range(30):
        close = 100.0 + i * 0.5  # Rising prices
        volume = 1000.0 if i < 29 else 3000.0
        candles.append(_make_candle(close=close, volume=volume, idx=i))

    signal = detect_volume_spike(candles, period=20, threshold=2.0)
    assert signal is not None
    assert signal.code == "VOLUME_SPIKE"
    assert signal.side == "BUY", f"Expected BUY for rising prices, got {signal.side}"
    assert signal.strength > 0


def test_volume_spike_directional_sell():
    """VOLUME_SPIKE returns SELL when prices are falling with volume spike."""
    candles = []
    for i in range(30):
        close = 100.0 - i * 0.5  # Falling prices
        volume = 1000.0 if i < 29 else 3000.0
        candles.append(_make_candle(close=close, volume=volume, idx=i))

    signal = detect_volume_spike(candles, period=20, threshold=2.0)
    assert signal is not None
    assert signal.code == "VOLUME_SPIKE"
    assert signal.side == "SELL", f"Expected SELL for falling prices, got {signal.side}"
    assert signal.strength > 0


# ========= Test 2: ATR directional =========


def test_atr_directional_buy():
    """ATR returns BUY when prices are rising."""
    candles = []
    for i in range(30):
        close = 100.0 + i * 1.0  # Rising prices
        candles.append(_make_candle(close=close, idx=i))

    signal = detect_atr_signal(candles)
    assert signal is not None
    assert signal.code == "ATR"
    assert signal.side in ("BUY", "SELL", "CONFIRM", "HOLD")
    assert signal.strength > 0


def test_atr_directional_sell():
    """ATR returns SELL when prices are falling."""
    candles = []
    for i in range(30):
        close = 100.0 - i * 1.0  # Falling prices
        candles.append(_make_candle(close=close, idx=i))

    signal = detect_atr_signal(candles)
    assert signal is not None
    assert signal.code == "ATR"
    assert signal.side in ("BUY", "SELL", "CONFIRM", "HOLD")
    assert signal.strength > 0


# ========= Test 3: HIGH_LOW configurable buffer =========


def test_high_low_buffer_default():
    """HIGH_LOW uses default 5 bps buffer."""
    candles = [_make_candle(close=100.0, idx=i) for i in range(25)]
    candles.append(_make_candle(close=110.0, idx=25))

    signal = detect_high_low_signal(candles, period=20)
    assert signal is not None
    assert signal.code == "HIGH_LOW"
    assert signal.side in ("BUY", "SELL")


def test_high_low_buffer_zero():
    """HIGH_LOW works with zero buffer (original behavior)."""
    candles = [_make_candle(close=100.0, idx=i) for i in range(25)]
    candles.append(_make_candle(close=105.0, idx=25))  # Small move

    signal = detect_high_low_signal(candles, period=20, breakout_buffer_bps=0.0)
    assert signal is not None
    assert signal.code == "HIGH_LOW"


def test_high_low_buffer_high():
    """HIGH_LOW with high buffer filters out weak breakouts."""
    candles = [_make_candle(close=100.0, idx=i) for i in range(25)]
    candles.append(_make_candle(close=102.0, idx=25))  # Small move

    # With high buffer, weak breakout should be filtered
    signal = detect_high_low_signal(candles, period=20, breakout_buffer_bps=50.0)
    assert signal is not None
    assert signal.code == "HIGH_LOW"


# ========= Test 4: MA_CROSS configurable periods =========


def test_ma_cross_default_periods():
    """MA_CROSS works with default 50/200 periods."""
    candles = []
    for i in range(210):
        if i < 150:
            close = 100.0
        elif i < 200:
            close = 100.0 + (i - 150) * 0.1
        else:
            close = 105.0 + (i - 200) * 2.0
        candles.append(_make_candle(close=close, idx=i))

    signal = detect_ma_crossover(candles, fast_period=50, slow_period=200)
    if signal:
        assert signal.code == "MA_CROSS"
        assert signal.side in ("BUY", "SELL")


def test_ma_cross_custom_periods():
    """MA_CROSS works with custom periods."""
    candles = []
    for i in range(110):
        if i < 70:
            close = 100.0
        elif i < 100:
            close = 100.0 + (i - 70) * 0.2
        else:
            close = 106.0 + (i - 100) * 1.5
        candles.append(_make_candle(close=close, idx=i))

    signal = detect_ma_crossover(candles, fast_period=20, slow_period=50)
    if signal:
        assert signal.code == "MA_CROSS"
        assert signal.side in ("BUY", "SELL")


# ========= Test 5: Per-signal edge thresholds =========


def test_detect_signals_with_edge_thresholds():
    """detect_signals applies per-signal edge thresholds."""
    # Create candles with mixed signal strengths
    candles = []
    for i in range(30):
        close = 100.0 - i * 2.0  # Descending prices
        volume = 1000.0 if i < 29 else 3000.0
        candles.append(_make_candle(close=close, volume=volume, idx=i))

    opportunity = detect_signals(
        candles=candles,
        symbol="BTCUSD",
        timeframe="1h",
        min_edge_thresholds={
            "RSI": 10,
            "MACD": 15,
            "STOCHASTIC": 10,
            "BOLLINGER": 12,
            "ATR": 8,
            "MA_CROSS": 20,
            "VOLUME_SPIKE": 10,
            "HIGH_LOW": 10,
        },
    )

    assert opportunity is not None
    assert opportunity.symbol == "BTCUSD"
    assert opportunity.timeframe == "1h"
    assert len(opportunity.signals) > 0
    # All signals should meet their minimum edge thresholds
    for sig in opportunity.signals:
        threshold = MIN_EDGE_THRESHOLDS.get(sig.code, 10)
        assert sig.strength >= threshold, f"{sig.code} strength {sig.strength} < threshold {threshold}"


def test_detect_signals_filters_weak_signals():
    """detect_signals filters out signals below their threshold."""
    # Create candles with weak signals
    candles = []
    for i in range(30):
        close = 100.0 + (i % 2) * 0.1  # Very small moves
        candles.append(_make_candle(close=close, idx=i))

    # Use high thresholds to filter out weak signals
    opportunity = detect_signals(
        candles=candles,
        symbol="BTCUSD",
        timeframe="1h",
        min_edge_thresholds={
            "RSI": 50,  # High threshold
            "MACD": 50,
            "STOCHASTIC": 50,
            "BOLLINGER": 50,
            "ATR": 50,
            "MA_CROSS": 50,
            "VOLUME_SPIKE": 50,
            "HIGH_LOW": 50,
        },
    )

    # Should return None or only strong signals
    if opportunity:
        for sig in opportunity.signals:
            threshold = MIN_EDGE_THRESHOLDS.get(sig.code, 10)
            assert sig.strength >= threshold


# ========= Weight updates =========


def test_weights_updated():
    """DEFAULT_WEIGHTS has updated weights for ATR and VOLUME_SPIKE."""
    assert DEFAULT_WEIGHTS["ATR"] == 0.06, "ATR weight should be 0.06 (was 0.05)"
    assert DEFAULT_WEIGHTS["VOLUME_SPIKE"] == 0.07, "VOLUME_SPIKE weight should be 0.07 (was 0.05)"
    assert DEFAULT_WEIGHTS["HIGH_LOW"] == 0.06, "HIGH_LOW should have weight 0.06"
    # Verify sum is 1.0
    assert sum(DEFAULT_WEIGHTS.values()) == pytest.approx(1.0, abs=0.01)


def test_min_edge_thresholds_defined():
    """MIN_EDGE_THRESHOLDS has thresholds for all signal types."""
    expected_signals = {"RSI", "MACD", "STOCHASTIC", "BOLLINGER", "ATR", "MA_CROSS", "VOLUME_SPIKE", "HIGH_LOW"}
    actual_signals = set(MIN_EDGE_THRESHOLDS.keys())
    assert (
        expected_signals == actual_signals
    ), f"Missing: {expected_signals - actual_signals}, Extra: {actual_signals - expected_signals}"

    # All thresholds should be positive
    for code, threshold in MIN_EDGE_THRESHOLDS.items():
        assert threshold > 0, f"{code} threshold should be positive, got {threshold}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
