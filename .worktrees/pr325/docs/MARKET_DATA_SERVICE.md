# Market Data Service - Architecture Proposal

## Vision

A standalone, continuously running market data service that:
1. **Collects** historical OHLCV candles from exchanges (Bitfinex first)
2. **Maintains** data integrity via gap detection and repair
3. **Streams** realtime updates via WebSocket
4. **Serves** data via REST API to any consumer

## Why Separate?

| Current State | Target State |
|---------------|--------------|
| Embedded in cryptotrader repo | Standalone `m0nklabs/market-data` repo |
| Tied to trading workflows | Independent service, any consumer |
| Manual/timer-based runs | Continuous daemon with health checks |
| Single exchange hardcoded | Multi-exchange support (pluggable) |

## Proposed Repository: `m0nklabs/market-data`

```
market-data/
├── README.md
├── pyproject.toml
├── requirements.txt
├── docker-compose.yml          # Postgres + service
├── Makefile
│
├── src/
│   └── market_data/
│       ├── __init__.py
│       ├── config.py           # Pydantic settings
│       ├── types.py            # Candle, Gap, Job types
│       │
│       ├── exchanges/          # Exchange adapters
│       │   ├── __init__.py
│       │   ├── base.py         # ExchangeAdapter protocol
│       │   ├── bitfinex.py     # Bitfinex REST + WS
│       │   └── binance.py      # Future: Binance
│       │
│       ├── storage/            # Persistence layer
│       │   ├── __init__.py
│       │   ├── postgres.py     # PostgreSQL implementation
│       │   └── schema.sql      # DB schema
│       │
│       ├── services/           # Core services
│       │   ├── __init__.py
│       │   ├── backfill.py     # Historical ingestion
│       │   ├── realtime.py     # WebSocket streaming
│       │   ├── gap_repair.py   # Gap detection/repair
│       │   └── health.py       # Health checks
│       │
│       ├── api/                # REST API
│       │   ├── __init__.py
│       │   ├── main.py         # FastAPI app
│       │   └── routes/
│       │       ├── candles.py  # GET /candles
│       │       ├── status.py   # GET /health, /status
│       │       └── gaps.py     # GET /gaps
│       │
│       └── daemon.py           # Main entry point
│
├── tests/
│   └── ...
│
└── systemd/                    # Service files
    ├── market-data.service
    └── market-data-api.service
```

## Core Components

### 1. Exchange Adapters (Pluggable)

```python
class ExchangeAdapter(Protocol):
    """Protocol for exchange data sources."""

    async def fetch_candles(
        self,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> list[Candle]:
        """Fetch historical candles."""
        ...

    async def subscribe_candles(
        self,
        symbol: str,
        timeframe: str,
        callback: Callable[[Candle], None],
    ) -> None:
        """Subscribe to realtime candle updates."""
        ...

    def get_symbols(self) -> list[str]:
        """List available trading pairs."""
        ...
```

### 2. Daemon Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Market Data Daemon                       │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │  Backfill   │  │  Realtime   │  │    Gap Repair       │  │
│  │  Service    │  │  Streamer   │  │    Service          │  │
│  │             │  │             │  │                     │  │
│  │ - On startup│  │ - WebSocket │  │ - Periodic scan     │  │
│  │ - Fill gaps │  │ - Candle    │  │ - Auto repair       │  │
│  │ - Resume    │  │   updates   │  │ - Alert on failure  │  │
│  └──────┬──────┘  └──────┬──────┘  └──────────┬──────────┘  │
│         │                │                     │             │
│         └────────────────┼─────────────────────┘             │
│                          │                                   │
│                   ┌──────▼──────┐                            │
│                   │  PostgreSQL │                            │
│                   │   Candles   │                            │
│                   └─────────────┘                            │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 3. REST API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/status` | GET | Ingestion status per symbol/timeframe |
| `/candles` | GET | Query candles (exchange, symbol, tf, start, end) |
| `/candles/latest` | GET | Get N most recent candles |
| `/gaps` | GET | List detected gaps |
| `/symbols` | GET | List available symbols per exchange |

### 4. Configuration

```yaml
# config.yaml
exchanges:
  bitfinex:
    enabled: true
    symbols:
      - BTCUSD
      - ETHUSD
      - SOLUSD
    timeframes:
      - 1m
      - 5m
      - 1h
      - 1d

database:
  url: postgresql://user:pass@localhost:5432/marketdata

daemon:
  backfill_on_startup: true
  backfill_days: 365
  gap_repair_interval_minutes: 60
  health_check_interval_seconds: 30

api:
  host: 0.0.0.0
  port: 8100
```

## Migration Plan

### Phase 1: Extract (Keep Both Working)
1. Create new `m0nklabs/market-data` repo
2. Copy relevant code from cryptotrader
3. Refactor into new structure
4. Add tests

### Phase 2: Deploy Standalone
1. Deploy market-data service
2. Point cryptotrader to use market-data API
3. Validate data consistency

### Phase 3: Remove from Cryptotrader
1. Remove `core/market_data/*` from cryptotrader
2. Update cryptotrader to fetch candles via API
3. Update systemd services

## Consumer Integration

### From Cryptotrader (Python)

```python
class MarketDataClient:
    """Client for market-data service."""

    def __init__(self, base_url: str = "http://localhost:8100"):
        self.base_url = base_url

    async def get_candles(
        self,
        exchange: str,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> list[Candle]:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.base_url}/candles",
                params={
                    "exchange": exchange,
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "start": start.isoformat(),
                    "end": end.isoformat(),
                }
            )
            resp.raise_for_status()
            return [Candle(**c) for c in resp.json()]
```

### From Frontend (TypeScript)

```typescript
const fetchCandles = async (
  symbol: string,
  timeframe: string,
  limit: number
): Promise<Candle[]> => {
  const response = await fetch(
    `http://localhost:8100/candles/latest?symbol=${symbol}&timeframe=${timeframe}&limit=${limit}`
  );
  return response.json();
};
```

## Database Schema

```sql
-- Candles table (same as current)
CREATE TABLE candles (
    id BIGSERIAL PRIMARY KEY,
    exchange VARCHAR(50) NOT NULL,
    symbol VARCHAR(50) NOT NULL,
    timeframe VARCHAR(10) NOT NULL,
    open_time TIMESTAMP NOT NULL,
    close_time TIMESTAMP NOT NULL,
    open DECIMAL(20, 8) NOT NULL,
    high DECIMAL(20, 8) NOT NULL,
    low DECIMAL(20, 8) NOT NULL,
    close DECIMAL(20, 8) NOT NULL,
    volume DECIMAL(30, 8) NOT NULL,
    CONSTRAINT uq_candles UNIQUE (exchange, symbol, timeframe, open_time)
);

-- Ingestion jobs tracking
CREATE TABLE ingestion_jobs (
    id SERIAL PRIMARY KEY,
    exchange VARCHAR(50) NOT NULL,
    symbol VARCHAR(50) NOT NULL,
    timeframe VARCHAR(10) NOT NULL,
    status VARCHAR(20) NOT NULL,
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    candles_fetched INT DEFAULT 0,
    last_error TEXT
);

-- Gap tracking
CREATE TABLE candle_gaps (
    id SERIAL PRIMARY KEY,
    exchange VARCHAR(50) NOT NULL,
    symbol VARCHAR(50) NOT NULL,
    timeframe VARCHAR(10) NOT NULL,
    gap_start TIMESTAMP NOT NULL,
    gap_end TIMESTAMP NOT NULL,
    detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    repaired_at TIMESTAMP,
    CONSTRAINT uq_gap UNIQUE (exchange, symbol, timeframe, gap_start)
);
```

## Next Steps

1. **Create repo**: `gh repo create m0nklabs/market-data --public`
2. **Bootstrap structure**: Use existing code as starting point
3. **Add daemon**: Continuous runner with all services
4. **Deploy**: Docker or systemd on server
5. **Integrate**: Update cryptotrader to use API

---

*This service becomes the single source of truth for all historical and realtime market data.*
