# Quick Testing Guide - Real-time Candle Streaming

This guide provides quick commands to test the WebSocket/SSE candle streaming feature.

## Prerequisites

```bash
# Install dependencies
pip install -r requirements.txt -r requirements-dev.txt
cd frontend && npm install && cd ..

# Set database URL
export DATABASE_URL="postgresql://user:pass@localhost:5432/cryptotrader"
```

## Backend Testing

### 1. Unit Tests
```bash
# Run all streaming tests
pytest tests/test_api_candle_stream.py -v

# Run WebSocket infrastructure tests
pytest tests/test_websocket_client.py tests/test_websocket_provider.py -v

# Run all API tests
pytest tests/test_api*.py -v
```

### 2. Integration Test
```bash
# Test service initialization and broadcast
python scripts/test_candle_stream.py
```

### 3. Live WebSocket Demo
```bash
# Architecture overview only
python scripts/demo_sse_stream.py --skip-live

# Connect to live Bitfinex WebSocket (requires network)
python scripts/demo_sse_stream.py
```

### 4. Start API Server
```bash
# Start on localhost:8000
python scripts/run_api.py

# With auto-reload for development
python scripts/run_api.py --reload

# Bind to all interfaces
python scripts/run_api.py --host 0.0.0.0 --port 8000
```

## Manual API Testing

### Test SSE Streaming
```bash
# Subscribe to BTCUSD 1m candles (blocks, press Ctrl+C to stop)
curl -N http://127.0.0.1:8000/candles/stream?symbol=BTCUSD&timeframe=1m

# Alternative: using httpie
http --stream GET http://127.0.0.1:8000/candles/stream symbol==BTCUSD timeframe==1m
```

Expected output:
```
data: {"type":"candle","symbol":"BTCUSD","timeframe":"1m","t":1704110400000,"o":50000.0,"h":50100.0,"l":49900.0,"c":50050.0,"v":10.5}

data: {"type":"heartbeat","timestamp":1704110430000}

data: {"type":"candle","symbol":"BTCUSD","timeframe":"1m","t":1704110460000,"o":50050.0,"h":50150.0,"l":50000.0,"c":50100.0,"v":8.3}
```

### Check Connection Status
```bash
curl http://127.0.0.1:8000/candles/stream/status | jq
```

Expected output:
```json
{
  "active_streams": 1,
  "total_subscribers": 2,
  "streams": [
    {
      "key": "BTCUSD:1m",
      "subscribers": 2,
      "connected": true
    }
  ]
}
```

### Test Traditional Endpoints
```bash
# Health check
curl http://127.0.0.1:8000/health | jq

# Get latest candles
curl "http://127.0.0.1:8000/candles/latest?symbol=BTCUSD&timeframe=1m&limit=10" | jq
```

## Frontend Testing

### 1. TypeScript Compilation
```bash
cd frontend
npx tsc --noEmit
```

### 2. Start Development Server
```bash
cd frontend
npm run dev
```

Visit http://localhost:5176

### 3. Browser Testing Checklist

**Visual Indicators:**
- [ ] Chart subtitle shows "(live ⚡)" when SSE connected
- [ ] Chart subtitle shows "(polling)" when falling back
- [ ] Chart updates smoothly without full page reload

**DevTools Network Tab:**
- [ ] See EventSource connection to `/candles/stream`
- [ ] Status: "pending" (stays open)
- [ ] Type: "eventsource"
- [ ] Messages appear in real-time

**DevTools Console:**
- [ ] `[CandleStream] Connected to /candles/stream?...`
- [ ] No error messages
- [ ] Optional: Set debug messages visible

**Fallback Testing:**
- [ ] Disable network in DevTools → should switch to "(polling)"
- [ ] Enable network → should reconnect and show "(live ⚡)"
- [ ] Chart continues updating in both modes

## Debugging

### Check Logs
```bash
# Backend logs (if using systemd)
journalctl -u cryptotrader-dashboard-api -f

# Development mode logs (stdout)
# Look for lines like:
# INFO: WebSocket connected
# INFO: Subscribed to BTCUSD:1m
# INFO: New SSE subscriber for BTCUSD:1m (total: 1)
```

### Common Issues

**SSE not connecting:**
```bash
# Check API server is running
curl http://127.0.0.1:8000/health

# Check endpoint exists
curl -I http://127.0.0.1:8000/candles/stream

# Expected: HTTP/1.1 200 OK with Content-Type: text/event-stream
```

**No candle updates:**
```bash
# Check WebSocket connection
curl http://127.0.0.1:8000/candles/stream/status

# If connected=false, check:
# - Internet connectivity
# - Bitfinex API status
# - Firewall/proxy settings
```

**High memory usage:**
```bash
# Check active streams
curl http://127.0.0.1:8000/candles/stream/status

# If many streams, they will be cleaned up when clients disconnect
# Can restart API server to force cleanup
```

## Performance Testing

### Monitor Resource Usage
```bash
# CPU and memory
ps aux | grep "python.*run_api"

# Network connections
netstat -an | grep :8000

# Active SSE connections
curl http://127.0.0.1:8000/candles/stream/status
```

### Load Testing (optional)
```bash
# Multiple concurrent SSE clients
for i in {1..10}; do
  curl -N http://127.0.0.1:8000/candles/stream?symbol=BTCUSD&timeframe=1m &
done

# Check status
curl http://127.0.0.1:8000/candles/stream/status

# Kill all background curl processes
killall curl
```

Expected: Single WebSocket connection regardless of client count.

## Expected Behavior

### Normal Operation
1. Frontend connects via SSE within 1-2 seconds
2. Chart subtitle shows "(live ⚡)"
3. Candles update within 1-2 seconds of close on Bitfinex
4. Heartbeat messages every 30 seconds keep connection alive
5. Status endpoint shows `connected: true`

### Fallback Mode
1. SSE connection fails (network issue, server restart, etc.)
2. Frontend automatically switches to polling mode
3. Chart subtitle shows "(polling)"
4. Candles update every 15 seconds via HTTP
5. Chart remains functional

### Recovery
1. When server/network recovers
2. Frontend attempts reconnection (up to 5 attempts)
3. If successful, switches back to "(live ⚡)"
4. Full chart refresh after reconnection

## Success Criteria

✅ All unit tests pass
✅ Integration test passes
✅ SSE endpoint returns proper EventSource format
✅ Frontend shows "(live ⚡)" when connected
✅ Chart updates within seconds of candle close
✅ Graceful fallback to "(polling)" on disconnect
✅ Status endpoint shows correct connection info
✅ No memory leaks after extended running
✅ Single WebSocket per symbol regardless of client count

## Additional Resources

- Full documentation: `docs/REALTIME_CANDLES.md`
- Unit tests: `tests/test_api_candle_stream.py`
- Integration test: `scripts/test_candle_stream.py`
- Demo script: `scripts/demo_sse_stream.py`
