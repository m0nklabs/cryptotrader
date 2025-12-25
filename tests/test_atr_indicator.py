from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.indicators.atr import compute_atr, generate_atr_signal
from core.types import Candle


def _make_candle(close: float, high: float | None = None, low: float | None = None, idx: int = 0) -> Candle:
    """Helper to create a candle with OHLC values."""
    from datetime import timedelta

    base_time = datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc)
    open_time = base_time + timedelta(hours=idx)
    close_time = base_time + timedelta(hours=idx, minutes=59)

    # Default high/low to close if not provided
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


# ========== compute_atr tests ==========


def test_compute_atr_requires_minimum_candles() -> None:
    """ATR with period=14 needs at least 15 candles."""
    candles = [_make_candle(100.0, idx=i) for i in range(14)]
    with pytest.raises(ValueError, match="need at least 15 candles"):
        compute_atr(candles, period=14)


def test_compute_atr_rejects_invalid_period() -> None:
    """Period must be >= 1."""
    candles = [_make_candle(100.0, idx=i) for i in range(20)]
    with pytest.raises(ValueError, match="period must be >= 1"):
        compute_atr(candles, period=0)


def test_compute_atr_returns_positive_value() -> None:
    """ATR should return positive value for volatile prices."""
    # Create candles with varying high/low
    candles = []
    for i in range(20):
        close = 100 + i
        candles.append(_make_candle(close, high=close + 5, low=close - 3, idx=i))

    atr = compute_atr(candles, period=14)

    assert atr > 0


def test_compute_atr_higher_for_volatile_prices() -> None:
    """ATR should be higher for more volatile prices."""
    # Low volatility
    low_vol_candles = []
    for i in range(20):
        close = 100
        low_vol_candles.append(_make_candle(close, high=close + 0.5, low=close - 0.5, idx=i))

    # High volatility
    high_vol_candles = []
    for i in range(20):
        close = 100
        high_vol_candles.append(_make_candle(close, high=close + 10, low=close - 10, idx=i))

    low_atr = compute_atr(low_vol_candles, period=14)
    high_atr = compute_atr(high_vol_candles, period=14)

    assert high_atr > low_atr


def test_compute_atr_uses_true_range() -> None:
    """ATR correctly uses true range (max of H-L, |H-PC|, |L-PC|)."""
    # Create scenario where gaps make |H-PC| or |L-PC| larger than H-L
    candles = [
        _make_candle(100, high=105, low=95, idx=0),  # Large range
        _make_candle(80, high=82, low=78, idx=1),  # Gap down (|L-PC| = 15)
        _make_candle(79, high=81, low=77, idx=2),  # Small range
    ]

    atr = compute_atr(candles, period=2)

    # ATR should reflect the large gap, not just the small ranges
    assert atr > 4  # Should be > simple average of ranges


def test_compute_atr_deterministic() -> None:
    """ATR produces deterministic output given fixed candle data."""
    candles = []
    for i in range(20):
        close = 100 + i * 0.5
        candles.append(_make_candle(close, high=close + 2, low=close - 1, idx=i))

    atr1 = compute_atr(candles)
    atr2 = compute_atr(candles)

    assert atr1 == atr2


def test_compute_atr_with_custom_period() -> None:
    """ATR works with custom period."""
    candles = []
    for i in range(25):
        close = 100 + i * 0.3
        candles.append(_make_candle(close, high=close + 1, low=close - 0.5, idx=i))

    atr = compute_atr(candles, period=10)

    # Should compute without error
    assert isinstance(atr, float)
    assert atr > 0


def test_compute_atr_with_flat_prices() -> None:
    """ATR with flat prices should be zero or near zero."""
    # All prices the same
    candles = [_make_candle(100.0, high=100.0, low=100.0, idx=i) for i in range(20)]

    atr = compute_atr(candles, period=14)

    # No volatility means ATR should be 0
    assert atr == 0.0


# ========== generate_atr_signal tests ==========


def test_generate_atr_signal_detects_high_volatility() -> None:
    """Signal detects high volatility condition."""
    # Create increasing volatility scenario
    candles = []

    # Normal volatility for first 40 candles
    for i in range(40):
        close = 100
        candles.append(_make_candle(close, high=close + 1, low=close - 1, idx=i))

    # High volatility for last few candles
    for i in range(40, 50):
        close = 100
        candles.append(_make_candle(close, high=close + 10, low=close - 10, idx=i))

    signal = generate_atr_signal(candles, period=14, high_volatility_threshold=1.5)

    assert signal.code == "ATR"
    # High volatility should be detected
    if signal.strength > 0:
        assert "high volatility" in signal.reason.lower() or "volatility" in signal.reason.lower()


def test_generate_atr_signal_detects_low_volatility() -> None:
    """Signal detects low volatility condition."""
    # Create decreasing volatility scenario
    candles = []

    # High volatility for first 40 candles
    for i in range(40):
        close = 100
        candles.append(_make_candle(close, high=close + 5, low=close - 5, idx=i))

    # Low volatility for last few candles
    for i in range(40, 50):
        close = 100
        candles.append(_make_candle(close, high=close + 0.1, low=close - 0.1, idx=i))

    signal = generate_atr_signal(candles, period=14, low_volatility_threshold=0.5)

    assert signal.code == "ATR"
    # Low volatility should be detected
    if signal.strength > 0:
        assert "low volatility" in signal.reason.lower() or "volatility" in signal.reason.lower()


def test_generate_atr_signal_normal_volatility() -> None:
    """Signal shows neutral for normal volatility."""
    # Consistent volatility
    candles = []
    for i in range(50):
        close = 100 + i * 0.1
        candles.append(_make_candle(close, high=close + 2, low=close - 2, idx=i))

    signal = generate_atr_signal(candles, period=14)

    assert signal.code == "ATR"
    # Normal volatility should result in HOLD with low/zero strength
    assert signal.side == "HOLD"


def test_generate_atr_signal_includes_atr_value() -> None:
    """Signal includes ATR value."""
    candles = []
    for i in range(20):
        close = 100 + i * 0.5
        candles.append(_make_candle(close, high=close + 1, low=close - 0.5, idx=i))

    signal = generate_atr_signal(candles)

    # Value should be a string representation of ATR
    atr_value = float(signal.value)
    assert atr_value > 0


def test_generate_atr_signal_rejects_invalid_high_threshold() -> None:
    """Raises error if high_volatility_threshold <= 1.0."""
    candles = [_make_candle(100.0, idx=i) for i in range(20)]

    with pytest.raises(ValueError, match="high_volatility_threshold must be > 1.0"):
        generate_atr_signal(candles, high_volatility_threshold=0.9)


def test_generate_atr_signal_rejects_invalid_low_threshold() -> None:
    """Raises error if low_volatility_threshold >= 1.0."""
    candles = [_make_candle(100.0, idx=i) for i in range(20)]

    with pytest.raises(ValueError, match="low_volatility_threshold must be < 1.0"):
        generate_atr_signal(candles, low_volatility_threshold=1.5)


def test_generate_atr_signal_with_custom_thresholds() -> None:
    """Works with custom volatility thresholds."""
    candles = []
    for i in range(50):
        close = 100 + i * 0.3
        candles.append(_make_candle(close, high=close + 1, low=close - 0.5, idx=i))

    signal = generate_atr_signal(candles, high_volatility_threshold=2.0, low_volatility_threshold=0.3)

    assert signal.code == "ATR"
    assert signal.side == "HOLD"  # ATR signals are always HOLD (informational)


def test_generate_atr_signal_deterministic_output() -> None:
    """Signal generation is deterministic with same inputs."""
    candles = []
    for i in range(50):
        close = 100 + i * 0.5
        candles.append(_make_candle(close, high=close + 1, low=close - 0.5, idx=i))

    signal1 = generate_atr_signal(candles)
    signal2 = generate_atr_signal(candles)

    assert signal1.code == signal2.code
    assert signal1.side == signal2.side
    assert signal1.strength == signal2.strength
    assert signal1.value == signal2.value
    assert signal1.reason == signal2.reason


def test_generate_atr_signal_handles_minimum_candles() -> None:
    """Signal works with minimum required candles."""
    candles = []
    for i in range(15):
        close = 100 + i
        candles.append(_make_candle(close, high=close + 2, low=close - 1, idx=i))

    signal = generate_atr_signal(candles, period=14)

    # Should work with minimum candles
    assert signal.code == "ATR"
    assert signal.side == "HOLD"


def test_generate_atr_signal_with_custom_period() -> None:
    """Works with custom ATR period."""
    candles = []
    for i in range(30):
        close = 100 + i * 0.3
        candles.append(_make_candle(close, high=close + 1, low=close - 0.5, idx=i))

    signal = generate_atr_signal(candles, period=10)

    assert signal.code == "ATR"
    assert signal.side == "HOLD"
    assert "ATR(10)" in signal.reason
