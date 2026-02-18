# AI Budget Guardrails

## Overview

Budget guardrails prevent runaway LLM spending by enforcing configurable daily and monthly spend limits. The system supports both global budgets (across all AI operations) and per-role budgets (e.g., tactical, screener, fundamental, strategist).

## Features

- **Daily & Monthly Limits**: Configure separate limits for daily and monthly spending
- **Global + Per-Role Budgets**: Set budgets globally or override for specific roles
- **UTC Timezone Safety**: All date boundaries calculated in UTC for consistency
- **Flexible Limits**: `0.0` = unlimited; any positive value enforces a limit
- **Enable/Disable Toggle**: Turn enforcement on/off per scope without changing limits
- **Detailed Error Messages**: API returns spent/limit/remaining when budget exceeded
- **Safe Defaults**: New installations have unlimited budgets (no disruption)

## API Endpoints

### Get Budget Status (All Scopes)

```bash
GET /api/ai/budget/status
```

Returns current spending vs limits for all scopes (global + all roles).

**Response:**
```json
{
  "global": {
    "exceeded": false,
    "daily_exceeded": false,
    "monthly_exceeded": false,
    "daily_spent": 5.23,
    "daily_limit": 10.0,
    "daily_remaining": 4.77,
    "monthly_spent": 45.67,
    "monthly_limit": 100.0,
    "monthly_remaining": 54.33,
    "enabled": true
  },
  "tactical": { ... },
  "screener": { ... },
  "fundamental": { ... },
  "strategist": { ... }
}
```

### Get Budget Config for Scope

```bash
GET /api/ai/budget/config/{scope}
```

**Parameters:**
- `scope`: Budget scope - `global` or role name (`screener`, `tactical`, `fundamental`, `strategist`)

**Response:**
```json
{
  "id": "global",
  "daily_limit_usd": 10.0,
  "monthly_limit_usd": 100.0,
  "enabled": true,
  "updated_at": "2026-02-18T20:00:00Z"
}
```

### Update Budget Config

```bash
PUT /api/ai/budget/config/{scope}?daily_limit_usd=10.0&monthly_limit_usd=100.0&enabled=true
```

**Query Parameters:**
- `daily_limit_usd` (optional): Daily spend limit in USD (0.0 = unlimited)
- `monthly_limit_usd` (optional): Monthly spend limit in USD (0.0 = unlimited)
- `enabled` (optional): Enable/disable budget enforcement

**Response:** Same as GET endpoint

## Budget Enforcement

When evaluation endpoints are called (`POST /api/ai/evaluate`, `POST /api/ai/evaluate/single`), the system:

1. **Checks Global Budget**: If global budget exceeded, return HTTP 429
2. **Checks Per-Role Budgets**: If any active role's budget exceeded, return HTTP 429
3. **Proceeds if OK**: Evaluation runs normally if budgets are within limits

### Concurrency Considerations

**Important**: Budget enforcement is currently "best-effort" under concurrent requests. Multiple evaluation requests can pass budget checks before any of them logs usage, potentially allowing spend to exceed configured caps during high-traffic periods.

This is acceptable for most deployments where:
- Traffic is relatively low or bursty
- Budgets have reasonable margins (e.g., 10-20% buffer)
- Monitoring alerts trigger before hard limits

If strict caps are required under high concurrency:
- Consider adding a concurrency control mechanism (e.g., per-scope in-process lock)
- Implement DB-backed reservation/locking strategy
- Add rate limiting at the API layer

### Error Response (HTTP 429)

When a budget is exceeded:

```json
{
  "detail": {
    "error": "Budget exceeded",
    "budget_status": {
      "exceeded": true,
      "daily_exceeded": true,
      "monthly_exceeded": false,
      "daily_spent": 10.50,
      "daily_limit": 10.0,
      "daily_remaining": -0.50,
      ...
    },
    "message": "Daily budget limit of $10.00 exceeded (spent: $10.5000)"
  }
}
```

For role-specific overages:

```json
{
  "detail": {
    "error": "Budget exceeded",
    "role": "tactical",
    "budget_status": { ... },
    "message": "Daily budget limit for role 'tactical' of $5.00 exceeded (spent: $5.2300)"
  }
}
```

## Configuration Examples

### Set Global Daily Limit ($10/day)

```bash
curl -X PUT "http://localhost:8000/api/ai/budget/config/global?daily_limit_usd=10.0"
```

### Set Global Monthly Limit ($300/month)

```bash
curl -X PUT "http://localhost:8000/api/ai/budget/config/global?monthly_limit_usd=300.0"
```

### Set Per-Role Limit (Tactical: $5/day)

```bash
curl -X PUT "http://localhost:8000/api/ai/budget/config/tactical?daily_limit_usd=5.0"
```

### Disable Budget Enforcement (Testing)

```bash
curl -X PUT "http://localhost:8000/api/ai/budget/config/global?enabled=false"
```

### Re-enable with Same Limits

```bash
curl -X PUT "http://localhost:8000/api/ai/budget/config/global?enabled=true"
```

### Set Unlimited Budget

```bash
curl -X PUT "http://localhost:8000/api/ai/budget/config/global?daily_limit_usd=0.0&monthly_limit_usd=0.0"
```

## Database Schema

```sql
CREATE TABLE ai_budget_config (
    id                  TEXT        PRIMARY KEY,            -- 'global' or role name
    daily_limit_usd     REAL        NOT NULL DEFAULT 0.0,   -- 0.0 = unlimited
    monthly_limit_usd   REAL        NOT NULL DEFAULT 0.0,   -- 0.0 = unlimited
    enabled             BOOLEAN     NOT NULL DEFAULT true,  -- false = budgets disabled
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

**Default Rows:**
- `global`: Unlimited budgets by default
- `screener`, `tactical`, `fundamental`, `strategist`: Unlimited budgets by default

## Budget Calculation Logic

### Daily Budget

```python
# UTC start of day
start_of_day = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

# Sum all costs since start of day
daily_spent = SUM(cost_usd) WHERE created_at >= start_of_day

# Check if exceeded (only if limit > 0.0)
daily_exceeded = daily_limit > 0.0 AND daily_spent >= daily_limit
```

### Monthly Budget

```python
# UTC start of month
start_of_month = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)

# Sum all costs since start of month
monthly_spent = SUM(cost_usd) WHERE created_at >= start_of_month

# Check if exceeded (only if limit > 0.0)
monthly_exceeded = monthly_limit > 0.0 AND monthly_spent >= monthly_limit
```

### Remaining Budget

```python
if limit > 0.0:
    remaining = limit - spent
else:
    remaining = 0.0  # unlimited
```

## Testing

Run budget tests:

```bash
# Requires DATABASE_URL to be set
pytest tests/test_ai_budget.py -v
pytest tests/test_ai_budget_api.py -v
```

Tests cover:
- Budget config CRUD operations
- Budget check logic (just-under, equal, just-over boundaries)
- UTC timezone safety
- Multiple usage record aggregation
- Role-specific vs global budgets
- API endpoint enforcement (HTTP 429 on overage)

## Migration

Apply the budget config migration:

```bash
psql $DATABASE_URL < db/migrations/003_ai_budget_config.sql
```

Or through SQLAlchemy (see `tests/test_ai_budget.py` for example).

## Production Recommendations

1. **Start with monitoring**: Leave budgets unlimited initially, monitor actual spending
2. **Set conservative limits**: Use historical data to set realistic limits
3. **Alert on 80% usage**: Set up monitoring to alert when 80% of budget consumed
4. **Different limits per role**: Expensive roles (tactical) may need lower limits
5. **Monthly buffer**: Set monthly limit higher than 30× daily to allow spike days
6. **Test before enforcement**: Use `enabled=false` to test limits without blocking

## Security Notes

- Budget checks are performed **before** LLM API calls (prevents spend)
- All date calculations use **UTC** (no timezone drift)
- Budget status includes **no secrets** (safe to expose in errors)
- Enforcement is **fail-safe** (missing config = unlimited, but logged)

## See Also

- Parent issue: #205 (Multi-Brain AI)
- Related issue: #210 (Usage endpoints)
- CRUD functions: `db/crud/ai.py`
- API routes: `api/routes/ai.py`
- Database schema: `db/migrations/003_ai_budget_config.sql`
