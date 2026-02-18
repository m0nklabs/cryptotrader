# LLM Assessment UI Components

## Overview
This document shows the visual structure of the new LLM Assessment components.

## Component 1: AssessmentBadge (Sidebar)

Appears in the coin sidebar list next to the direction badge.

```
┌─────────────────────────────────────────┐
│ BTCUSD  ↗ UP   🟢 BUY   ✅ Correct      │
│ $96,543  +2.45%  RSI 65                 │
└─────────────────────────────────────────┘
```

Color coding:
- 🟢 BUY = Green background (#16a34a)
- 🔴 SELL = Red background (#dc2626)
- 🟡 HOLD = Amber background (#d97706)
- ⚫ AVOID = Gray background (#6b7280)

## Component 2: AssessmentPanel (Detail View)

Full assessment panel in the dossier detail view, positioned between "Stats Summary" and "Technical Analysis" sections.

```
┌─────────────────────────────────────────────────┐
│ 🤖 LLM ASSESSMENT                               │
│                                                 │
│  ████ BUY ████      Confidence: 7/10            │
│                     Risk: Medium                │
│                                                 │
│  Entry Zone: $95,000 – $96,500                  │
│  Stop Loss:  $93,000                            │
│  Target 1:   $98,000                            │
│  Target 2:   $100,000                           │
│                                                 │
│  "Strong upward momentum with RSI not yet       │
│   overbought. MACD showing bullish crossover    │
│   with increasing volume."                      │
└─────────────────────────────────────────────────┘
```

Visual characteristics:
- Background tinted based on action (green/red/amber/gray with 10% opacity)
- Border colored to match action
- Confidence displayed as X/10
- Risk level color-coded:
  - Low = green
  - Medium = yellow
  - High = orange
  - Extreme = red
- Entry/Exit levels in grid layout
- Stop loss in red
- Target prices in green
- Reasoning in italics with quotes

## Full Page Layout

```
┌─ Sidebar ──────┐ ┌─ Detail View ────────────────────────┐
│                │ │ BTCUSD  ↗ UP  🟢 BUY  ✅ Correct     │
│ BTCUSD         │ │                                      │
│ ↗ UP  🟢 BUY   │ │ ┌──────── Stats Bar ────────┐       │
│ ✅ Correct     │ │ │ Price  24h  RSI  MACD      │       │
│                │ │ └────────────────────────────┘       │
│ ETHUSD         │ │                                      │
│ ↘ DOWN 🔴 SELL │ │ ┌──── 🤖 LLM Assessment ────┐       │
│ ❌ Wrong       │ │ │                             │       │
│                │ │ │ BUY  Confidence: 7/10      │       │
│ SOLUSD         │ │ │      Risk: Medium           │       │
│ → SIDEWAYS     │ │ │                             │       │
│ 🟡 HOLD        │ │ │ Entry: $95K-$96.5K         │       │
│ pending        │ │ │ Stop:  $93K                │       │
│                │ │ │ Targets: $98K, $100K       │       │
└────────────────┘ │ │                             │       │
                   │ │ "Strong momentum..."        │       │
                   │ └─────────────────────────────┘       │
                   │                                      │
                   │ ┌─ Stats Summary ───────────┐        │
                   │ │ Current price $96,543...   │        │
                   │ └────────────────────────────┘        │
                   │                                      │
                   │ ┌─ Technical Analysis ──────┐        │
                   │ │ RSI at 65 indicates...     │        │
                   │ └────────────────────────────┘        │
                   │                                      │
                   └──────────────────────────────────────┘
```

## Data Flow

1. **LLM Generation**: Ollama generates response with `## ASSESSMENT` section containing JSON
2. **Parsing**: `_parse_llm_response()` extracts JSON with regex and parses it
3. **Storage**: `_store_entry()` saves assessment fields to database
4. **Retrieval**: `_row_to_entry()` loads assessment fields from DB
5. **API**: FastAPI `/dossier/` endpoints return full DossierEntry with assessment
6. **Frontend**: React components render AssessmentBadge and AssessmentPanel

## Database Schema

New columns in `coin_dossier_entries`:
```sql
assessment_action TEXT NOT NULL DEFAULT '',
assessment_confidence INTEGER NOT NULL DEFAULT 0,
assessment_risk TEXT NOT NULL DEFAULT '',
assessment_entry_low DOUBLE PRECISION NOT NULL DEFAULT 0,
assessment_entry_high DOUBLE PRECISION NOT NULL DEFAULT 0,
assessment_stop_loss DOUBLE PRECISION NOT NULL DEFAULT 0,
assessment_take_profit_1 DOUBLE PRECISION NOT NULL DEFAULT 0,
assessment_take_profit_2 DOUBLE PRECISION NOT NULL DEFAULT 0,
assessment_reasoning TEXT NOT NULL DEFAULT ''
```

## Example JSON from LLM

```json
{
  "action": "BUY",
  "confidence": 7,
  "risk_level": "medium",
  "entry_zone": [95000, 96500],
  "stop_loss": 93000,
  "take_profit": [98000, 100000],
  "timeframe": "24h",
  "reasoning_summary": "Strong upward momentum with RSI not yet overbought. MACD showing bullish crossover with increasing volume."
}
```
