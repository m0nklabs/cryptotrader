# WebSocket Market Data

Real-time candle updates via WebSocket streaming.

## Overview

The WebSocket market data implementation provides real-time OHLCV candle updates for supported exchanges (currently Bitfinex). This complements the REST API-based backfill functionality with live streaming capabilities.

## Architecture

### Components

1. **BitfinexWebSocket** (`cex/bitfinex/api/websocket_client.py`)
   - Low-level WebSocket client for Bitfinex API v2
   - Handles connection, subscriptions, and message parsing
   - Thread-safe with automatic reconnection

2. **BitfinexWebSocketCandleProvider** (`core/market_data/websocket_provider.py`)
   - High-level candle provider using WebSocket streaming
   - Implements CandleProvider interface for compatibility
   - Converts raw WebSocket data to canonical Candle objects

### Data Flow

```
Bitfinex WebSocket API
        ↓
BitfinexWebSocket
  (connection + parsing)
        ↓
BitfinexWebSocketCandleProvider
  (normalization to Candle)
        ↓
Application callbacks
  (real-time processing)
```

## Usage

### Basic Example

```python
from core.market_data.websocket_provider import BitfinexWebSocketCandleProvider

# Create provider
provider = BitfinexWebSocketCandleProvider()

# Define callback for candle updates
def on_candle(candle):
    print(f"{candle.symbol} @ {candle.close}")

# Subscribe to symbol/timeframe
provider.subscribe('BTCUSD', '1m', on_candle)

# Start streaming
provider.start()

# ... application logic ...

# Stop when done
provider.stop()
```

### Demo Script

A demonstration script is provided:

```bash
# Stream BTCUSD 1m candles for 60 seconds
python scripts/websocket_candles_demo.py

# Stream ETHUSD 5m candles
python scripts/websocket_candles_demo.py --symbol ETHUSD --timeframe 5m

# Run indefinitely
python scripts/websocket_candles_demo.py --duration 0
```

### Queue-based Polling

For applications that prefer polling over callbacks:

```python
provider = BitfinexWebSocketCandleProvider()
provider.subscribe('BTCUSD', '1m')  # No callback
provider.start()

# Poll for updates
while True:
    candles = provider.get_candle_updates(timeout=1.0)
    for candle in candles:
        process_candle(candle)
    time.sleep(0.1)
```

## Supported Exchanges

### Bitfinex

- **Endpoint**: wss://api-pub.bitfinex.com/ws/2
- **Timeframes**: 1m, 5m, 15m, 1h, 4h, 1d
- **Features**:
  - Real-time candle updates
  - Automatic reconnection
  - Snapshot + incremental updates
  - Heartbeat handling

## Configuration

### Environment Variables

No special configuration required for public WebSocket endpoints. The client works out of the box.

### Timeframe Mapping

Internal timeframes are mapped to exchange-specific formats:

| Internal | Bitfinex API |
|----------|-------------|
| 1m       | 1m          |
| 5m       | 5m          |
| 15m      | 15m         |
| 1h       | 1h          |
| 4h       | 4h          |
| 1d       | 1D          |

## Features

### Automatic Reconnection

The WebSocket client automatically reconnects on disconnection with configurable backoff:

```python
ws = BitfinexWebSocket(
    reconnect=True,
    reconnect_interval=5  # seconds
)
```

### Thread Safety

Both `BitfinexWebSocket` and `BitfinexWebSocketCandleProvider` are thread-safe and run the WebSocket connection in a background thread.

### Multiple Subscriptions

Subscribe to multiple symbols/timeframes simultaneously:

```python
provider = BitfinexWebSocketCandleProvider()
provider.subscribe('BTCUSD', '1m', on_btc_1m)
provider.subscribe('BTCUSD', '5m', on_btc_5m)
provider.subscribe('ETHUSD', '1m', on_eth_1m)
provider.start()
```

### Canonical Data Format

All WebSocket candle data is normalized to the canonical `Candle` type defined in `core/types.py`:

```python
@dataclass(frozen=True)
class Candle:
    symbol: str          # e.g., 'BTCUSD'
    exchange: str        # e.g., 'bitfinex'
    timeframe: Timeframe # e.g., '1m'
    open_time: datetime
    close_time: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
```

## Testing

### Unit Tests

```bash
# Run WebSocket tests
python -m pytest tests/test_websocket_client.py -v
python -m pytest tests/test_websocket_provider.py -v
```

### Integration Tests

Integration tests against live WebSocket are skipped by default (to avoid network dependencies in CI). To run manually:

```python
# Mark test as runnable
pytest.mark.skip(reason="...") → pytest.mark.integration

# Run integration tests
python -m pytest tests/test_websocket_client.py::TestBitfinexWebSocketIntegration -v
```

## Limitations & Best Practices

### Use Cases

✅ **Good for:**
- Real-time signal generation
- Live monitoring dashboards
- Streaming data pipelines
- Event-driven trading

❌ **Not optimal for:**
- Historical data backfill (use REST API instead)
- Bulk candle fetching (use `bitfinex_backfill.py`)

### Performance Considerations

- WebSocket connections are persistent and use minimal bandwidth
- Candles are only transmitted when they update (not on every tick)
- Multiple subscriptions share a single WebSocket connection

### Error Handling

The client handles common error scenarios:
- Network disconnections → automatic reconnection
- Invalid subscriptions → logged errors
- Malformed messages → logged and skipped

## Future Extensions

Planned enhancements for WebSocket market data:

1. **Additional Exchanges**
   - Binance WebSocket support
   - Kraken WebSocket support
   - Generic WebSocket provider interface

2. **Additional Data Streams**
   - Ticker updates
   - Order book updates
   - Trade stream

3. **Advanced Features**
   - WebSocket authentication for private endpoints
   - Rate limit handling
   - Compression support

## Related

- Epic: [#70 Market Data Infrastructure](https://github.com/m0nk111/cryptotrader/issues/70)
- Replaces: [#26 WebSocket candle updates](https://github.com/m0nk111/cryptotrader/issues/26)
- REST API backfill: `core/market_data/bitfinex_backfill.py`
- Candle types: `core/types.py`
