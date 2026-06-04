# Roadmap V2: Current State and Execution Plan

Last audited: 2026-05-28

This roadmap is intentionally blunt. It describes the repository as it exists now, not as an aspirational pitch deck. The project is a local-first crypto trading workbench with real market-data ingestion, paper trading, portfolio tracking, AI evaluation plumbing, and a sizeable frontend. It is not yet a proven autonomous profit engine.

North Star: generate durable positive PnL while keeping live-money risk controlled.

Operating rule: paper trading and dry-run remain the default until strategy validation, execution controls, and observability are proven end to end.

---

## Summary of Current State

### Working and Testable

| Area | Current state | Evidence |
| --- | --- | --- |
| Market data | Bitfinex/Binance backfill, gap repair, candle storage, realtime stream plumbing | `core/market_data/`, `core/storage/postgres/`, `api/candle_stream.py` |
| Technical analysis | RSI, MACD, Bollinger, Stochastic, ATR, scoring and reasoning modules | `core/indicators/`, `core/signals/` |
| Paper trading | Paper executor, order book simulation, position/PnL tracking, hardening tests | `core/execution/paper.py`, `core/execution/order_book.py` |
| Risk controls | Position sizing, exposure limits, drawdown controls, automation safety policies | `core/risk/`, `core/automation/` |
| Portfolio/trades | API routes and PostgreSQL CRUD for snapshots, trade history, balances, positions | `api/routes/portfolio.py`, `api/routes/trade_history.py`, `db/crud/` |
| Backtesting | API and engine exist for RSI/SMA strategies with core metrics | `core/backtest/`, `api/routes/backtest.py`, `strategies/` |
| AI/Multi-Brain | Provider adapters, roles, router, consensus, API, budget checks, frontend panels exist | `core/ai/`, `api/routes/ai.py`, `frontend/src/api/ai.ts` |
| Frontend | Rich dashboard with charts, orders, portfolio, alerts, AI, backtest, watchlist panels | `frontend/src/` |
| Operations | Native API/frontend systemd units plus Docker PostgreSQL are in use | `systemd/`, `docker-compose.yml`, `docs/OPERATIONS.md` |

### Not Yet Proven

| Area | Reality |
| --- | --- |
| Profitability | No documented strategy has passed robust walk-forward or out-of-sample validation. |
| Live trading | Bitfinex live adapter exists but should remain gated; dry-run/paper mode is the real supported mode. |
| AI-to-execution | AI decisions are observable and persisted, but not a safe automated execution pipeline. |
| Multi-exchange trading | Bitfinex is the only real exchange path. Binance/KuCoin remain adapter/backfill scope, not production trading support. |
| Production hardening | Frontend and API are suitable for local operations, not an unattended public SaaS or money-moving production system. |

---

## Inconsistencies Found

1. Older roadmap text marked AI, backtesting, portfolio, and frontend as `Planned` or `Skeleton` even though substantial code now exists.
2. Older issue references point to many closed issues: #205, #206-#211, #181, #184, #177, #182, #231, #229 and related follow-ups are no longer open tracker items.
3. `FEATURES.md` still advertises old open issue numbers and old Ollama wording in places, while runtime work now routes local LLM calls through Guardian.
4. The audit found and fixed the shell-injection pattern reported by #284 in `custom-agent.yml`; comment bodies now flow through `COMMENT_BODY` instead of direct shell interpolation.
5. Docs mix three deployment modes without clearly naming the live one: Docker Postgres, native systemd API, and optional Compose API/frontend.
6. Frontend docs understate the current UI as a skeleton, but the UI still lacks production-grade error boundaries, offline states, and complete wallet/balance integration.
7. The AI docs overstate maturity when they imply automated trading decisions are ready for execution; AI is currently an analysis/decision layer, not a trusted execution authority.

---

## Missing Features and Gaps

### P0 - Must Fix Before Trusting Automation

1. **Keep the CI comment-body command injection fix covered (#284).**
   - The shipped fix replaces shell interpolation with `COMMENT_BODY` env input that treats the comment body as data.
   - Add a regression check or workflow lint rule if this workflow grows new parsing logic.

2. **Prove strategy validity before live automation.**
   - Add walk-forward and out-of-sample validation.
   - Add lookahead-bias tests for indicators, signals, and backtest data loading.
   - Persist backtest run metadata and compare runs over time.

3. **Keep live trading gated.**
   - Preserve `dry_run=True` defaults.
   - Require explicit operator confirmation and audit logging before any live Bitfinex order path can be enabled.

### P1 - High-Value Development

4. **Wire AI decisions into paper-trading only.**
   - AI consensus may create paper-order intents after risk checks.
   - Every decision must include role verdicts, veto state, budget state, and execution outcome.

5. **Harden Postgres integration tests.**
   - Add migration smoke tests against a real disposable PostgreSQL service.
   - Cover candle upserts, trades, portfolio snapshots, AI usage logs, and alert persistence.

6. **Make backtesting cost-aware.**
   - Integrate `FeeModel`, spread, slippage, and realistic fill assumptions into the backtest engine.
   - Report net edge after costs, not only raw PnL.

7. **Replace stale LLM/Ollama terminology with Guardian terminology.**
   - Keep legacy aliases in code where needed, but public docs and API descriptions should call the local provider Guardian.

### P2 - Observability and Operator UX

8. **Trace and control the local `/research/llm/status` poller.**
   - The route is now authenticated and single-request, but a local client polls it roughly every 10 minutes.
   - Identify the caller and decide whether it should use cache, backoff, or a cheaper health endpoint.

9. **Frontend resilience pass.**
   - Add error boundaries, explicit empty/error states, and backend-unavailable states for data-heavy panels.
   - Remove or label fallback/sample data in operator-facing performance views.

10. **Wallets and balances.**
   - `wallets-data` remains reserved/not deployed in the current cryptotrader stack.
   - Exchange balance UI must not imply live balance coverage until that service exists.

### P3 - Cleanup and Coherence

11. **Retire or quarantine dead abstractions.**
   - `core/storage/noop_stores.py` and protocol-only persistence layers should be documented as delegation scaffolding or removed from runtime paths.

12. **Normalize deployment docs.**
   - Current live mode is: Docker PostgreSQL + native systemd API/frontend.
   - Compose remains a development option, not the live service model.

---

## Updated Realistic Roadmap

| Epic | Priority | Status | Concrete next deliverable |
| --- | --- | --- | --- |
| Security and CI safety | P0 | #284 fixed in 7ee5646 | Add workflow lint coverage if parsing expands. |
| Backtesting and validation | P0 | Engine exists, validation incomplete | Walk-forward/out-of-sample validation plus lookahead-bias coverage. |
| Execution and automation | P0/P1 | Paper trading solid, live gated | AI-to-paper execution with risk gates; no live default. |
| AI/Multi-Brain | P1 | Implemented analysis layer, not execution authority | Paper-only decision integration, budget/usage observability, provider health hardening. |
| Database reliability | P1 | Schema and CRUD exist, integration coverage weak | Disposable Postgres migration/integration test suite. |
| Frontend observability | P2 | Broad dashboard exists, production UX incomplete | Error states, status caching, alert/chart integration, no misleading fallback data. |
| Portfolio and wallets | P2 | Portfolio/trades exist, wallet service absent | Keep wallet UI disabled/explicit until `wallets-data` is deployed. |
| Infrastructure | P3 | Mixed but workable live stack | Document Docker DB + native API/frontend as the current supported ops mode. |

---

## Updated and Corrected Issue List

Current open issues after audit:

| Issue | Status after audit | Action |
| --- | --- | --- |
| #284 Security issue in workflow YAML | Fixed in 7ee5646 | Closed after push. |
| #212 Project Roadmap Priority Matrix | Stale body, useful parent issue | Update body to this current-state roadmap and link new focused issues. |
| #170 Frontend Observability | Still relevant but too broad | Keep as epic; split into focused issues for error states, chart alerts/projections, and poller/cache behavior. |
| #179 Infrastructure & Operations | Still relevant but stale | Keep as epic; update to current mixed deployment and remaining ops work. |

New focused issues created from this audit:

1. #303: Add walk-forward and lookahead-bias validation to backtesting.
2. #304: Wire AI consensus into paper-only execution with audited risk gates.
3. #305: Add disposable PostgreSQL migration and store integration tests.
4. #306: Harden frontend error, empty, and offline states.
5. #307: Identify and rationalize the `/research/llm/status` poller.
6. #308: Review and tighten PostgreSQL port exposure for the live local stack.

---

## Recommended Next Development Steps

1. Land the walk-forward validation work before adding new strategy logic.
2. Make AI decisions produce paper-order intents only, behind explicit risk and budget gates.
3. Add a real Postgres integration test path in CI or an explicitly documented local command.
4. Update frontend status/error handling so operator screens are trustworthy under partial backend failure.
5. Keep workflow issue-comment parsing covered if the custom agent grows new flags.

---

## Risks and Technical Debt

- The project has many real modules, but the profitable strategy validation layer is still the weak link.
- Live execution code must remain treated as dangerous until validation, operator approval, and audit trails are boringly reliable.
- The issue tracker drifted from code reality; old closed issue references made the backlog look larger and less mature than it is.
- Docs still contain legacy Ollama wording and older deployment assumptions.
- Mixed deployment is acceptable today, but it must stay explicit: Postgres in Docker, API/frontend native systemd.
- Integration tests depend too much on optional local services and too little on disposable test infrastructure.

---

## Validation Commands

Use targeted commands for each roadmap slice:

```bash
# Backend core and API
pytest tests/test_api_*.py tests/test_backtest*.py tests/test_paper*.py

# AI/Multi-Brain
pytest tests/ai/ tests/test_ai_*.py tests/test_guardian_status_probe.py

# Frontend
cd frontend && npm run build && npm test

# Full local quality gate
ruff check . && pytest
```
