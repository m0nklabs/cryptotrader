# LLM Assessment Feature - Testing Guide

This document explains how to test the new structured LLM assessment feature for CoinDossier.

## Database Migration

### Apply the migration

The migration adds assessment columns to the `coin_dossier_entries` table.

**Using the migration script:**
```bash
# Set your DATABASE_URL environment variable first
export DATABASE_URL="postgresql://user:pass@localhost:5432/cryptotrader"

# Apply all migrations
python -m scripts.apply_migrations

# Or apply just the assessment migration
python -m scripts.apply_migrations 003_dossier_assessment.sql
```

**Using psql directly:**
```bash
psql -U cryptotrader -d cryptotrader -f db/migrations/003_dossier_assessment.sql
```

**Using Docker Compose:**
```bash
# Copy migration to the container
docker cp db/migrations/003_dossier_assessment.sql cryptotrader-postgres:/tmp/

# Execute it
docker exec cryptotrader-postgres psql -U cryptotrader -d cryptotrader -f /tmp/003_dossier_assessment.sql
```

### Verify the migration

Check that the new columns exist:
```sql
\d coin_dossier_entries
```

You should see these new columns:
- `assessment_action` (TEXT)
- `assessment_confidence` (INTEGER)
- `assessment_risk` (TEXT)
- `assessment_entry_low` (DOUBLE PRECISION)
- `assessment_entry_high` (DOUBLE PRECISION)
- `assessment_stop_loss` (DOUBLE PRECISION)
- `assessment_take_profit_1` (DOUBLE PRECISION)
- `assessment_take_profit_2` (DOUBLE PRECISION)
- `assessment_reasoning` (TEXT)

## Testing the Feature

### 1. Generate a test dossier

Using the Python API:
```python
from core.dossier.service import DossierService
import asyncio

async def test_dossier():
    svc = DossierService()
    entry = await svc.generate_entry("bitfinex", "BTCUSD")
    
    print(f"Assessment Action: {entry.assessment_action}")
    print(f"Confidence: {entry.assessment_confidence}/10")
    print(f"Risk: {entry.assessment_risk}")
    print(f"Entry Zone: ${entry.assessment_entry_low} - ${entry.assessment_entry_high}")
    print(f"Stop Loss: ${entry.assessment_stop_loss}")
    print(f"Take Profit 1: ${entry.assessment_take_profit_1}")
    print(f"Take Profit 2: ${entry.assessment_take_profit_2}")
    print(f"Reasoning: {entry.assessment_reasoning}")

asyncio.run(test_dossier())
```

Using the REST API:
```bash
# Generate a new dossier
curl -X POST http://localhost:8000/dossier/BTCUSD/generate?exchange=bitfinex

# Fetch the latest dossier
curl http://localhost:8000/dossier/BTCUSD?exchange=bitfinex&days=1 | jq '.'
```

### 2. Verify the LLM response

Check that the LLM includes the `## ASSESSMENT` section in its response with valid JSON:

```json
{
  "action": "BUY",
  "confidence": 7,
  "risk_level": "medium",
  "entry_zone": [95000, 96500],
  "stop_loss": 93000,
  "take_profit": [98000, 100000],
  "timeframe": "24h",
  "reasoning_summary": "Strong upward momentum with RSI not yet overbought."
}
```

### 3. Test the frontend UI

1. Start the frontend dev server:
   ```bash
   cd frontend
   npm run dev
   ```

2. Navigate to the CoinDossier page

3. Verify the following elements appear:
   - **AssessmentBadge** in the sidebar (BUY/SELL/HOLD/AVOID badge next to direction badge)
   - **AssessmentPanel** in the detail view (prominent panel between Stats and Narrative sections)
   - Color coding:
     - BUY = green background
     - SELL = red background
     - HOLD = amber background
     - AVOID = gray background
   - Entry zone, stop loss, and target levels displayed correctly

### 4. Test backward compatibility

Old dossiers without assessment data should still render correctly:
- Assessment panel should not appear if `assessment_action` is empty
- Assessment badge should not appear in sidebar if no action
- All existing narrative sections should still display

## Expected LLM Prompt

The updated system prompt should include:

```
## ASSESSMENT
(Structured JSON block with your trading recommendation - must be valid JSON)
```json
{
  "action": "BUY",
  "confidence": 7,
  "risk_level": "medium",
  "entry_zone": [0.038, 0.042],
  "stop_loss": 0.035,
  "take_profit": [0.048, 0.055],
  "timeframe": "24h",
  "reasoning_summary": "Bullish MACD crossover with increasing volume suggests continuation."
}
```
```

## Troubleshooting

### LLM doesn't return valid JSON

- The Ollama model (llama3.2:3b) sometimes struggles with JSON
- The parser has robust fallback to handle malformed JSON
- Check logs for JSON parse errors
- Default values (empty/0) will be used if parsing fails

### Assessment panel not showing

- Check browser console for errors
- Verify the dossier entry has `assessment_action` populated
- Check that the API response includes assessment fields

### Database errors

- Ensure the migration was applied successfully
- Check column types match the migration
- Verify DATABASE_URL is correct

## Files Modified

- `core/dossier/service.py` - DossierEntry dataclass, prompt, parser, storage
- `db/migrations/003_dossier_assessment.sql` - Database migration
- `frontend/src/components/CoinDossier.tsx` - UI components
- `scripts/apply_migrations.py` - Migration utility
