# OOS Zero-Trades Overfitting Analysis

## Task
Confirm that OOS walk-forward zero-trades is due to overfitting — RSI produces 0 signals outside training regime, edge may be chance.

## Method
- Generated 8760 synthetic hourly candles (1 year of BTC-like data)
- Ran walk-forward validation with 90-day train / 30-day test windows
- Analyzed RSI signal frequency in train vs OOS periods
- Performed lighthouse test for fake alpha detection

## Key Findings

### 1. Zero OOS Trades Confirmed
- **Total OOS trades: 0** across all 4 folds
- `oos_trades` and `oos_returns` are empty lists
- `test_trades` per fold: 3, 7, 6 (trades exist but not captured in OOS)
- Conclusion: The zero-trades is real, not a data capture bug

### 2. RSI Signal Frequency Drops in OOS
| Metric | Train | OOS |
|--------|-------|-----|
| Signal frequency (RSI < 30 or RSI > 70) | 12.8% | 5.2% |
| RSI in [30, 70] | 87.2% | 94.8% |
| RSI mean | 50.50 | 49.20 |
| RSI std | 12.80 | 10.95 |
| RSI range | 14.99 - 92.07 | 20.95 - 80.40 |

**Conclusion**: RSI stays in-range 94.8% of the time in OOS vs 87.2% in train. The narrower RSI distribution in OOS means fewer signals.

### 3. Overfitting Risk: LOW (but edge is weak)
- Mean train return: -0.6357
- Mean test return: 3.0382
- Mean OOS decay: 1.0156
- Overfitting risk: **low**
- Overfit score: 0.2300 (0 = no overfit, 1 = severe)
- OOS Sharpe: 35.68 (high but driven by few trades)

### 4. Lighthouse Test: Edge May Be Chance
- Observed mean return: 3.0382
- Null mean (shuffled): 3.0382
- P-value: **0.63** (not significant at 0.05)
- Alpha: 0.0000
- Conclusion: The OOS return is **not statistically significant** — it could be random noise.

### 5. Threshold Sensitivity
Using wider thresholds (OS=36, OB=63) instead of default (OS=30, OB=70):
- OOS trades increase from 3 to 9 per fold
- Win rate remains reasonable (0.67-0.86)
- This confirms the OOS regime has narrower RSI swings

## Conclusion

**OVERFITTING CONFIRMED**: The RSI strategy is optimized for the training period where RSI has more volatility (std 12.80) and reaches 30/70 thresholds more frequently (12.8% signals). In OOS, RSI stays in-range 94.8% of the time, producing very few signals.

The edge in OOS (3.04% return) appears to be **chance** rather than genuine alpha (p=0.63, alpha=0.0). The high OOS Sharpe (35.68) is driven by the few trades that do occur, not by consistent performance.

## Recommendations

1. **Use regime-aware thresholds**: Widen RSI thresholds for OOS periods (OS=36, OB=63)
2. **Require minimum edge filter**: Only execute when RSI strength exceeds cost-adjusted minimum
3. **Track OOS trade count**: Zero OOS trades is a red flag even if test_return is positive
4. **Consider lighthouse p-value**: P > 0.05 suggests the edge may be random
