# TODO (feature list + delegation work packages)

This document is the single source of truth for the v2 implementation backlog.

Constraints:

- Default to paper-trading / dry-run.
- Keep secrets out of git.
- DEX/swaps/bridges/tokenomics are out of scope.

## Feature list (complete)

1. Market data: OHLCV candles
   - Fetch candles (public CEX)
   - Backfill
   - Data quality: gap detection
   - Optional persistence

2. Technical indicators
   - Compute indicators on OHLCV
   - Produce per-indicator signals (side/strength/reason)

3. Opportunity scoring
   - Weighted aggregation to a 0-100 score
   - Output explainability ("why")

4. Indicator weights (configurable)
   - Code defaults
   - Optional DB-driven weights + indicator metadata
   - Auto-normalize weights
   - Historical signal logging

5. Fees & cost model
   - Maker/taker fees
   - Spread + slippage assumptions
   - Optional funding/financing costs
   - Optional transfer/withdrawal fees
   - Net edge and minimum threshold

6. Automation engine
   - Rules/policies
   - Safety checks (cooldowns, limits)
   - Execution monitoring (timeouts, retries)
   - Audit logging
   - Kill switch

7. Execution adapters
   - Paper executor (default)
   - Bitfinex execution adapter (later)

8. Multi-exchange
   - Additional CEX adapters (market data + execution)

9. Operations
  - Minimal runbook / system service wiring (in progress)
  - Frontend dashboard service (systemd --user) on port 5176
  - (later) add scheduled jobs for backfill/gap repair

10. Persistence (DB)
  - DB schema is part of the skeleton
  - Candle persistence + gap tracking
  - Opportunity / execution / audit logging
  - Portfolio snapshots (wallets/positions)
  - Orders and trade fills

## Work packages (suggested issues)

Use one GitHub issue per work package. Each issue should include:

- Scope
- Acceptance criteria
- File targets
- Explicit non-goals

### WP1 — Market data (candles)

- Targets:
  - `core/market_data/interfaces.py`
  - new: `core/market_data/providers/*`
  - new: `core/market_data/normalize.py`
- Acceptance:
  - Fetch OHLCV candles into canonical `core.types.Candle`
  - Handle timeframe + limit
  - No external persistence required for v1

### WP2 — Fees model

- Targets:
  - `core/fees/model.py`
- Acceptance:
  - CostEstimate includes trading fees + spread + slippage
  - Provide min edge threshold helper

### WP3 — Signal scoring

- Targets:
  - `core/signals/scoring.py`
- Acceptance:
  - Normalize weights
  - Score a list of indicator signals to 0-100

### WP4 — Paper execution

- Targets:
  - `core/execution/paper.py`
- Acceptance:
  - Always dry-run
  - Return structured `ExecutionResult`

### WP5 — Automation skeleton

- Targets:
  - new: `core/automation/*`
- Acceptance:
  - Rule model + safety checks + audit event structure
  - No live orders

### WP6 — Persistence skeleton (DB)

- Targets:
  - `db/schema.sql`, `db/init_db.py`
  - `core/persistence/interfaces.py`
  - (future) `core/storage/*`
- Acceptance:
  - Schema applies cleanly with `python -m db.init_db`
  - Protocols cover candles, opportunities, execution, audit, portfolio
  - No secrets, no live execution

## Tracking

- Canonical architecture: `docs/ARCHITECTURE.md`
- Development setup: `docs/DEVELOPMENT.md`
