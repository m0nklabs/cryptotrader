# Changelog

## 2026-06-01
### Paper Execution PR Repair
- Repair PR #325 paper execution review blockers: rebuild consensus decisions from public enum constructors, preserve execution timeframes in risk decisions, and reject non-trade consensus actions before paper execution.
- Apply Kelly-based position sizing through the backtest API and walk-forward validation path while preserving fixed-size defaults for direct engine callers.
- Harden disposable PostgreSQL integration testing by using authenticated psql URLs, a project-local Python runner, per-test table cleanup, and portable Postgres array binds for latest candle-close queries.
- Restore project pytest/Ruff configuration and fix backtest validation tests so lookahead-bias checks fail on future candle access instead of relying on stale imports or duplicate decorators.
- Close the remaining PR #325 review items by preserving legacy unit sizing for unsized backtests, comparing gate enums directly in paper-execution tests, and aligning disposable Postgres fixtures/scripts to skip cleanly without Docker and reuse one container name.

## 2026-05-31
### Walk-Forward Validation Fix
- Fix a post-merge regression in `core/strategy_eval/walk_forward.py` where warmup equity used `Decimal + float`, causing `TypeError` and breaking strict OOS walk-forward tests.
- Keep warmup-equity denominator computation in float space and remove stale unused locals from the fold setup path.

## 2026-05-28
### Paper Trading Hardening
- Store orchestrator position exposure as quote-currency market value after fills so position-size checks compare against the configured quote-denominated limits.
- Add causal timestamps to paper limit orders and market price updates so orders created after a price update cannot be filled by that earlier price.
- Keep pending limit orders without a fill price until `update_market_price()` fills them, and add lookahead-bias regression tests for order-book and paper-executor fills.

### Devcontainer
- Add the generated devcontainer feature lockfile to pin resolved Docker-in-Docker and Node devcontainer feature versions.

### Frontend Build Repair
- Fix the portfolio positions React Query call so the optional symbol argument is not mistaken for the query context under React Query v5.
- Add explicit leveraged-position result narrowing in the risk calculator so TypeScript can safely render effective size and margin requirements.

### Workflow Hardening
- Route `/agent` issue-comment parsing through a `COMMENT_BODY` environment variable in `.github/workflows/custom-agent.yml` so untrusted comment text is no longer interpolated directly into the shell script.

### Roadmap Audit
- Rewrite `docs/ROADMAP_V2.md` around the current implemented codebase, replacing stale skeleton/planned claims with a realistic P0-P3 roadmap.
- Update `docs/TODO.md`, `docs/FEATURES.md`, and `docs/ARCHITECTURE.md` to stop referencing closed umbrella issues as active backlog and to separate implemented local features from unproven production/live-trading maturity.

## 2026-05-25
### Guardian Status Probe Hardening
- Collapse `check_guardian()` to a single authenticated `/v1/models` request per `/research/llm/status` probe instead of issuing separate availability and model-list calls from the same endpoint.
- Keep the no-key short-circuit path intact so cryptotrader still avoids unauthenticated Guardian polling when `GUARDIAN_API_KEY` is absent.

## 2026-05-25
### Research Script Cleanup
- Add ad-hoc Bitfinex market research scripts at the repo root and align them with the current `cex.bitfinex.api.bitfinex_client_v2.BitfinexClient` surface so they lint and compile cleanly before being committed.
- Keep the archived public-safe MARK1 agent snapshot under `scratch/copilot-agent-archive/` for reference alongside the repo-local agent centralization work.

## 2026-05-25
### Copilot Agent Centralization
- Remove repo-local `.github/agents/` copies (`MARK1`, `monks`, `spock`, `trader`) and point the repo documentation at the canonical agents in `/home/flip/github-copilot-config/.github/agents/`.
- Move the support repos under `related-repos/`, ignore that parent directory in the main repo, and treat `market-data` plus `wallets-data` as cryptotrader-owned sibling repos instead of loose home-root projects.

## 2026-02-05
### Multi-Brain AI Architecture (Epic 3 — #205)
- Add `core/ai/` module skeleton — Role-Based Mixture of Agents architecture
- Add provider adapters: DeepSeek (R1/V3.2), OpenAI (o3-mini), xAI (Grok 4), Ollama (local)
- Add agent roles: Screener, Tactical, Fundamental, Strategist with domain-specific prompts
- Add `LLMRouter` for parallel role dispatch with usage tracking
- Add `ConsensusEngine` with weighted voting and hard VETO support
- Add `PromptRegistry` with versioning and default system prompts (from research doc 08)
- Add frontend skeleton: `AiConfigPanel.tsx`, `aiStore.ts`, `api/ai.ts` (12 TypeScript types + 6 API functions)
- Add DB migration `001_ai_tables.sql`: `system_prompts`, `ai_role_configs`, `ai_usage_log`, `ai_decisions`
- Add AI provider env vars to `.env.example` (DEEPSEEK, OPENAI, XAI, GOOGLE, OLLAMA)
- Update `docs/ARCHITECTURE.md` with AI pipeline step and module reference
- Update `docs/ROADMAP_V2.md` — Epic 3 upgraded to 🟠 High with full architecture breakdown
- Research basis: m0nklabs/market-data PR #14 (8 benchmark docs)

## 2026-02-02
### Frontend Improvements
- Add Market Watch view with live price updates, 24h change %, RSI, and EMA trend indicators
- Enhance Signals view with color-coded signal cards showing RSI, MACD, and EMA crossover signals
- Improve Opportunities view with detailed signal breakdowns and clickable symbols
- Add `useMemo` for chart candle sorting to fix lightweight-charts assertion errors
- Disable wallet service calls (port 8101 not deployed) to prevent NetworkErrors
- Add Paper Trading as separate nav section with dedicated Orders and Positions views
- Improve OrdersTable to support both paper trading and exchange order formats

### Backend API
- Add `/market-watch` endpoint returning prices, 24h stats, RSI, and EMA trends for all symbols
- Enhance `/signals` endpoint to scan all symbols with multi-indicator scoring (RSI, EMA, MACD)
- Add `/research/{symbol}` endpoint for comprehensive technical analysis with LLM integration
- Add `/research/llm/status` endpoint to check Ollama availability
- Fix `/gaps/summary` SQL to use correct column names (`open_time` vs `open_time_ms`)

### New Core Modules
- Add `core/signals/reasoning.py` - Technical analysis engine with rule-based recommendations
- Add `core/signals/llm.py` - Ollama integration for natural language trading explanations

### Configuration & Documentation
- Add port management section to `.github/copilot-instructions.md`
- Document systemd services for frontend (user) and market-data (system)
- Add debug and test scripts in `scripts/`

## 2025-12-21
- Add `scripts/bitfinex_candles_smoke.py` to validate Bitfinex public candle downloads without a DB.
- Add minimal frontend dashboard skeleton under `frontend/` (sticky header/footer, panel layout, small fonts, dark mode, collapsible panels) and document it.
- Add a minimal settings popup in the header (cogwheel button) for dashboard controls.
- Update frontend dashboard skeleton to use an MT4/5-inspired dock layout while keeping panels collapsible.
- Add `docs/OPERATIONS.md` runbook for ports + systemd service management.
- Make the frontend dev server listen on all interfaces so it can be opened via LAN IP (e.g. `http://192.168.1.6:5176/`).
- Add a user-level systemd service for the frontend (`systemd/cryptotrader-frontend.service`) serving the built UI on port 5176.
- Add `--resume` workflow for candle backfill and gap repair to avoid manual start/end micromanagement.
- Add Bitfinex candle gap detect/repair job (`python -m core.market_data.bitfinex_gap_repair`) and implement `CandleGapStore` in Postgres.
- Add Bitfinex historical candle backfill runner (`python -m core.market_data.bitfinex_backfill`) that writes to Postgres and logs job/run tracking.
- Implement PostgreSQL `PostgresStores` methods for candles and market-data job tracking (jobs/runs) using SQLAlchemy text queries.
- Add PostgreSQL storage skeleton (`core.storage.postgres`) with a single `PostgresStores` aggregator and `PostgresConfig` (structure only; no DB calls yet).
- Add `core.storage` no-op store stubs implementing persistence Protocols (raise NotImplementedError) to ease delegation without choosing a DB backend yet.
- Expand persistence boundary Protocols to cover new v2 DB tables (jobs/runs, gaps, portfolio snapshots, orders/fills, fee schedules) and export them via `core.persistence`.
- Expand v2 skeleton to be more complete (DB schema, core types, automation/risk/portfolio scaffolding).
- Add DB skeleton (`db/schema.sql`) and init helper (`python -m db.init_db`).
- Extend DB schema with opportunities, execution audit trail, and audit events; add persistence interface skeleton.
- Document concrete PostgreSQL-style tables for candles + indicator weights/signals; fix indicator DB write paths and remove stray research doc references.
- Add workspace VS Code setting to disable terminal GPU acceleration to prevent terminal crashes.
- Consolidate canonical docs to a minimal set under `docs/` and keep `docs/extract/` as an archive of imported historical notes.
- Treat `docs/*` as the authoritative spec set for delegation (do not require local-only `research/*`).
- Add initial `core/` module skeleton for delegated implementation (market data, fees, signals, execution; paper by default).
- Ignore `research/` in `.gitignore` and move canonical requirements into `docs/` (add `docs/TODO.md` and expand `docs/ARCHITECTURE.md`).
- Add `docs/ORCHESTRATION.md` and switch delegation references to `docs/*` (update issue #1 accordingly).
- Pivot project focus toward trading opportunities, technical analysis, and API autotrading (v2 direction).
- Add Copilot agent config at `.github/agents/monks.agent.md` and align repo to the `.github/agents` naming.
- Add `.gitignore` + `.env.example` to prevent committing secrets.
- Vendor in core TA module (`shared/technical_indicators.py`) and Bitfinex REST client (`cex/bitfinex/api/bitfinex_client_v2.py`) from the prior platform for the v2 foundation.
- Add `requirements.txt` and `.venv`-based local setup.
