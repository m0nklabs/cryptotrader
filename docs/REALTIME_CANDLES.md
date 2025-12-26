# Real-time Candle Updates via WebSocket

This document describes the real-time candle streaming implementation using Server-Sent Events (SSE) and WebSocket technology.

## Overview

The system provides near-instant candle updates with automatic fallback to polling, reducing latency from ~1-2 minutes to just a few seconds.

### Architecture

```
Bitfinex WebSocket API
        ↓
BitfinexWebSocketCandleProvider
        ↓
CandleStreamService (Backend)
        ↓ (SSE)
Frontend EventSource
        ↓
Chart Component
```

## Components

### Backend

#### 1. `api/candle_stream.py` - Streaming Service

**CandleStreamService**
- Singleton service managing WebSocket connections
- Maintains one WebSocket connection per symbol/timeframe
- Broadcasts updates to multiple SSE clients
- Thread-safe subscription management

Key features:
- In-memory broadcast to all connected clients
- Automatic reconnection on disconnect
- Latest candle caching
- Connection status monitoring

#### 2. FastAPI Endpoints

**GET /candles/stream**
- Parameters: `symbol`, `timeframe`
- Returns: SSE stream with real-time candle updates
- Format: JSON events via Server-Sent Events

**GET /candles/stream/status**
- Returns: Connection status for all active streams
- Useful for monitoring and debugging

### Frontend

#### 1. `frontend/src/api/candleStream.ts` - SSE Client

**CandleStream class**
- Manages EventSource connection
- Automatic reconnection with exponential backoff
- Error handling and callbacks
- Connection status tracking

#### 2. `frontend/src/App.tsx` - Integration

- Attempts SSE connection first
- Falls back to polling on error
- Visual indicator (⚡) when streaming is active
- Periodic full refresh every 60s

## Usage

### Starting the API Server

```bash
# Set up environment
export DATABASE_URL="postgresql://user:pass@localhost:5432/cryptotrader"

# Start FastAPI server
python scripts/run_api.py --host 127.0.0.1 --port 8000
```

The SSE endpoint will be available at:
```
http://127.0.0.1:8000/candles/stream?symbol=BTCUSD&timeframe=1m
```

### Frontend Integration

The frontend automatically uses SSE when available:

```typescript
import { createCandleStream } from './api/candleStream'

const stream = createCandleStream(
  'BTCUSD',
  '1m',
  (candle) => {
    console.log('New candle:', candle)
    updateChart(candle)
  }
)
```

### Testing

Run the integration tests:

```bash
# Unit tests
pytest tests/test_api_candle_stream.py -v

# Integration test
python scripts/test_candle_stream.py

# Demo (shows architecture only)
python scripts/demo_sse_stream.py --skip-live

# Demo with live WebSocket (requires network access)
python scripts/demo_sse_stream.py
```

## Benefits

1. **Low Latency**: Updates within 1-2 seconds vs 15-120 seconds with polling
2. **Efficient**: Single WebSocket connection shared by multiple clients
3. **Reliable**: Automatic reconnection and fallback to polling
4. **Scalable**: Broadcast pattern supports many concurrent clients
5. **Rate-Limit Safe**: No increase in Bitfinex API usage

## Fallback Behavior

The system gracefully handles failures:

1. **SSE Connection Fails**
   - Frontend automatically switches to polling mode
   - Polls every 15 seconds as before
   - Visual indicator shows polling mode

2. **WebSocket to Bitfinex Fails**
   - Backend attempts automatic reconnection
   - Exponential backoff (1s, 2s, 4s, 8s, 16s)
   - Max 5 reconnection attempts before giving up

3. **Network Issues**
   - Frontend EventSource auto-reconnects
   - Backend WebSocket auto-reconnects
   - Chart continues to update via polling

## Monitoring

Check active streams:

```bash
curl http://127.0.0.1:8000/candles/stream/status
```

Response:
```json
{
  "active_streams": 2,
  "total_subscribers": 5,
  "streams": [
    {
      "key": "BTCUSD:1m",
      "subscribers": 3,
      "connected": true
    },
    {
      "key": "ETHUSD:5m",
      "subscribers": 2,
      "connected": true
    }
  ]
}
```

## Configuration

No additional configuration required. The system uses existing settings:

- `DATABASE_URL` - For historical candle data
- No API keys needed for public WebSocket endpoint

## Security Considerations

1. **Rate Limiting**: Only one WebSocket connection per symbol/timeframe regardless of client count
2. **No Authentication**: Public read-only endpoint (local network only)
3. **Resource Management**: Automatic cleanup when no subscribers remain

## Performance

- **Latency**: < 1 second from Bitfinex to frontend
- **Memory**: ~1MB per active WebSocket connection
- **CPU**: Minimal (async event-driven)
- **Network**: Same as current polling (1 req/min vs 4 req/min)

## Troubleshooting

### SSE Not Connecting

1. Check FastAPI server is running
2. Verify `/candles/stream` endpoint exists
3. Check browser console for errors
4. Verify no proxy/firewall blocking SSE

### No Candle Updates

1. Check WebSocket connection to Bitfinex
2. Verify market is open and has activity
3. Check `/candles/stream/status` endpoint
4. Review backend logs for errors

### High Memory Usage

1. Check number of active streams
2. Verify old connections are being cleaned up
3. Restart API server if needed

## Future Enhancements

Potential improvements:

1. **Compression**: Gzip SSE stream for bandwidth savings
2. **Delta Updates**: Send only changed fields
3. **Multiple Symbols**: Single SSE connection for multiple symbols
4. **Persistence**: Store candles to database in real-time
5. **Metrics**: Prometheus metrics for monitoring

## Related Files

- `api/candle_stream.py` - Backend streaming service
- `api/main.py` - FastAPI endpoints
- `core/market_data/websocket_provider.py` - WebSocket provider
- `cex/bitfinex/api/websocket_client.py` - Bitfinex WebSocket client
- `frontend/src/api/candleStream.ts` - Frontend SSE client
- `frontend/src/App.tsx` - Chart integration
- `tests/test_api_candle_stream.py` - Unit tests
- `scripts/test_candle_stream.py` - Integration test
- `scripts/demo_sse_stream.py` - Demo script
