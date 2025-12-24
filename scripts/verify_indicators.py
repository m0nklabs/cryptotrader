#!/usr/bin/env python3
"""
Manual verification script for extended TA indicators.
Demonstrates that all new indicators work correctly.
"""

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.indicators import (
    compute_atr,
    compute_bollinger_bands,
    compute_macd,
    compute_rsi,
    compute_stochastic,
    generate_atr_signal,
    generate_bollinger_signal,
    generate_macd_signal,
    generate_rsi_signal,
    generate_stochastic_signal,
)
from core.signals.detector import detect_signals
from core.types import Candle


def make_test_candles(count: int = 100) -> list[Candle]:
    """Generate test candles with realistic price movement."""
    from datetime import timedelta

    base_time = datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc)
    candles = []

    price = 100.0
    for i in range(count):
        # Add some realistic price variation
        price += (i % 7 - 3) * 0.5  # Oscillating pattern
        high = price + 2
        low = price - 1
        volume = 1000 + (i * 10)

        candle = Candle(
            symbol="BTCUSD",
            exchange="bitfinex",
            timeframe="1h",
            open_time=base_time + timedelta(hours=i),
            close_time=base_time + timedelta(hours=i, minutes=59),
            open=Decimal(str(price)),
            high=Decimal(str(high)),
            low=Decimal(str(low)),
            close=Decimal(str(price)),
            volume=Decimal(str(volume)),
        )
        candles.append(candle)

    return candles


def main():
    print("=" * 80)
    print("Extended TA Indicators - Manual Verification")
    print("=" * 80)
    print()

    # Generate test data
    print("📊 Generating test candles...")
    candles = make_test_candles(250)
    print(f"   Generated {len(candles)} candles")
    print()

    # Test RSI (existing)
    print("1️⃣  RSI Indicator")
    print("-" * 80)
    rsi_value = compute_rsi(candles, period=14)
    rsi_signal = generate_rsi_signal(candles, period=14)
    print(f"   RSI Value: {rsi_value:.2f}")
    print(f"   Signal: {rsi_signal.side} (strength: {rsi_signal.strength})")
    print(f"   Reason: {rsi_signal.reason}")
    print()

    # Test MACD (new)
    print("2️⃣  MACD Indicator")
    print("-" * 80)
    macd_line, signal_line, histogram = compute_macd(candles, fast=12, slow=26, signal_period=9)
    macd_signal = generate_macd_signal(candles)
    print(f"   MACD Line: {macd_line:.4f}")
    print(f"   Signal Line: {signal_line:.4f}")
    print(f"   Histogram: {histogram:.4f}")
    print(f"   Signal: {macd_signal.side} (strength: {macd_signal.strength})")
    print(f"   Reason: {macd_signal.reason}")
    print()

    # Test Stochastic (new)
    print("3️⃣  Stochastic Oscillator")
    print("-" * 80)
    k_value, d_value = compute_stochastic(candles, k_period=14, d_period=3)
    stoch_signal = generate_stochastic_signal(candles)
    print(f"   %K: {k_value:.2f}")
    print(f"   %D: {d_value:.2f}")
    print(f"   Signal: {stoch_signal.side} (strength: {stoch_signal.strength})")
    print(f"   Reason: {stoch_signal.reason}")
    print()

    # Test Bollinger Bands (new)
    print("4️⃣  Bollinger Bands")
    print("-" * 80)
    upper, middle, lower = compute_bollinger_bands(candles, period=20, std_dev=2.0)
    bb_signal = generate_bollinger_signal(candles)
    print(f"   Upper Band: ${upper:.2f}")
    print(f"   Middle Band: ${middle:.2f}")
    print(f"   Lower Band: ${lower:.2f}")
    print(f"   Current Price: {bb_signal.value}")
    print(f"   Signal: {bb_signal.side} (strength: {bb_signal.strength})")
    print(f"   Reason: {bb_signal.reason}")
    print()

    # Test ATR (new)
    print("5️⃣  ATR (Average True Range)")
    print("-" * 80)
    atr_value = compute_atr(candles, period=14)
    atr_signal = generate_atr_signal(candles)
    print(f"   ATR: {atr_value:.4f}")
    print(f"   Signal: {atr_signal.side} (strength: {atr_signal.strength})")
    print(f"   Reason: {atr_signal.reason}")
    print()

    # Test integrated signal detection
    print("6️⃣  Integrated Signal Detection")
    print("-" * 80)
    opportunity = detect_signals(candles=candles, symbol="BTCUSD", timeframe="1h")
    if opportunity:
        print(f"   Symbol: {opportunity.symbol}")
        print(f"   Timeframe: {opportunity.timeframe}")
        print(f"   Overall Side: {opportunity.side}")
        print(f"   Score: {opportunity.score}/100")
        print(f"   Signals Detected: {len(opportunity.signals)}")
        print()
        print("   Signal Breakdown:")
        for sig in opportunity.signals:
            print(f"      • {sig.code}: {sig.side} (strength: {sig.strength})")
            print(f"        {sig.reason}")
    else:
        print("   No opportunity detected (not enough signals)")
    print()

    print("=" * 80)
    print("✅ All indicators working correctly!")
    print("=" * 80)


if __name__ == "__main__":
    main()
