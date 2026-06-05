# Indicator Correlation Analysis — Acceptance Criteria & Evidence

## Overview

This document describes the acceptance criteria, validation results, and evidence for the indicator correlation analysis module (`core/analysis/indicator_correlation.py`). The module detects when correlated indicators (RSI, MACD, Stochastic) produce duplicate signals, causing double exposure in the AI consensus trading pipeline.

## Acceptance Criteria

### AC-1: Correlation Matrix Computation

**Criterion:** The correlation matrix correctly computes pairwise Pearson correlations between RSI, MACD, and Stochastic indicators.

**Evidence:**
- Matrix is symmetric: `matrix[A][B] == matrix[B][A]`
- Diagonal is 1.0: `matrix[RSI][RSI] == 1.0`
- All values in [-1.0, 1.0]
- 3 pairs computed: RSI/MACD, RSI/Stochastic, MACD/Stochastic

**Validation:** `tests/test_indicator_correlation.py::TestCorrelationMatrix::test_matrix_has_all_pairs`, `test_matrix_symmetry`

---

### AC-2: Threshold Configuration

**Criterion:** The correlation threshold is configurable and defaults to 0.7. Pairs with absolute correlation >= threshold are flagged as "over-correlated."

**Evidence:**
- Default threshold: `DEFAULT_CORRELATION_THRESHOLD = 0.7`
- Low threshold (0.1): all pairs flagged as over-correlated
- High threshold (0.99): no pairs over-correlated
- Custom threshold propagates through all result fields

**Validation:** `tests/test_indicator_correlation.py::TestCorrelationMatrix::test_matrix_with_custom_threshold`

---

### AC-3: Double Exposure Detection

**Criterion:** Over-correlated pairs (correlation >= threshold) are correctly identified as potential double exposure sources.

**Evidence:**

| Pair | Correlation | Threshold | Status |
|------|------------|-----------|--------|
| RSI / Stochastic | 0.8056 | 0.7 | ABOVE [!!] |
| MACD / RSI | 0.6227 | 0.7 | BELOW |
| MACD / Stochastic | 0.6798 | 0.7 | BELOW |

RSI and Stochastic are the most correlated pair (~0.81), confirming that using both simultaneously creates double exposure risk. MACD is moderately correlated with both (~0.62-0.68).

**Validation:** `validate_correlation.py` — all 3 expected values within +/-0.05 tolerance.

---

### AC-4: Correlation Regime Sensitivity

**Criterion:** Correlation values change predictably across market regimes (high trend/low noise vs. low trend/high noise).

**Evidence:**
- High regime (trend=4.0, noise=0.3): at least 1 of 3 pairs above threshold
- Low regime (trend=0.3, noise=4.0): at least 1 of 3 pairs below threshold
- Neutral regime: mixed results with reasonable spread between max and min

**Validation:** `tests/test_indicator_correlation.py::TestHighLowCorrelationRegime` (3 tests)

---

### AC-5: Risk Level Assessment

**Criterion:** The module assigns risk levels based on the count of over-correlated pairs:
- **Low:** 0 over-correlated pairs
- **Medium:** 1 to N/2 pairs over-correlated
- **High:** More than N/2 pairs over-correlated

**Evidence:** Risk level is computed in `check_correlation_threshold()` and included in the formatted report.

**Validation:** `tests/test_indicator_correlation.py::TestCorrelationThresholdCheck::test_within_limits`, `test_high_risk`

---

### AC-6: Signal Series Extraction

**Criterion:** Signal series are correctly extracted from candle data using a rolling window approach with proper warmup periods.

**Evidence:**
- RSI: computed over lookback window, period=14
- MACD: histogram used as signal value (fast=12, slow=26, signal_period=9)
- Stochastic: %K value used (k_period=14, d_period=3)
- Minimum 10 data points required for valid correlation

**Validation:** `tests/test_indicator_correlation.py::TestEdgeCases::test_min_data_points`, `test_insufficient_data_raises`

---

### AC-7: Integration with AI Consensus Paper-Only Execution

**Criterion:** Correlation analysis provides evidence for the AI consensus engine's paper-only execution decisions by quantifying indicator redundancy.

**Evidence:**

The correlation analysis feeds into the AI consensus pipeline as follows:

1. **Signal Deduplication:** When RSI and Stochastic are both above 0.7 correlation, the consensus engine recognizes they may produce redundant BUY/SELL signals. This prevents double-counting of the same market signal.

2. **Strategist Correlation Penalty:** The `StrategistRole._calculate_correlation_penalty()` method uses correlation data to adjust position sizing when multiple correlated indicators signal the same direction.

3. **Consensus Confidence:** High correlation between indicators reduces the effective number of independent opinions in the consensus, which is factored into the final confidence score.

4. **Paper-Only Validation:** Before executing live trades, the paper trading system validates that the correlation matrix is stable (no extreme shifts) as a quality gate. This ensures that paper trades aren't driven by spurious indicator coincidences.

**Key integration points:**
- `core/analysis/indicator_correlation.py` — core computation
- `core/ai/roles/strategist.py` — correlation penalty for position sizing
- `core/analysis/correlation.py` — asset correlation (complementary, different scope)
- `validate_correlation.py` — standalone validation CLI

---

## Test Suite Summary

| Category | Tests | Status |
|----------|-------|--------|
| RSI/Stochastic correlation | 2 | PASS |
| RSI/MACD correlation | 2 | PASS |
| MACD/Stochastic correlation | 1 | PASS |
| Correlation matrix | 5 | PASS |
| Threshold checking | 5 | PASS |
| Edge cases | 5 | PASS |
| High/low regimes | 4 | PASS |
| Signal detection integration | 2 | PASS |
| **Total** | **26** | **26 PASS** |

Run: `pytest tests/test_indicator_correlation.py -v`

---

## Validation Script

The standalone validation script (`validate_correlation.py`) provides a quick check:

```bash
python validate_correlation.py
python validate_correlation.py --count 500 --threshold 0.65 --seed 123
```

Output includes:
- Pair correlations with ABOVE/BELOW threshold flags
- Full correlation matrix
- Max/min correlation pairs
- Over-correlated pair list
- Risk level assessment
- Validation against expected values

---

## Files

| File | Purpose |
|------|---------|
| `core/analysis/indicator_correlation.py` | Core correlation computation module |
| `core/analysis/correlation.py` | Asset correlation (complementary) |
| `tests/test_indicator_correlation.py` | 26-unit test suite |
| `validate_correlation.py` | Standalone validation CLI |
| `docs/INDICATOR_CORRELATION_ACCEPTANCE.md` | This document |
| `core/ai/roles/strategist.py` | Strategist role with correlation penalty |

---

## PR Reference

- **PR #336:** `feat: add indicator correlation analysis (RSI, MACD, Stochastic)`
- Branch: `hermes/issue-indicator-correlation`
- All 26 tests pass
- Validation confirms expected correlation values

---

## Future Work

1. Extend to support additional indicators (Bollinger, ATR, MA)
2. Add rolling correlation (time-decaying weights)
3. Integrate correlation data into the frontend dashboard
4. Add correlation-based position sizing in execution layer
5. Historical correlation analysis from Postgres candle data
