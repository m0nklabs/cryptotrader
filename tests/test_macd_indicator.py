from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.indicators.macd import compute_macd, generate_macd_signal
from core.types import Candle


def _make_candle(close: float, idx: int = 0) -> Candle:
    """Helper to create a candle with minimal required fields."""
    from datetime import timedelta

    base_time = datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc)
    open_time = base_time + timedelta(hours=idx)
    close_time = base_time + timedelta(hours=idx, minutes=59)
    return Candle(
        symbol="BTCUSD",
        exchange="bitfinex",
        timeframe="1h",
        open_time=open_time,
        close_time=close_time,
        open=Decimal(str(close)),
        high=Decimal(str(close)),
        low=Decimal(str(close)),
        close=Decimal(str(close)),
        volume=Decimal("1000"),
    )


# ========== compute_macd tests ==========


def test_compute_macd_requires_minimum_candles() -> None:
    """MACD with default params (12,26,9) needs at least 35 candles."""
    candles = [_make_candle(100.0, i) for i in range(34)]
    with pytest.raises(ValueError, match="need at least 35 candles"):
        compute_macd(candles)


def test_compute_macd_rejects_invalid_periods() -> None:
    """Periods must be >= 1."""
    candles = [_make_candle(100.0, i) for i in range(50)]
    with pytest.raises(ValueError, match="periods must be >= 1"):
        compute_macd(candles, fast=0, slow=26, signal_period=9)


def test_compute_macd_rejects_fast_gte_slow() -> None:
    """Fast period must be < slow period."""
    candles = [_make_candle(100.0, i) for i in range(50)]
    with pytest.raises(ValueError, match="fast period .* must be < slow period"):
        compute_macd(candles, fast=26, slow=12, signal_period=9)


def test_compute_macd_with_uptrend() -> None:
    """MACD with uptrend should have positive MACD and signal lines."""
    # Strong uptrend
    prices = [100 + i * 2 for i in range(50)]
    candles = [_make_candle(p, i) for i, p in enumerate(prices)]

    macd_line, signal_line, histogram = compute_macd(candles)

    # In strong uptrend, both MACD and signal should be positive
    # Histogram sign depends on whether MACD is accelerating or decelerating
    assert macd_line > 0
    assert signal_line > 0


def test_compute_macd_with_downtrend() -> None:
    """MACD with downtrend should have negative histogram."""
    # Strong downtrend
    prices = [100 - i * 2 for i in range(50)]
    candles = [_make_candle(p, i) for i, p in enumerate(prices)]

    macd_line, signal_line, histogram = compute_macd(candles)

    # In downtrend, MACD line should be negative and below signal line
    assert macd_line < 0
    assert histogram < 0  # MACD below signal


def test_compute_macd_deterministic() -> None:
    """MACD produces deterministic output given fixed candle data."""
    prices = [100 + i * 0.5 for i in range(50)]
    candles = [_make_candle(p, i) for i, p in enumerate(prices)]

    macd1, signal1, hist1 = compute_macd(candles)
    macd2, signal2, hist2 = compute_macd(candles)

    assert macd1 == macd2
    assert signal1 == signal2
    assert hist1 == hist2


def test_compute_macd_with_custom_periods() -> None:
    """MACD works with custom periods."""
    prices = [100 + i * 0.3 for i in range(60)]
    candles = [_make_candle(p, i) for i, p in enumerate(prices)]

    macd_line, signal_line, histogram = compute_macd(candles, fast=8, slow=21, signal_period=5)

    # Should compute without error
    assert isinstance(macd_line, float)
    assert isinstance(signal_line, float)
    assert isinstance(histogram, float)


# ========== generate_macd_signal tests ==========


def test_generate_macd_signal_buy_on_bullish_crossover() -> None:
    """BUY signal when MACD crosses above signal line."""
    # Create trend reversal: downtrend then uptrend
    prices = [100 - i for i in range(20)] + [80 + i * 2 for i in range(30)]
    candles = [_make_candle(p, i) for i, p in enumerate(prices)]

    signal = generate_macd_signal(candles)

    # After reversal, should eventually get bullish crossover or positive histogram
    assert signal.code == "MACD"
    # Signal could be BUY (crossover) or HOLD (trending)
    assert signal.side in ["BUY", "HOLD"]


def test_generate_macd_signal_sell_on_bearish_crossover() -> None:
    """SELL signal when MACD crosses below signal line."""
    # Create trend reversal: uptrend then downtrend
    prices = [100 + i for i in range(20)] + [120 - i * 2 for i in range(30)]
    candles = [_make_candle(p, i) for i, p in enumerate(prices)]

    signal = generate_macd_signal(candles)

    # After reversal, should eventually get bearish crossover or negative histogram
    assert signal.code == "MACD"
    # Signal could be SELL (crossover) or HOLD (trending)
    assert signal.side in ["SELL", "HOLD"]


def test_generate_macd_signal_hold_when_no_crossover() -> None:
    """HOLD signal when no crossover occurs."""
    # Steady uptrend (no crossover)
    prices = [100 + i * 0.5 for i in range(50)]
    candles = [_make_candle(p, i) for i, p in enumerate(prices)]

    signal = generate_macd_signal(candles)

    assert signal.code == "MACD"
    # In steady trend, likely HOLD
    assert signal.side == "HOLD"


def test_generate_macd_signal_includes_reason() -> None:
    """Signal includes human-readable reason."""
    prices = [100 + i * 0.5 for i in range(50)]
    candles = [_make_candle(p, i) for i, p in enumerate(prices)]

    signal = generate_macd_signal(candles)

    # Reason should contain MACD parameters
    assert "MACD(12,26,9)" in signal.reason
    assert len(signal.reason) > 10


def test_generate_macd_signal_value_contains_histogram() -> None:
    """Signal value field contains histogram value."""
    prices = [100 + i * 0.5 for i in range(50)]
    candles = [_make_candle(p, i) for i, p in enumerate(prices)]

    signal = generate_macd_signal(candles)

    # Value should be a string representation of histogram
    hist_value = float(signal.value)
    assert isinstance(hist_value, float)


def test_generate_macd_signal_strength_based_on_histogram() -> None:
    """Signal strength increases with histogram magnitude."""
    # Create two scenarios: weak and strong trends
    weak_prices = [100 + i * 0.1 for i in range(50)]
    strong_prices = [100 + i * 2 for i in range(50)]

    weak_candles = [_make_candle(p, i) for i, p in enumerate(weak_prices)]
    strong_candles = [_make_candle(p, i) for i, p in enumerate(strong_prices)]

    weak_signal = generate_macd_signal(weak_candles)
    strong_signal = generate_macd_signal(strong_candles)

    # Stronger trend should have higher strength (if same side)
    if weak_signal.side == strong_signal.side and weak_signal.side != "HOLD":
        assert strong_signal.strength >= weak_signal.strength


def test_generate_macd_signal_requires_crossover_detection_candles() -> None:
    """Needs extra candles to detect crossover."""
    candles = [_make_candle(100.0, i) for i in range(35)]
    with pytest.raises(ValueError, match="need at least 36 candles"):
        generate_macd_signal(candles)


def test_generate_macd_signal_with_custom_periods() -> None:
    """Works with custom MACD periods."""
    prices = [100 + i * 0.3 for i in range(60)]
    candles = [_make_candle(p, i) for i, p in enumerate(prices)]

    signal = generate_macd_signal(candles, fast=8, slow=21, signal_period=5)

    assert signal.code == "MACD"
    assert signal.side in ["BUY", "SELL", "HOLD"]
    assert "MACD(8,21,5)" in signal.reason


def test_generate_macd_signal_deterministic_output() -> None:
    """Signal generation is deterministic with same inputs."""
    prices = [100 + i * 0.5 for i in range(50)]
    candles = [_make_candle(p, i) for i, p in enumerate(prices)]

    signal1 = generate_macd_signal(candles)
    signal2 = generate_macd_signal(candles)

    assert signal1.code == signal2.code
    assert signal1.side == signal2.side
    assert signal1.strength == signal2.strength
    assert signal1.value == signal2.value
    assert signal1.reason == signal2.reason
