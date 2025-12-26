# Market Cap Rankings

## Overview

The cryptotrader dashboard now displays symbols sorted by their live market capitalization rankings from CoinGecko. This replaces the previous hardcoded rankings.

## Architecture

### Backend

**CoinGecko Client** (`core/market_cap/coingecko.py`):
- Fetches top coins by market cap from CoinGecko's free API
- No API key required
- Rate limit aware (10-30 calls/minute on free tier)

**API Endpoint** (`/api/market-cap`):
- Returns current market cap rankings as JSON
- Implements in-memory caching with 10-minute TTL
- Gracefully falls back to static rankings on API failure
- Response format:
  ```json
  {
    "rankings": {"BTC": 1, "ETH": 2, "SOL": 4, ...},
    "cached": true,
    "source": "coingecko",
    "last_updated": 1234567890
  }
  ```

**Database Table** (`market_cap_ranks`):
- Schema defined in `db/schema.sql`
- Currently unused (using in-memory cache only)
- Available for future persistent storage if needed

### Frontend

**Market Cap API Client** (`frontend/src/api/marketCap.ts`):
- Simple fetch wrapper for `/api/market-cap` endpoint

**App.tsx Updates**:
- Fetches market cap rankings on load
- Refreshes every 10 minutes
- Falls back to static rankings on error
- Sorts Market Watch symbols by live rankings

## Rate Limiting

CoinGecko free tier limits:
- 10-30 calls per minute
- No API key required

To respect these limits:
- Backend caches for 10 minutes (configurable via `MARKET_CAP_CACHE_TTL`)
- Frontend polls every 10 minutes (configurable via `MARKET_CAP_REFRESH_INTERVAL_MS`)

## Fallback Behavior

If CoinGecko API is unavailable:
1. Backend returns last cached data if available
2. If no cache, returns static fallback rankings
3. Frontend continues with existing rankings on fetch error

Static fallback rankings (defined in `api/main.py`):
```python
FALLBACK_MARKET_CAP_RANK = {
    "BTC": 1, "ETH": 2, "XRP": 3, "SOL": 4, "ADA": 5,
    "DOGE": 6, "LTC": 7, "AVAX": 8, "LINK": 9, "DOT": 10,
}
```

## Testing

**Unit Tests**:
- `tests/test_coingecko_client.py` - CoinGecko client tests
- `tests/test_api_market_cap.py` - API endpoint tests

**Manual Testing**:
```bash
# Test the endpoint directly
python scripts/test_market_cap_endpoint.py

# Run all tests
pytest tests/test_coingecko_client.py tests/test_api_market_cap.py -v
```

## Future Enhancements

1. **Database Persistence**: Store rankings in `market_cap_ranks` table for historical tracking
2. **Background Refresh**: Use scheduled job (systemd timer, cron, or FastAPI background task) instead of on-demand refresh
3. **Multiple Sources**: Add CoinMarketCap or other providers as alternative sources
4. **Extended Data**: Store additional metadata (market cap value, 24h change, etc.)
5. **Admin UI**: Allow manual rank overrides for specific symbols
