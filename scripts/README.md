# Market Data Ingestion Scripts

This directory contains scripts for ingesting and managing candle (OHLCV) data from exchanges.

## Multi-Timeframe Ingestion

The `ingest_multi_timeframe.py` script provides a convenient way to ingest candles for multiple timeframes and symbols.

### Standard Timeframes

The following timeframes are supported and ingested by default:
- **1m** - 1 minute
- **5m** - 5 minutes
- **15m** - 15 minutes
- **1h** - 1 hour
- **4h** - 4 hours
- **1d** - 1 day

### Quick Start

```bash
# Set up environment
export DATABASE_URL="postgresql://user:pass@localhost:5432/cryptotrader"

# Backfill all timeframes for BTCUSD from a start date
python -m scripts.ingest_multi_timeframe --symbol BTCUSD --start 2024-01-01

# Resume ingestion (fetch from last candle to now) for all timeframes
python -m scripts.ingest_multi_timeframe --symbol BTCUSD --resume

# Ingest multiple symbols
python -m scripts.ingest_multi_timeframe \
  --symbol BTCUSD \
  --symbol ETHUSD \
  --symbol SOLUSD \
  --resume

# Ingest specific timeframes only
python -m scripts.ingest_multi_timeframe \
  --symbol BTCUSD \
  --timeframe 1h \
  --timeframe 4h \
  --timeframe 1d \
  --resume
```

### Command-Line Options

```
--symbol SYMBOL         Symbol to ingest (repeatable for multiple symbols)
--timeframe TIMEFRAME   Timeframe to ingest (repeatable, default: all standard timeframes)
--start DATE            ISO datetime/date for initial backfill (required unless --resume)
--end DATE              ISO datetime/date (default: now)
--resume                Resume from latest candle in DB
--exchange EXCHANGE     Exchange code (default: bitfinex)
--batch-size N          DB upsert batch size (default: 1000)
--max-retries N         Maximum retry attempts (default: 6)
--fail-fast             Stop on first error
```

### Examples

#### Initial Historical Backfill

Fetch historical data for the past year:

```bash
python -m scripts.ingest_multi_timeframe \
  --symbol BTCUSD \
  --start 2023-01-01 \
  --end 2024-01-01
```

#### Quick Start with Example Script

For convenience, use the example script that ingests common trading pairs:

```bash
# Resume mode (fetch latest candles for BTCUSD, ETHUSD, SOLUSD, XRPUSD)
python -m scripts.example_multi_timeframe_ingestion --mode resume

# Backfill mode (last 30 days)
python -m scripts.example_multi_timeframe_ingestion --mode backfill --days 30
```

#### Continuous Ingestion (Cron/Systemd)

Set up a cron job or systemd timer to run every 15 minutes:

```bash
*/15 * * * * cd /path/to/cryptotrader && python -m scripts.ingest_multi_timeframe --symbol BTCUSD --resume
```

Or create a systemd timer using the template in `systemd/cryptotrader-bitfinex-backfill@.timer`.

#### Multiple Symbols for Trading

Ingest data for your entire watchlist:

```bash
python -m scripts.ingest_multi_timeframe \
  --symbol BTCUSD \
  --symbol ETHUSD \
  --symbol SOLUSD \
  --symbol XRPUSD \
  --symbol ADAUSD \
  --resume
```

## Single Timeframe Ingestion

For more control or when you need to ingest a single timeframe, use the underlying backfill script directly:

```bash
python -m core.market_data.bitfinex_backfill \
  --symbol BTCUSD \
  --timeframe 1h \
  --start 2024-01-01 \
  --resume
```

## Gap Detection and Repair

After ingestion, you can detect and repair gaps in your data:

```bash
# Detect gaps
python -m core.market_data.bitfinex_gap_repair \
  --symbol BTCUSD \
  --timeframe 1h \
  --detect

# Repair gaps
python -m core.market_data.bitfinex_gap_repair \
  --symbol BTCUSD \
  --timeframe 1h \
  --repair
```

## Verification

Check ingestion status via the API or ingestion report script:

```bash
# Check status via API (requires API server running)
curl "http://localhost:8787/api/ingestion/status?symbol=BTCUSD&timeframe=1h"

# Generate ingestion report
python -m scripts.ingestion_report \
  --exchange bitfinex \
  --symbol BTCUSD \
  --timeframe 1h
```

## Environment Variables

Required:
- `DATABASE_URL` - PostgreSQL connection string

Optional:
- `TIMEFRAMES` - Comma-separated list of default timeframes (default: 1m,5m,15m,1h,4h,1d)

## Troubleshooting

### Rate Limiting

If you encounter rate limiting errors (HTTP 429), the scripts have built-in exponential backoff with retry logic. You can adjust:

```bash
python -m scripts.ingest_multi_timeframe \
  --symbol BTCUSD \
  --max-retries 10 \
  --initial-backoff-seconds 2.0 \
  --max-backoff-seconds 30.0 \
  --jitter-seconds 5.0 \
  --resume
```

### Database Connection Issues

Verify your `DATABASE_URL` is correct and the database is accessible:

```bash
python -m scripts.db_health_check
```

### Missing Data

Use the gap detection script to identify and repair missing candles:

```bash
python -m core.market_data.bitfinex_gap_repair \
  --symbol BTCUSD \
  --timeframe 1h \
  --detect \
  --repair
```

## Performance Tips

1. **Batch Size**: Larger batch sizes (e.g., 5000) can speed up initial backfills but use more memory
2. **Parallel Ingestion**: Run multiple instances with different symbols/timeframes in parallel
3. **Time Range**: For large historical backfills, consider breaking into smaller chunks (e.g., monthly)
4. **Database Indexes**: Ensure indexes exist on `(exchange, symbol, timeframe, open_time)` for optimal performance

## See Also

- Database schema: `db/schema.sql`
- Systemd service templates: `systemd/`
- API documentation: `api/README.md`
