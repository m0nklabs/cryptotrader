# Backtesting

How `core/backtest/engine.py` values a strategy run, and what its numbers mean.
Written for issue [#431](https://github.com/m0nklabs/cryptotrader/issues/431)
(open positions and intra-trade PnL were missing from the equity curve).

## Equity is marked to market

The engine keeps realized cash and the open position apart and revalues the
position on **every** candle:

```
equity(t) = cash + unrealized_pnl(open_position, close(t))
```

- `cash` starts at `initial_capital` and moves only when a trade closes.
- A long position is worth `(mark - entry) * size`, a short one
  `(entry - mark) * size`. `size` is the position quantity from
  `core/risk/sizing.py` (fixed `1.0` when no `position_size_config` is set).
- `equity_curve[0]` is `initial_capital`, then one entry per candle, so a run
  over `n` candles returns `n + 1` points.

Consequences that the operator can rely on:

- `total_pnl == realized_pnl + unrealized_pnl` for every run.
- `max_drawdown` and the Sharpe returns are computed from the marked curve, so
  an adverse intra-trade excursion is visible even when the trade never closes.
- An open position at the end of the data is **not** silently dropped from the
  result: it is either marked or liquidated, per the policy below.

Fills are priced gross. The engine has no fee/slippage model of its own;
cost-aware replay is applied one layer up, by wrapping the strategy with
`_CostAwareStrategy` and a `FeeModel` in `core/strategy_eval/walk_forward.py`.

## End-of-run policy

`BacktestEngine(..., end_of_run_policy=...)` decides what happens to a
position that is still open on the last candle:

| Policy | Meaning |
|---|---|
| `mark_to_market` (default) | The position stays open. The final equity is its marked value, and `open_position` / `unrealized_pnl` describe it. |
| `force_close` | The position is liquidated at the last close. The liquidation is appended to `trades` (so it counts in win rate and profit factor), `unrealized_pnl` becomes `0`, and `open_position` becomes `None`. |

Both policies report `end_of_run_policy` on the result. An unknown policy is
rejected with `ValueError` when the engine is constructed.

`BacktestResult.open_position` is a small dict
(`side`, `size`, `entry_price`, `mark_price`, `unrealized_pnl`) or `None` for a
flat book.

## Walk-forward interaction

`run_walk_forward()` subtracts the warmup phase's result from the full
training run to attribute only the in-window PnL. With marked equity that
subtraction now includes the mark move of a position carried across the
boundary — the warmup loss itself still stays out of the training window, but
a carried position is no longer invisible.

`WalkForwardFold.oos_decay` is `test_return / train_return`, a sign-carrying
ratio: it is negative when a fold loses in-sample and gains out-of-sample, and
it has no upper bound. Do not treat it as a percentage.

## Tests

- `tests/test_backtest_open_position.py` — long/short favorable and adverse
  excursions, both end-of-run policies, and the
  `realized + unrealized == total_pnl` invariant.
- `tests/test_backtest_integration.py` — engine behaviour on synthetic data.
- `tests/test_backtest_validation.py`, `tests/test_walk_forward_lookahead.py`
  — walk-forward metrics built on the engine.