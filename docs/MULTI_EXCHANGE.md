# Multi-Exchange Support

cryptotrader v2 supports ingesting market data from multiple exchanges:

- **Bitfinex** (default)
- **Binance** (high liquidity, good API)
- **Kraken** (EUR pairs support)

## Architecture

The exchange abstraction is implemented using the `ExchangeProvider` interface in `core/market_data/base.py`:

```python
from core.market_data import get_provider

# Get a provider instance
provider = get_provider("binance")  # or "bitfinex", "kraken"

# Fetch candles
candles = provider.iter_candles(
    symbol="BTCUSD",
    timeframe="1h",
    start=start_datetime,
    end=end_datetime,
)
```

## Backfilling Data

The `core/market_data/bitfinex_backfill.py` script now supports all exchanges via the `--exchange` flag:

### Bitfinex (default)

```bash
python -m core.market_data.bitfinex_backfill \
    --exchange bitfinex \
    --symbol BTCUSD \
    --timeframe 1h \
    --start 2024-01-01 \
    --end 2024-01-31
```

### Binance

```bash
python -m core.market_data.bitfinex_backfill \
    --exchange binance \
    --symbol BTCUSD \
    --timeframe 1h \
    --start 2024-01-01 \
    --end 2024-01-31
```

**Note:** Binance automatically converts `BTCUSD` to `BTCUSDT` as Binance uses USDT for most trading pairs.

### Kraken

```bash
python -m core.market_data.bitfinex_backfill \
    --exchange kraken \
    --symbol BTCUSD \
    --timeframe 1h \
    --start 2024-01-01 \
    --end 2024-01-31
```

**Note:** Kraken uses special symbol mappings (e.g., `BTCUSD` → `XXBTZUSD`). The provider handles this automatically.

## Resume Mode

All exchanges support resume mode to continue from the last ingested candle:

```bash
python -m core.market_data.bitfinex_backfill \
    --exchange binance \
    --symbol BTCUSD \
    --timeframe 1m \
    --resume
```

## Dashboard Exchange Selector

The frontend dashboard includes an exchange selector in the **Market Watch** panel:

1. Click the dropdown next to "Exchange"
2. Select your desired exchange (Bitfinex, Binance, or Kraken)
3. The available symbols and chart data will update automatically

![Exchange Selector](https://github.com/user-attachments/assets/3712db39-2f20-4ea7-8e36-c56e6ed43682)

## Supported Timeframes

All exchanges support the following timeframes:

- `1m` - 1 minute
- `5m` - 5 minutes
- `15m` - 15 minutes
- `1h` - 1 hour
- `4h` - 4 hours
- `1d` - 1 day

## Exchange-Specific Notes

### Bitfinex
- Symbol prefix: Symbols are automatically prefixed with `t` (e.g., `BTCUSD` → `tBTCUSD`)
- Rate limits: 90 requests per minute (managed by automatic retry with exponential backoff)

### Binance
- Symbol format: Most pairs use USDT (e.g., `BTCUSD` → `BTCUSDT`)
- Rate limits: 1200 requests per minute (managed by automatic retry with exponential backoff)
- Page size: 1000 candles per request

### Kraken
- Symbol mapping: Uses X/Z prefixes for crypto/fiat (e.g., `BTCUSD` → `XXBTZUSD`)
- Rate limits: Variable tier-based limits (managed by automatic retry with exponential backoff)
- Timeframe format: Uses minutes (e.g., `1h` → `60`)

## Database Schema

The `candles` table is exchange-agnostic and stores data from all exchanges:

```sql
CREATE TABLE candles (
    exchange VARCHAR(50) NOT NULL,
    symbol VARCHAR(50) NOT NULL,
    timeframe VARCHAR(10) NOT NULL,
    open_time TIMESTAMP NOT NULL,
    ...
    CONSTRAINT uq_candles_exchange_symbol_tf_open_time 
        UNIQUE (exchange, symbol, timeframe, open_time)
);
```

This allows you to store and query candles from multiple exchanges simultaneously.

## API Endpoints

The API server (`scripts/api_server.py`) supports the `exchange` parameter:

```bash
# Get available symbols for an exchange
GET /api/candles/available?exchange=binance

# Get candles for a specific exchange
GET /api/candles?exchange=binance&symbol=BTCUSD&timeframe=1h&limit=100

# Get signals for an exchange
GET /api/signals?exchange=binance&limit=10
```

## Adding New Exchanges

To add support for a new exchange:

1. Create a new provider class in `core/market_data/<exchange>_provider.py`
2. Implement the `ExchangeProvider` interface:
   - `exchange_name` property
   - `get_timeframe_spec()` method
   - `iter_candles()` method
3. Register the provider in `core/market_data/__init__.py` in the `get_provider()` function
4. Add tests in `tests/test_exchange_providers.py`
5. Update this documentation

## Testing

Run the exchange provider tests:

```bash
python -m pytest tests/test_exchange_providers.py -v
```

The test suite includes:
- Provider factory tests
- Timeframe specification tests
- Symbol normalization tests
- Error handling tests
