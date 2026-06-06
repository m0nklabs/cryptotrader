# CryptoTrader API Documentation

## Endpoints

### GET /health

Read-only health check endpoint. Returns the application status without depending on the database or any external services.

- **Method**: `GET`
- **Authentication**: None (public, no auth required)
- **Response code**: Always `200 OK`

**Response schema:**

```json
{
  "status": "ok",
  "uptime_seconds": 12345,
  "version": "0.1.0"
}
```

| Field              | Type   | Description                                      |
|--------------------|--------|--------------------------------------------------|
| `status`           | string | Always `"ok"`. Indicates the API is running.      |
| `uptime_seconds`   | int    | Seconds since the application started.            |
| `version`          | string | Application version from the `APP_VERSION` env var. |

**Alias:** `/healthz` is an alias for `/health` (same handler, same response).

**Example request:**

```bash
curl http://localhost:8000/health
```

**Example response:**

```json
{
  "status": "ok",
  "uptime_seconds": 3600,
  "version": "0.1.0"
}
```

---

### GET /version

Returns the application version string.

- **Method**: `GET`
- **Authentication**: None
- **Response code**: `200 OK`

**Response schema:**

```json
{
  "version": "0.1.0"
}
```

---

### GET /ingestion/status

Get ingestion status for a specific exchange, symbol, and timeframe. Checks database connectivity and schema.

- **Method**: `GET`
- **Authentication**: None
- **Query parameters:**

| Parameter  | Required | Default   | Description                    |
|------------|----------|-----------|--------------------------------|
| `exchange` | No       | `bitfinex` | Exchange name.                 |
| `symbol`   | Yes      | —          | Trading symbol (e.g., `BTCUSD`). |
| `timeframe`| Yes      | —          | Timeframe (e.g., `1m`, `1h`).  |

**Response schema:**

```json
{
  "latest_candle_open_time": 1234567890000,
  "candles_count": 100000,
  "schema_ok": true,
  "db_ok": true
}
```

---

### GET /system/status

Comprehensive system health status including backend and database.

- **Method**: `GET`
- **Authentication**: None
- **Response code**: `200 OK`

**Response schema:**

```json
{
  "backend": {
    "status": "ok",
    "uptime_seconds": 12345
  },
  "database": {
    "status": "ok",
    "connected": true,
    "latency_ms": 2.34
  },
  "timestamp": 1234567890000
}
```

---

### GET /gaps/summary

Get candle gap summary statistics.

- **Method**: `GET`
- **Authentication**: None
- **Response code**: `200 OK` (or `503` on error)

**Response schema:**

```json
{
  "open_gaps": 5,
  "repaired_24h": 12,
  "oldest_open_gap": 1234567890000
}
```

---

## Paper Trading Endpoints

### POST /orders

Place a paper order.

- **Method**: `POST`
- **Authentication**: None
- **Request body**: `OrderIntent` (JSON)

**Response code**: `200 OK` or `400 Bad Request`

---

### GET /orders

List open paper orders.

- **Method**: `GET`
- **Authentication**: None
- **Response code**: `200 OK`

---

### DELETE /orders/{order_id}

Cancel a paper order by ID.

- **Method**: `DELETE`
- **Authentication**: None
- **Path parameter**: `order_id` (string)
- **Response code**: `200 OK` or `404 Not Found`

---

### GET /positions

List open paper positions.

- **Method**: `GET`
- **Authentication**: None
- **Response code**: `200 OK`

---

## Candles

### GET /candles/latest

Get the latest candles with optional filtering.

- **Method**: `GET`
- **Authentication**: None
- **Query parameters:**

| Parameter  | Required | Default   | Description                    |
|------------|----------|-----------|--------------------------------|
| `exchange` | No       | `bitfinex` | Exchange name.                 |
| `symbol`   | Yes      | —          | Trading symbol (e.g., `BTCUSD`). |
| `timeframe`| Yes      | —          | Timeframe (e.g., `1m`, `1h`).  |

**Response code**: `200 OK`

---

## Market Cap

### GET /market-cap

Get current market cap rankings from CoinGecko.

- **Method**: `GET`
- **Authentication**: None
- **Response code**: `200 OK`

---

## Authentication

All endpoints are accessible without authentication. The API is designed for local network access only.

## Requirements

- `DATABASE_URL` must be set in the environment for most endpoints.
- The `/health` and `/version` endpoints work without a database.
