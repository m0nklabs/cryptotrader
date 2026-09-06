# AGENTS.md — cryptotrader

Personal self-hosted crypto trading platform: Bitfinex market-data ingestion,
backtesting, paper trading, risk-gated execution, AI/dossier features, and a
TimesFM forecasting lane. React+Vite frontend, FastAPI backend, PostgreSQL.

## Ground rules

- All code, comments, docstrings, and docs in this repo are written in English.
- Secrets live only in `.env` (gitignored). Never commit keys, tokens, or DB
  credentials. `.env.example` documents the variable names.
- Verify before you claim: run the targeted checks listed below and report
  results, not intentions.

## Repo layout

| Path | Purpose |
|---|---|
| `api/` | FastAPI app (`api/main.py` registers routers; route modules in `api/routes/`) |
| `core/` | Domain services (`execution/`, `backtest/`, `fees/`, `forecasting/`, `market_cap/`, `storage/postgres/`, …) |
| `frontend/` | React + Vite + Tailwind dashboard |
| `scripts/` | Ops/maintenance scripts (`scripts/research/` = research scripts) |
| `strategies/` | Backtest strategies |
| `systemd/` | **Source of truth for all systemd units** (see below) |
| `deployment/` | Deploy templates and docs |
| `docs/` | All documentation (no `.md` files in repo root) |
| `db/` | Schema, migrations, CRUD |
| `tests/` | Pytest suites (`tests/test_api_*.py`, `tests/unit/`, `tests/integration/`) |

Root exceptions (deliberate, do not "clean" blindly):
- `execution_orchestrator.py` — live module imported by `api/main.py` and
  `api/routes/execution.py` via a root-level import; relocation into `core/`
  is a tracked refactor (update all import sites + tests).
- `backtest_results.json`, `backtest_comparison.json` — generated outputs that
  are also checked-in evidence: `tests/test_fee_proof_gate.py` asserts their
  existence. Regenerate via `scripts/run_backtest.py`.

## Runtime topology (single source of truth)

- All units are **systemd user units that are symlinks into `systemd/`**:
  `~/.config/systemd/user/cryptotrader-*.service -> /home/flip/cryptotrader/systemd/…`.
  Edit the template in `systemd/`, then `systemctl --user daemon-reload`.
  Never create a second copy or a second stack (the former copilot/hermes
  stacks were decommissioned — do not resurrect them).
- Ports: dashboard `:5176` (vite preview; proxies `/api` → `127.0.0.1:8000`
  via `VITE_API_PROXY_TARGET` set in the frontend unit), main API `:8000`,
  legacy helper `:8787` (wallet balances endpoint lives here).
- Database: docker container `cryptotrader-postgres` on `127.0.0.1:50432`,
  database `cryptotrader` (plus `cryptotrader_archive_20260602`,
  `cryptotrader_test`). The live connection string comes from `.env`
  (`DATABASE_URL`).
- systemd precedence gotcha: `EnvironmentFile=` (`.env`) **overrides**
  `Environment=` lines in the unit. Do not add fallback `DATABASE_URL`
  `Environment=` lines — they are dead config that misled debugging before.
- Restarting the API must stay fast: uvicorn runs with
  `--timeout-graceful-shutdown 15` so a stop can never hang 90 s.

## CI runners

CI runs on the **central org-level self-hosted runner pool** of `m0nklabs`,
which runs ON THIS SERVER: 4 runners (`m0nklabs-runner-1` … `-4`) shared by all
org projects. **Never add a per-project runner.**

- Host: `ai-kvm2`
- Auto labels: `self-hosted`, `Linux`, `X64`; all 4 are GPU-capable (label
  `gpu`, 2× NVIDIA RTX on the host)
- Source of truth & configuration: the public repo
  `m0nklabs/github-action-runners` (see its README.md and AGENTS.md)
- Using them in workflows:
  - normal job (no GPU): `runs-on: [self-hosted, Linux]`
  - GPU job: `runs-on: [self-hosted, Linux, gpu]`

### GPU access is serialized (one job at a time)

All runners share the same GPUs. Every GPU job must wrap its heavy commands
with the central lock so two jobs never compete for the same cards:

```yaml
- name: Train
  run: /home/flip/github-action-runners/bin/gpu-run.sh <command>
```

### Generic (reusable) workflows

Do not copy CI logic — reuse the generic workflows from
`m0nklabs/github-action-runners`: `python-ci`, `frontend-ci`, `go-ci`,
`rust-ci`, `gpu-ci`, `codeql-detect`. Call only the ones for languages this
project actually contains:

```yaml
jobs:
  codeql:
    uses: m0nklabs/github-action-runners/.github/workflows/codeql-detect.yml@main
    secrets: inherit
```

### Rules

- Never add per-project runners — always use the org pool.
- No GPU work without `gpu-run.sh` — otherwise two jobs compete for the same cards.
- Never commit secrets in workflows.

Because runners execute on this host, CI failures can also come from host
state (port conflicts, running services) rather than the code — check runner
context before debugging test failures.

## Backend conventions

- Python 3.11 venv at `.venv/`. Lint: `ruff` (E/F, line-length 120).
- Route modules: `router = APIRouter(prefix="/...", tags=[...])`, static routes
  before parametrized ones, module-level lazy singletons (`_service` +
  `_get_service()`); blocking work (torch, subprocess, slow HTTP) goes through
  a thread pool executor — never on the event loop.
- Services in `core/` are plain classes; caching follows the module-dict +
  `threading.Lock` TTL pattern (see `core/market_cap/coingecko.py`).
- Tests: mock external services; unit tests must not need network, DB, GPU, or
  the model weights.

## Forecasting lane

- `core/forecasting/` (service, models, cache) + `api/routes/forecast.py`
  (`POST /forecast`, `POST /forecast/batch`, `GET /forecast/status`).
- Backends: TimesFM 2.5 (`google/timesfm-2.5-200m-pytorch`, Apache-2.0) and
  TimesFM 3.0 (`google/timesfm-3.0-pytorch`, **non-commercial weights** — use
  for local evaluation only). Select via `TIMESFM_BACKEND` /
  `TIMESFM_MODEL_ID`; 3.0 quantiles are 9 columns (p10=0, p50=4, p90=8), 2.5
  are 10 columns (p10=1, p50=5, p90=9) — both surface as p10/p50/p90.
- Env knobs: `TIMESFM_MODEL_ID`, `TIMESFM_BACKEND`, `TIMESFM_DEVICE`
  (auto|cpu|cuda, auto pre-checks free VRAM), `TIMESFM_MAX_CONTEXT`,
  `TIMESFM_MAX_HORIZON`, `TIMESFM_CACHE_TTL`, `TIMESFM_PRELOAD`.
- Forecast cache is keyed on the last closed candle — new candle ⇒ recompute.

## Frontend conventions

- TypeScript strict; verify with `cd frontend && npm run build`.
- Charts draw on raw `<canvas>` (see `EquityCurve.tsx`) — Recharts is NOT
  installed; do not import it without adding the dependency deliberately.
- API clients hardcode `const API_BASE = '/api'` (one per file in
  `frontend/src/api/`); views are wired in `App.tsx` + `nav.ts` (`VIEW_IDS`).
- Styling uses the CSS tokens from `index.css` (`var(--panel)`,
  `var(--panel-2)`, …) — avoid hardcoded hex colors.

## Verification commands

```bash
# backend targeted tests + lint
.venv/bin/python -m pytest tests/test_api_forecast.py tests/test_forecasting_service.py -q
.venv/bin/ruff check <changed paths>

# frontend build
cd frontend && npm run build

# live chain (dashboard → API → DB)
curl -fsS 'http://127.0.0.1:5176/api/health'
curl -fsS 'http://127.0.0.1:5176/api/candles?symbol=BTCUSD&timeframe=1h&limit=2'
curl -fsS http://127.0.0.1:8787/api/wallet/balances   # legacy wallet endpoint
```

Symbol format for the candle store is without slash (`BTCUSD`, not `BTC/USD`).

## Documentation discipline

- Everything user- or operator-facing lives in `docs/`; the repo root stays
  code + config only (see exceptions above).
- `CHANGELOG.md` gets an entry for every user-visible change.
- New features ship with a docs page and tests in the same change.
