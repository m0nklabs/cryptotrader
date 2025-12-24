# Real-time Candle Updates via WebSocket

This document explains the WebSocket integration for real-time candle updates.

## Overview

The system now supports real-time candle updates from Bitfinex via WebSocket, replacing the polling approach with near-instant updates.

### Architecture

1. **Backend WebSocket Client** (`core/market_data/bitfinex_websocket.py`)
   - Connects to Bitfinex public WebSocket API (`wss://api-pub.bitfinex.com/ws/2`)
   - Subscribes to candle channels for specified symbol/timeframe pairs
   - Maintains thread-safe subscription management
   - Handles reconnection with exponential backoff

2. **API Server Integration** (`scripts/api_server.py`)
   - Manages WebSocket connections on startup (when `--enable-websocket` flag is used)
   - Maintains in-memory candle cache for latest updates
   - Provides Server-Sent Events (SSE) endpoint at `/api/candles/stream`
   - Broadcasts candle updates to all connected SSE clients

3. **Frontend Consumer** (`frontend/src/App.tsx`)
   - Connects to SSE endpoint for real-time updates
   - Gracefully falls back to polling if SSE connection fails
   - Updates chart in real-time as candles close

## Usage

### Starting the API Server with WebSocket

```bash
# With WebSocket enabled (recommended for real-time updates)
python scripts/api_server.py --enable-websocket

# Without WebSocket (uses polling only)
python scripts/api_server.py
```

### Frontend Integration

The frontend automatically:
1. Loads initial candle data via REST API (`/api/candles`)
2. Establishes SSE connection to `/api/candles/stream`
3. Receives real-time candle updates as they occur
4. Falls back to 15-second polling if SSE fails

No frontend configuration changes are needed.

### Testing the Integration

Run the integration test script:

```bash
# Make sure DATABASE_URL is set
export DATABASE_URL="postgresql://user:pass@localhost/cryptotrader"

# Run the test
python scripts/test_websocket_integration.py
```

This will:
- Connect to Bitfinex WebSocket
- Subscribe to BTCUSD and ETHUSD 1m candles
- Print updates as they arrive
- Run until you press Ctrl+C

## Configuration

### Systemd Service

Update the dashboard API service to enable WebSocket:

```ini
# /etc/systemd/user/cryptotrader-dashboard-api.service
[Service]
ExecStart=/usr/bin/python /path/to/cryptotrader/scripts/api_server.py --enable-websocket
```

Then reload and restart:

```bash
systemctl --user daemon-reload
systemctl --user restart cryptotrader-dashboard-api.service
```

### Environment Variables

- `DATABASE_URL`: Required for all operations (existing requirement)

### WebSocket Manager Options

The `BitfinexWebSocketManager` class supports:

```python
from core.market_data.bitfinex_websocket import BitfinexWebSocketManager

# Create manager with callback
def on_update(update):
    print(f"Received: {update.symbol} {update.timeframe}")

manager = BitfinexWebSocketManager(callback=on_update)

# Start connection
manager.start()

# Subscribe to symbols
manager.subscribe("BTCUSD", "1m")
manager.subscribe("ETHUSD", "5m")

# Unsubscribe
manager.unsubscribe("BTCUSD", "1m")

# Stop
manager.stop()
```

## API Endpoints

### `/api/candles/stream` (SSE)

Server-Sent Events endpoint for real-time candle updates.

**Query Parameters:**
- `symbol` (required): Trading pair symbol (e.g., "BTCUSD")
- `timeframe` (required): Candle timeframe (e.g., "1m", "5m", "1h")

**Example:**
```javascript
const eventSource = new EventSource('/api/candles/stream?symbol=BTCUSD&timeframe=1m');

eventSource.onmessage = (event) => {
  const data = JSON.parse(event.data);
  if (data.type === 'candle_update') {
    console.log('New candle:', data.candle);
  }
};
```

**Event Types:**
- `connected`: Initial connection confirmation
- `candle_update`: New candle data received

## Benefits

### Before (Polling)
- Dashboard polled `/api/candles` every 15 seconds
- Database queried repeatedly for same data
- Latency: up to 1-2 minutes behind live market
- Unnecessary database load

### After (WebSocket + SSE)
- Updates arrive within seconds of candle close
- In-memory cache reduces database queries
- SSE pushes updates to clients instantly
- Graceful fallback to polling if WebSocket unavailable

## Rate Limits

**Bitfinex WebSocket API:**
- No explicit rate limits for public WebSocket connections
- Connection limit: ~30 concurrent subscriptions per connection
- Our implementation uses a single connection with multiple subscriptions

**No increase in API risk** because:
- WebSocket is a single persistent connection (vs. repeated REST calls)
- Bitfinex encourages WebSocket for real-time data
- Backfill timer still runs for gap detection/repair

## Troubleshooting

### WebSocket Not Connecting

Check logs for connection errors:
```bash
journalctl --user -u cryptotrader-dashboard-api.service -f
```

Common issues:
- Firewall blocking outbound WebSocket connections (port 443)
- Network requiring proxy configuration (not currently supported)

### SSE Connection Failing

Frontend will automatically fall back to polling. Check:
- Browser developer console for errors
- API server logs for SSE client connection attempts

### Candles Not Updating

1. Verify WebSocket is enabled: `ps aux | grep api_server`
2. Check if subscriptions are active: look for "Subscription confirmed" in logs
3. Ensure symbol/timeframe exists in database
4. Wait up to 1 minute for next candle to close (1m timeframe)

## Testing

Run the test suite:

```bash
# WebSocket manager unit tests
pytest tests/test_bitfinex_websocket.py -v

# All tests
pytest tests/
```

## Future Improvements

Potential enhancements (not in current scope):

- Support for multiple exchanges
- WebSocket authentication for private channels
- Client-side reconnection status indicator
- Configurable subscription limits
- WebSocket metrics/monitoring endpoint
