# Scheduled Jobs & Automated Backfill

This document describes the scheduled jobs for automated market data maintenance.

## Overview

Cryptotrader uses scheduled jobs to maintain data quality and completeness. These jobs run on a regular schedule to:
- Backfill missing historical data
- Repair detected gaps in candle data
- Maintain data freshness

## Implementation

Scheduled job implementation is managed in the **m0nklabs/market-data** repository.

See: https://github.com/m0nklabs/market-data/issues/12

## Job Types

### 1. Backfill Jobs

**Purpose**: Fill historical data for new symbols or timeframes

**Schedule**: Run manually or triggered by new symbol addition

**Process**:
1. Determine start date (earliest missing candle)
2. Fetch candles in batches from exchange API
3. Insert into database
4. Log progress in `market_data_job_runs` table

### 2. Gap Repair Jobs

**Purpose**: Repair detected gaps in existing candle data

**Schedule**: Daily at 02:00 UTC

**Process**:
1. Query `candle_gaps` table for unrepaired gaps
2. Fetch missing candles from exchange API
3. Insert candles and mark gap as repaired
4. Log repair status

### 3. Continuous Ingestion

**Purpose**: Keep data fresh with latest candles

**Schedule**: Every 5 minutes (configurable)

**Process**:
1. For each tracked symbol/timeframe, fetch latest candles
2. Insert new candles (skip duplicates via upsert)
3. Update last ingestion timestamp

## Monitoring

### Health Checks

The `/health` API endpoint provides basic service health (database connectivity, latency, and high-level candle counts).

Ingestion and job-level metrics are exposed via:
- `/system/health` - Aggregated health status including ingestion timers
- `/ingestion/status` - Detailed ingestion statistics
- `/system/status` - System status with database connectivity

These endpoints report:
- Number of ingestion runs in last 24 hours
- Last successful run timestamp
- Database connectivity and latency

### Gap Detection

Gaps are detected during ingestion and logged to `candle_gaps` table.

Query open gaps:
```sql
SELECT * FROM candle_gaps
WHERE repaired_at IS NULL
ORDER BY detected_at DESC;
```

## Configuration

### Environment Variables

```bash
# Timeframes to ingest
TIMEFRAMES=1m,5m,15m,1h,4h,1d

# Exchange API credentials
BITFINEX_API_KEY=<your_key>
BITFINEX_API_SECRET=<your_secret>

# Database connection
DATABASE_URL=postgresql://user:pass@host:port/database
```

### Systemd Timers

Example timer for gap repair:

```ini
[Unit]
Description=Market data gap repair timer

[Timer]
OnCalendar=02:00:00
Persistent=true

[Install]
WantedBy=timers.target
```

## Manual Operations

### Backfill a Symbol

```bash
python -m scripts.ingest_multi_timeframe \
  --symbol BTCUSD \
  --start 2024-01-01 \
  --resume
```

### Repair Gaps

```bash
python -m scripts.repair_gaps \
  --symbol BTCUSD \
  --timeframe 1h \
  --max-gaps 100
```

### Check Ingestion Status

```bash
curl http://localhost:8000/ingestion/status
```

## Database Schema

### market_data_jobs

Tracks scheduled job configuration:
- `id`: Job ID
- `symbol`: Trading symbol
- `exchange`: Exchange name
- `timeframe`: Timeframe
- `job_type`: backfill, gap_repair, continuous
- `schedule`: Cron expression
- `enabled`: Active status

### market_data_job_runs

Tracks job execution history:
- `id`: Run ID
- `job_id`: Foreign key to market_data_jobs
- `started_at`: Start timestamp
- `completed_at`: Completion timestamp
- `status`: success, failed, running
- `candles_inserted`: Number of candles inserted
- `error_message`: Error details if failed

### candle_gaps

Tracks detected gaps in candle data:
- `id`: Gap ID
- `symbol`: Trading symbol
- `exchange`: Exchange name
- `timeframe`: Timeframe
- `gap_start`: Start of gap
- `gap_end`: End of gap
- `detected_at`: When gap was detected
- `repaired_at`: When gap was repaired (NULL if open)

## Best Practices

1. **Rate Limits**: Respect exchange rate limits to avoid throttling
2. **Idempotency**: Jobs should be safe to re-run
3. **Logging**: Log all operations for debugging
4. **Monitoring**: Track success/failure metrics
5. **Alerting**: Alert on job failures or persistent gaps

## Troubleshooting

### Job Not Running

Check systemd timer status:
```bash
systemctl --user list-timers
systemctl --user status market-data-gap-repair.timer
```

### Persistent Gaps

1. Check exchange API availability
2. Verify API credentials
3. Check rate limit status
4. Manually attempt gap repair

### High Failure Rate

1. Review logs: `journalctl --user -u market-data-gap-repair`
2. Check database connectivity
3. Verify exchange API status
4. Check for rate limiting

## See Also

- [Market Data Service](MARKET_DATA_SERVICE.md) - Ingestion service architecture
- [Operations](OPERATIONS.md) - Production deployment guide
- [Docker Setup](DOCKER.md) - Containerized deployment
