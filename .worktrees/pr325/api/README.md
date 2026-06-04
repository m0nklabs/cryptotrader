# Read-Only API

Minimal FastAPI-based HTTP API for candles and health checks.

## Features

- **GET /health** - Database connectivity and schema validation
- **GET /candles/latest** - Latest candles with query parameters
- Automatic API documentation (Swagger UI and ReDoc)
- No authentication (designed for local network only)
- Clear error messages and status codes

## Requirements

- Python 3.12+
- DATABASE_URL environment variable set
- PostgreSQL database with candles table

## Running the API

### Quick Start

```bash
# From repository root
python scripts/run_api.py
```

The API will start on `http://127.0.0.1:8000`

### Custom Host/Port

```bash
# Bind to all interfaces
python scripts/run_api.py --host 0.0.0.0 --port 8080

# Development mode (auto-reload)
python scripts/run_api.py --reload
```

## API Documentation

Once running, access interactive documentation at:

- **Swagger UI**: http://127.0.0.1:8000/docs
- **ReDoc**: http://127.0.0.1:8000/redoc

## Endpoints

### GET /health

Check database connectivity and schema.

**Response:**

```json
{
  "status": "ok",
  "database": {
    "connected": true,
    "candles_table_exists": true,
    "total_candles": 12345
  }
}
```

**Error Response (503):**

```json
{
  "status": "error",
  "database": {
    "connected": false,
    "error": "connection refused"
  }
}
```

### GET /candles/latest

Get latest candles for a trading pair.

**Query Parameters:**

- `exchange` (optional, default: "bitfinex") - Exchange name
- `symbol` (required) - Trading symbol (e.g., BTCUSD)
- `timeframe` (required) - Candle timeframe (e.g., 1m, 5m, 1h)
- `limit` (optional, default: 100, max: 5000) - Number of candles

**Example Request:**

```bash
curl "http://127.0.0.1:8000/candles/latest?symbol=BTCUSD&timeframe=1h&limit=50"
```

**Response:**

```json
{
  "exchange": "bitfinex",
  "symbol": "BTCUSD",
  "timeframe": "1h",
  "count": 50,
  "latest_open_time": "2025-12-24T10:00:00+00:00",
  "latest_open_time_ms": 1735034400000,
  "candles": [
    {
      "open_time": "2025-12-24T08:00:00+00:00",
      "open_time_ms": 1735027200000,
      "open": 98765.43,
      "high": 99000.00,
      "low": 98500.00,
      "close": 98800.00,
      "volume": 123.456
    }
  ]
}
```

**Error Response (404):**

```json
{
  "error": "no_data",
  "message": "No candles found for bitfinex:BTCUSD:1h"
}
```

## Examples

See `scripts/api_example.py` for usage examples.

## Architecture

- **FastAPI**: Modern, fast web framework with automatic API docs
- **PostgresStores**: Database access layer from core.storage
- **Async endpoints**: Non-blocking I/O for better performance
- **Global error handling**: Consistent error responses

## Security Notes

- No authentication implemented (designed for local network)
- Never exposes DATABASE_URL in responses
- Read-only operations only
- No trading or execution endpoints

## Port Assignment

Default port: **8000** (see `docs/PORTS.md` for all services)

## Testing

Run the test suite:

```bash
pytest tests/test_api.py -v
```

## Development

For development with auto-reload:

```bash
python scripts/run_api.py --reload
```

## See Also

- `docs/ARCHITECTURE.md` - System architecture
- `docs/DEVELOPMENT.md` - Development guide
- `docs/FRONTEND.md` - Frontend integration
