# AI evaluations — context, provenance and abstention

The Multi-Brain AI lane (`/api/ai/evaluate`) aggregates per-role verdicts into
one consensus decision. This page documents what that decision is allowed to
claim, because a `BUY`/`SELL` badge is only meaningful when it was produced
from current, timestamped evidence (issue #432).

## The rule

**No current evidence, no executable recommendation.** The server builds the
evaluation context itself; the client no longer supplies it.

Two failure tiers, because "no market data" and "no risk limits" are different
problems:

| Tier | Condition | Behaviour |
|---|---|---|
| Blocking | The candle series is absent, stale, or has no timestamp | No role is queried, no provider cost is incurred, the answer is `NEUTRAL` with confidence `0.0`, `abstained: true` and the reasons |
| Degraded | Candles are usable but the portfolio snapshot and/or the risk limits are absent or stale | Roles are queried for information, but the consensus is clamped to `NEUTRAL`, confidence `0.0`, `abstained: true` |

Either way an executable action (`BUY`, `SELL`, `VETO`) requires all three
inputs to be current.

## Request

`POST /api/ai/evaluate`

| Field | Type | Default | Meaning |
|---|---|---|---|
| `symbol` | string | required | Display symbol (`BTC/USD`); normalized to the store key (`BTCUSD`) |
| `timeframe` | string | `1h` | Candle timeframe |
| `exchange` | string | `bitfinex` | Exchange the market data is read from |
| `roles` | string[] | all active | Roles to query |
| `riskLimits` | object | — | Risk limits. Configuration, so no timestamp is required; **there is no authoritative server-side source for these yet**, so a request without them cannot be executable |
| `buildContext` | bool | `true` | Assemble the context server-side. `false` restores the pre-#432 pass-through contract and reports `context: null` |
| `maxContextAgeS` | number | `3600` | Freshness budget applied to every input; server-capped at `604800` (7 days), so a caller cannot widen the window until old data counts as fresh |

With `buildContext: true` (the default) the supplied `candles`, `indicators`
and `portfolio` fields are ignored: the authoritative sources win. That is
enforced, not merely documented — client indicators are dropped before the
roles are called, because there is no authoritative indicator source to
replace them with and an unrecorded, client-supplied input would undermine
the provenance the snapshot promises.

## Where the context comes from

| Input | Source | Timestamp |
|---|---|---|
| `candles` | `candles` table, last 200 rows for `(exchange, symbol, timeframe)`, oldest first | `close_time` of the last candle |
| `portfolio` | newest `portfolio_snapshots` row for the exchange | `snapshot_time` |
| `risk_limits` | the request body (configuration) | none, by design |

A read failure in either table is treated as missing evidence, never as an
excuse to guess: it is logged and the evaluation abstains.

## Response additions

| Field | Meaning |
|---|---|
| `context` | The snapshot the decision was built from, or `null` when assembly was disabled |
| `abstained` | `true` when the consensus is not executable |
| `abstainReasons` | Why it is not executable, one line per unusable input |
| `roleFailures` | Roles that errored, with provider and model |

The snapshot itself carries the provenance:

```json
{
  "version": 2,
  "builtAt": "2026-11-24T11:00:00+00:00",
  "maxAgeSeconds": 3600,
  "marketSymbol": "BTCUSD",
  "exchange": "bitfinex",
  "dataAgeSeconds": 42.5,
  "canRun": true,
  "executableReady": false,
  "missing": ["risk_limits"],
  "stale": [],
  "inputs": [
    {
      "name": "candles",
      "provided": true,
      "required": true,
      "usable": true,
      "asOf": "2026-11-24T10:59:00+00:00",
      "ageSeconds": 60.0,
      "missingReason": null
    }
  ]
}
```

The snapshot keys are camelCase, like the rest of the `/api/ai` contract: it
is served as plain JSON, so FastAPI's alias serialization does not reach
inside it and the keys are fixed where the payload is built
(`core/ai/context.py`). `dataAgeSeconds` is the age of the **oldest usable**
input, so one stale input cannot hide behind a fresh one.

## Dashboard

`AiEvaluationPanel` renders three things beyond the verdicts:

- an **ABSTAINED — not executable** notice with the server's reasons whenever
  `abstained` is true;
- a **context provenance strip** (snapshot version, exchange/market symbol,
  oldest input age, per-input usability with age) under the consensus card;
- a **role failures** list, so a role that timed out is visible instead of
  silently missing from the verdict count.

## Tests

`tests/test_ai_evaluation_context.py` pins the guarantees:

- the pure classifier in `core/ai/context.py` (fresh / missing / stale /
  undated / future-dated inputs, configuration without a timestamp);
- empty or stale market data → `NEUTRAL`, `abstained`, and **no provider call**;
- missing risk limits → roles run, consensus clamped to `NEUTRAL`;
- complete context → the provider's `BUY` survives;
- the server snapshot, not the request body, feeds the pipeline;
- `buildContext: false` keeps the legacy contract;
- failed roles are reported in `roleFailures`.

## Known gaps

Indicators have no authoritative server-side source yet either, and the
`core/indicators/` calculators are not wired into the context assembly. With
`buildContext: true` no indicators reach the roles at all; deriving them from
the authoritative candle series is the follow-up that lets them count as
evidence.

Risk limits have no authoritative server-side source yet (`RiskLimits` in
`core/risk/limits.py` is never instantiated outside a request body). Until
that exists, a request that omits `riskLimits` can never be executable — by
design, rather than by inventing a source.
