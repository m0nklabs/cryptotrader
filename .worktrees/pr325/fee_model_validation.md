# Fee Model Validation - Acceptance Criteria & Evidence

## Summary
FeeModel is fully implemented and wired into paper trading. All acceptance criteria met.

## Acceptance Criteria

### 1. FeeModel computes taker/maker fees correctly
- Taker fee: 0.2% (0.002) - Bitfinex standard
- Maker fee: 0.1% (0.001) - Bitfinex standard
- Evidence: `test_estimate_cost_computes_fees_and_edge_threshold` - $1000 taker = $2.00 fees
- Evidence: `test_estimate_cost_maker` - $1000 maker = $1.00 fees

### 2. Spread and slippage costs computed correctly
- Spread: 10 bps (0.1%) assumed
- Slippage: 5 bps (0.05%) assumed
- Evidence: $1000 taker: spread=$1.00, slippage=$0.50

### 3. Minimum edge filter works
- Taker minimum edge: 35 bps (20 fee + 10 spread + 5 slippage)
- Maker minimum edge: 25 bps (10 fee + 10 spread + 5 slippage)
- Percentage-based (scales with notional)
- Evidence: `test_minimum_edge_bps` - 35.00 bps for taker at $1000
- Evidence: `test_evaluate_opportunity_maker_fees_lower_threshold` - 25.00 bps for maker

### 4. FeeModel wired into PaperExecutor
- PaperExecutor accepts FeeModel in constructor
- Falls back to default FeeModel if not provided
- Fees applied to market orders via `estimate_cost()`
- Fee tracking per symbol and total
- Evidence: `test_fee_model_wired`, `test_custom_fee_model`
- Evidence: `test_fees_applied_to_market_orders`, `test_fees_by_symbol`

### 5. FeeModel wired into Policy (signal path)
- Policy.decide() uses fee_model for edge threshold checks
- Converts opportunity score (0-100) to edge_rate (score/10000)
- Calls evaluate_opportunity() with fee_model
- Falls back to notional-only check if fee_model is None
- Evidence: `test_policy_allows_with_fee_model`, `test_policy_denies_low_edge`

### 6. Opportunity evaluator uses FeeModel
- Pure function evaluate_opportunity() with no side effects
- Compares observed edge vs required minimum edge
- Returns EvaluationResult with decision, required/observed bps, reasons
- Supports pre-computed CostEstimate
- Evidence: Full test suite in `test_opportunity_evaluator.py` (12 tests)

### 7. Paper summary includes fee model state
- `get_paper_summary()` returns fee_model breakdown
- Maker/taker rates, spread bps, slippage bps
- Evidence: `test_paper_summary`

### 8. Edge cases handled
- Zero/negative notional raises ValueError
- Zero edge fails (below threshold)
- Very high edge passes (200+ bps)
- Boundary case: edge == threshold passes (>=)
- Result is immutable (frozen dataclass)
- Evidence: `test_evaluate_opportunity_zero_edge_fails`, `test_evaluate_opportunity_boundary_equal_threshold`, `test_evaluate_opportunity_very_high_edge_passes`, `test_evaluate_opportunity_result_immutable`

## Test Results
- 126 tests pass (0 failures)
- test_fees_model.py: 2 tests
- test_paper_trading_hardening.py: 35 tests
- test_opportunity_evaluator.py: 12 tests
- test_automation.py: 77 tests (includes policy, trade history, safety checks)

## Known Gaps (non-blocking)
- Kelly default is full (1.0) - aggressive sizing (noted in ARCHITECTURE_MAP)
- FeeModel not wired to ALL signal paths (only policy path currently uses it)
- No live drawdown monitoring as trading signal (tracked but not actively used)

## Files
- Core: core/fees/model.py
- Types: core/types.py (FeeBreakdown, CostEstimate)
- Evaluator: core/opportunities/evaluator.py
- Policy: core/automation/policy.py
- Paper: core/execution/paper.py
- Tests: tests/test_fees_model.py, tests/test_paper_trading_hardening.py, tests/test_opportunity_evaluator.py
