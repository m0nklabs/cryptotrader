# Changelog

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
