#!/bin/bash
set -e

# Seed sample market data for testing
# This script populates the database with sample OHLCV data

echo "Seeding sample market data..."

# Check for DATABASE_URL
if [ -z "$DATABASE_URL" ]; then
    echo "Error: DATABASE_URL not set"
    exit 1
fi

# Seed a few days of 1h candles for BTC and ETH
python3 <<EOF
import os
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from sqlalchemy import create_engine, text

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    print("DATABASE_URL not set")
    sys.exit(1)

engine = create_engine(DATABASE_URL, echo=False)

# Sample symbols to seed
SYMBOLS = [
    ("BTCUSD", "bitfinex", Decimal("50000"), Decimal("5000")),
    ("ETHUSD", "bitfinex", Decimal("3000"), Decimal("300")),
]

# Generate sample candles for the last 7 days
end_time = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
start_time = end_time - timedelta(days=7)

print(f"Generating sample candles from {start_time} to {end_time}")

with engine.begin() as conn:
    for symbol, exchange, base_price, volatility in SYMBOLS:
        current_time = start_time
        price = base_price
        
        count = 0
        while current_time < end_time:
            # Simple random walk for demo data
            import random
            change = Decimal(random.uniform(-0.02, 0.02))  # +/- 2%
            price = price * (Decimal("1") + change)
            
            open_price = price
            high_price = price * Decimal("1.005")  # 0.5% higher
            low_price = price * Decimal("0.995")   # 0.5% lower
            close_price = price * (Decimal("1") + Decimal(random.uniform(-0.005, 0.005)))
            volume = Decimal(random.uniform(100, 1000))
            
            # Insert candle (ignore conflicts for idempotency)
            conn.execute(text("""
                INSERT INTO candles (
                    symbol, exchange, timeframe, open_time, close_time,
                    open, high, low, close, volume
                ) VALUES (
                    :symbol, :exchange, '1h', :open_time, :close_time,
                    :open, :high, :low, :close, :volume
                )
                ON CONFLICT (symbol, exchange, timeframe, open_time) DO NOTHING
            """), {
                "symbol": symbol,
                "exchange": exchange,
                "open_time": current_time,
                "close_time": current_time + timedelta(hours=1),
                "open": float(open_price),
                "high": float(high_price),
                "low": float(low_price),
                "close": float(close_price),
                "volume": float(volume),
            })
            
            current_time += timedelta(hours=1)
            count += 1
        
        print(f"✓ Seeded {count} candles for {symbol} on {exchange}")

print("Sample data seeding complete!")
EOF

echo "Seeding complete"
