# Multi-Exchange Support

CryptoTrader v2 supports ingesting market data from multiple exchanges. This guide explains how to configure and use additional exchanges beyond the default Bitfinex.

## Supported Exchanges

- **Bitfinex** (default) - USD pairs, high liquidity
- **Binance** - USDT pairs, highest volume globally

## Quick Start

### 1. Bootstrap a New Exchange

Use the `bootstrap_symbols.py` script with the `--exchange` flag:

```bash
# Bootstrap Binance with default symbols
python scripts/bootstrap_symbols.py --exchange binance --lookback-days 3

# Bootstrap specific symbols
python scripts/bootstrap_symbols.py \
  --exchange binance \
  --symbols BTCUSDT,ETHUSDT,SOLUSDT \
  --timeframe 1m \
  --lookback-days 7
```

### 2. Manual Backfill

You can also run backfills manually for each exchange:

#### Binance

```bash
python -m core.market_data.binance_backfill \
  --symbol BTCUSDT \
  --timeframe 1h \
  --start 2024-01-01 \
  --end 2024-12-31 \
  --exchange binance
```

#### Bitfinex

```bash
python -m core.market_data.bitfinex_backfill \
  --symbol BTCUSD \
  --timeframe 1h \
  --start 2024-01-01 \
  --end 2024-12-31 \
  --exchange bitfinex
```

### 3. Resume Backfills

Both exchange adapters support `--resume` to continue from the latest candle:

```bash
python -m core.market_data.binance_backfill \
  --symbol BTCUSDT \
  --timeframe 1m \
  --resume \
  --exchange binance
```

## Exchange-Specific Notes

### Binance

- **Symbol Format**: Uppercase without separators (e.g., `BTCUSDT`)
  - The adapter automatically converts `BTCUSD` → `BTCUSDT`
  - Removes separators: `BTC/USDT` → `BTCUSDT`
- **Rate Limits**: 1200 requests per minute (enforced by automatic backoff)
- **Max Candles per Request**: 1000
- **Supported Timeframes**: `1m`, `5m`, `15m`, `1h`, `4h`, `1d`

### Bitfinex

- **Symbol Format**: Prefixed with `t` (e.g., `tBTCUSD`)
  - The adapter automatically adds the `t` prefix
- **Rate Limits**: Handled with exponential backoff (default: 0.5s → 8s)
- **Max Candles per Request**: 10,000
- **Supported Timeframes**: `1m`, `5m`, `15m`, `1h`, `4h`, `1d`

## Dashboard Usage

### Switching Exchanges

The dashboard includes an exchange selector in the **Market Watch** panel:

1. Click the dropdown next to "Exchange"
2. Select `Bitfinex` or `Binance`
3. The chart and available symbols will update automatically

### Exchange-Specific Behavior

- **Symbol Lists**: Each exchange shows only symbols with available data in the database
- **Ingestion Status**: The "Market Data" panel displays status for the selected exchange
- **Real-time Updates**: WebSocket/SSE streams are exchange-specific

## Database Schema

All exchanges share the same database schema. Candles are differentiated by the `exchange` column:

```sql
SELECT exchange, symbol, timeframe, COUNT(*) as candle_count
FROM candles
GROUP BY exchange, symbol, timeframe
ORDER BY exchange, symbol, timeframe;
```

Example output:
```
 exchange | symbol  | timeframe | candle_count
----------+---------+-----------+--------------
 binance  | BTCUSDT | 1m        | 43200
 binance  | ETHUSDT | 1m        | 43200
 bitfinex | BTCUSD  | 1m        | 50400
 bitfinex | ETHUSD  | 1m        | 50400
```

## Systemd Integration

If using systemd timers for automated ingestion:

### Creating Exchange-Specific Units

The bootstrap script creates instance-specific environment files:

```bash
~/.config/cryptotrader/
├── binance-backfill-BTCUSDT-1m.env
├── binance-realtime-BTCUSDT-1m.env
├── bitfinex-backfill-BTCUSD-1m.env
└── bitfinex-realtime-BTCUSD-1m.env
```

### Managing Timers

```bash
# List all timers
systemctl --user list-timers 'cryptotrader-*'

# Enable Binance realtime ingestion
systemctl --user enable --now cryptotrader-binance-realtime@BTCUSDT-1m.timer

# Check status
systemctl --user status cryptotrader-binance-realtime@BTCUSDT-1m.timer
```

## API Endpoints

All API endpoints support the `exchange` parameter:

```bash
# Get latest candles for Binance
curl "http://localhost:8000/api/candles/latest?exchange=binance&symbol=BTCUSDT&timeframe=1m&limit=100"

# Get available pairs for Binance
curl "http://localhost:8000/api/candles/available?exchange=binance"

# Check ingestion status
curl "http://localhost:8000/ingestion/status?exchange=binance&symbol=BTCUSDT&timeframe=1m"
```

## Troubleshooting

### No Data Appearing for New Exchange

1. Verify the backfill completed successfully:
   ```sql
   SELECT * FROM market_data_jobs 
   WHERE exchange = 'binance' 
   ORDER BY created_at DESC 
   LIMIT 5;
   ```

2. Check for errors in job runs:
   ```sql
   SELECT * FROM market_data_job_runs 
   WHERE status = 'failed' 
   ORDER BY started_at DESC 
   LIMIT 5;
   ```

### Symbol Format Issues

- **Binance**: Use `BTCUSDT` not `BTCUSD` or `tBTCUSD`
- **Bitfinex**: Use `BTCUSD` (the `t` prefix is added automatically)

### Rate Limiting

Both adapters include automatic retry with exponential backoff. If you encounter persistent rate limit errors:

```bash
# Increase backoff parameters
python -m core.market_data.binance_backfill \
  --symbol BTCUSDT \
  --timeframe 1m \
  --start 2024-01-01 \
  --initial-backoff-seconds 1.0 \
  --max-backoff-seconds 16.0 \
  --jitter-seconds 0.5
```

## Adding New Exchanges

To add support for a new exchange:

1. Create a new adapter module: `core/market_data/<exchange>_backfill.py`
2. Implement the standard interface (see `core/market_data/base.py`)
3. Update `scripts/bootstrap_symbols.py` to include the new exchange
4. Add the exchange to the frontend dropdown
5. Update this documentation

See `core/market_data/binance_backfill.py` as a reference implementation.

## Related Documentation

- [Database Schema](../db/schema.sql)
- [API Documentation](../api/README.md)
- [Bootstrap Script](../scripts/bootstrap_symbols.py)
