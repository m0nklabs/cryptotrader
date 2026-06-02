# Operations (runbook)

This document covers how to run the `cryptotrader` dashboard and related v2 components on a multi-project server.

## Ports

- Shared PostgreSQL for both workspaces: `50432`
- Copilot backend / frontend / legacy helper: `50000`, `50176`, `50787`
  - LAN URL example (if host is `192.168.1.6`): `http://192.168.1.6:50176/`
- Hermes backend / frontend / legacy helper: `51000`, `51176`, `51787`
- Ingestion daemon ports are reserved as `50100` (Copilot) and `51100` (Hermes)

Notes:

- Both workspaces share the same Postgres endpoint on `50432`, but must never share 50k/51k app ports.
- `INGESTION_PORT` is reserved for a future standalone market-data daemon. This repo still uses timer-based Bitfinex ingestion units.

## Dual-Stack Services (system scope)

Install the systemd templates from `deployment/systemd/` into `/etc/systemd/system/`.

- Copilot units live in `deployment/systemd/copilot/`
- Hermes units live in `deployment/systemd/hermes/`

Install + start:

- `sudo cp /home/flip/cryptotrader_copilot/deployment/systemd/copilot/*.service /etc/systemd/system/`
- `sudo cp /home/flip/cryptotrader_copilot/deployment/systemd/hermes/*.service /etc/systemd/system/`
- `sudo systemctl daemon-reload`
- `sudo systemctl enable --now ct-backend-copilot ct-frontend-copilot ct-legacy-copilot`

Status / logs:

- `sudo systemctl status ct-backend-copilot ct-frontend-copilot ct-legacy-copilot`
- `journalctl -u ct-backend-copilot -u ct-frontend-copilot -u ct-legacy-copilot -f`

Restart / stop:

- `sudo systemctl restart ct-backend-copilot ct-frontend-copilot ct-legacy-copilot`
- `sudo systemctl stop ct-backend-copilot ct-frontend-copilot ct-legacy-copilot`

Hermes automation rules:

- Hermes may only start and stop `ct-*-hermes` units during tests.
- Example start: `sudo systemctl start ct-backend-hermes ct-frontend-hermes ct-legacy-hermes`
- Example stop: `sudo systemctl stop ct-backend-hermes ct-frontend-hermes ct-legacy-hermes`
- There is no `ct-ingestion-*` daemon yet in this repo. Keep using the existing `cryptotrader-bitfinex-*` timer units, or the separate `market-data` repo when you need a port-bound ingestion API.

## Offline vs online

- Dashboard UI can run without internet once it is built and served locally.
- Market data ingestion (Bitfinex candle downloads) requires internet.

## Common checks

- Verify port is listening:
  - `ss -tulpen | grep -E '50432|50000|50176|50787|51000|51176|51787'`

- If the unit file changed:
  - `sudo systemctl daemon-reload`

## Troubleshooting

- Never print or log secrets (e.g. `DATABASE_URL`, API keys) when debugging; prefer checking service status/logs instead of echoing env vars.

### Bitfinex HTTP 429 (rate limits)

- Meaning: Bitfinex rejected the request because too many calls were made in a short window.
- What to do:
  - Let the built-in exponential backoff finish (rerun after waiting 30–120s).
  - If a systemd timer or cron wrapper is calling the job, ensure only one instance is running and lengthen the interval before the next run.
  - Reduce the lookback window to shrink request volume (e.g., use `--resume`, or run smaller `--start/--end` slices instead of a huge range).
  - Add manual spacing between runs if you are triggering multiple backfills.
    - Example: `sleep 5 && python -m core.market_data.bitfinex_backfill --symbol BTCUSD --timeframe 1h --resume`

### Postgres container (docker compose)

- Shared DB endpoint for both `cryptotrader_copilot` and `../cryptotrader_hermes`: `localhost:50432`
- Keep only one shared Postgres container running; other workspaces should connect to it instead of creating a second DB.
- Keep API/frontend/ingestion host ports separate between workspaces: prefer 50xxx for Copilot and 51xxx for Hermes.
- Check status: `docker compose ps`
- Tail logs: `docker compose logs -f postgres`
- Quick health query: `docker compose exec postgres sh -lc 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT 1;"'`
- Restart the DB container if needed: `docker compose restart postgres`

### systemd --user timers/services

Quickstart (examples use instance format `@SYMBOL-TIMEFRAME`, e.g. `@BTCUSD-1m`):

- Reload unit files after changes: `systemctl --user daemon-reload`
- Enable + start realtime ingest: `systemctl --user enable --now cryptotrader-bitfinex-realtime@BTCUSD-1m.timer`
- Disable + stop realtime ingest: `systemctl --user disable --now cryptotrader-bitfinex-realtime@BTCUSD-1m.timer`
- Enable + start gap repair: `systemctl --user enable --now cryptotrader-bitfinex-gap-repair@BTCUSD-1m.timer`
- Disable + stop gap repair: `systemctl --user disable --now cryptotrader-bitfinex-gap-repair@BTCUSD-1m.timer`
- Follow logs (service): `journalctl --user -u cryptotrader-bitfinex-backfill@BTCUSD-1m.service -f`

- List timers (next run + last run, includes inactive):\
  `systemctl --user list-timers --all | grep -E 'cryptotrader-(bitfinex|frontend)'`
- Service/timer status (examples):\
  `systemctl --user status cryptotrader-bitfinex-backfill@BTCUSD-1m.timer`\
  `systemctl --user status cryptotrader-bitfinex-gap-repair@BTCUSD-1m.timer`\
  `systemctl --user status cryptotrader-frontend.service`
- Recent logs for a specific instance (without printing secrets):\
  `journalctl --user -u cryptotrader-bitfinex-backfill@BTCUSD-1m.service --since "2 hours ago"`\
  `journalctl --user -u cryptotrader-bitfinex-gap-repair@BTCUSD-1m.service --since "2 hours ago"`\
  `journalctl --user -u cryptotrader-frontend.service --since "1 hour ago"`
- Force a one-off run of a specific instance (outside of any timer):\
  `systemctl --user start cryptotrader-bitfinex-backfill@BTCUSD-1m.service`\
  `systemctl --user start cryptotrader-bitfinex-gap-repair@BTCUSD-1m.service`\
  `systemctl --user start cryptotrader-frontend.service`

## AI System Initialization

### Guardian API Key Requirement

Guardian-backed LLM features require `GUARDIAN_API_KEY` to be set in the environment.
When absent, Guardian features short-circuit rather than polling the proxy unauthenticated:

- `GuardianAnalyst.is_available()` raises `GuardianUnauthenticated`
- `GuardianProvider.health_check()` returns `False`
- `MultiBrain.is_available()` returns `False`
- `GuardianAnalyst.list_models()` returns `[]`

Set it to any non-empty string (the value is used as a Bearer token):

```bash
export GUARDIAN_API_KEY="your-key-here"
```

### Automatic Seeding on Startup

**Default behavior**: The FastAPI backend automatically seeds default AI configuration on startup (via `bootstrap_ai()` in `api/routes/ai.py`).

This seeding is **idempotent** and ensures:
- Default system prompts exist for all 4 roles (Screener, Tactical, Fundamental, Strategist)
- Exactly one prompt is marked active per role
- Default role configs exist with proper provider/model assignments
- Existing user modifications are never overwritten

**No manual action required** - the seeding happens automatically when the API starts.

### Manual Seeding (Optional)

If you need to manually seed or re-seed the AI configuration (e.g., after a database reset):

```bash
export DATABASE_URL="postgresql://user:pass@host:port/cryptotrader"
python scripts/seed_ai_defaults.py
```

**Output example:**
```
Seeding system prompts...
  ✓ Created prompt: screener_v1 (role=screener, v1)
  ✓ Created prompt: tactical_v1 (role=tactical, v1)
  ✓ Created prompt: fundamental_v1 (role=fundamental, v1)
  ✓ Created prompt: strategist_v1 (role=strategist, v1)

Seeding role configurations...
  ✓ Created role config: screener (deepseek/deepseek-chat)
  ✓ Created role config: tactical (deepseek/deepseek-reasoner)
  ✓ Created role config: fundamental (xai/grok-4)
  ✓ Created role config: strategist (openai/o3-mini)

✅ Seeding completed successfully!
```

**Running multiple times is safe** - the script checks for existing records and skips them.

### Verifying AI Configuration

Check that the AI system is properly initialized:

```bash
# Query role configs
psql $DATABASE_URL -c "SELECT name, provider, model, enabled FROM ai_role_configs;"

# Query active prompts
psql $DATABASE_URL -c "SELECT role, id, version, is_active FROM system_prompts WHERE is_active = true;"
```

Expected output: 4 role configs (one per role) and 4 active prompts (one per role).

### Troubleshooting

**Issue**: "No role configs found in database" warning at startup
- **Cause**: Database migration not applied or seeding failed
- **Fix**: Run database migrations manually, then restart the API

**Issue**: "AI bootstrap failed to seed defaults" warning
- **Cause**: Database connection issue or insufficient permissions
- **Fix**: Check DATABASE_URL and database permissions; the API will fall back to in-memory defaults

## Backend API service (FastAPI)

The frontend proxies `/api/*`, `/candles/*`, `/ws/*` and other routes to FastAPI.

- Command (dev): `PORT=50000 python scripts/run_api.py --host 0.0.0.0`

In addition to REST endpoints, the backend serves:

- Candle streaming via SSE: `/candles/stream`
- Live prices via WebSocket: `/ws/prices`

## Legacy dashboard API service (optional)

Older iterations used a separate DB-backed helper API. It is optional now.

- Script: `LEGACY_PORT=50787 python scripts/api_server.py --host 127.0.0.1`
- Unit file: `deployment/systemd/copilot/ct-legacy-copilot.service`

Install + start:

- `sudo cp /home/flip/cryptotrader_copilot/deployment/systemd/copilot/ct-legacy-copilot.service /etc/systemd/system/`
- `sudo systemctl daemon-reload`
- `sudo systemctl enable --now ct-legacy-copilot`

Status / logs:

- `systemctl --user status cryptotrader-dashboard-api.service`
- `journalctl --user -u cryptotrader-dashboard-api.service -f`

## Daily dossier (systemd timer)

Generate a daily per-coin dossier summary.

- Unit file: `systemd/cryptotrader-dossier.service`
- Timer: `systemd/cryptotrader-dossier.timer` (08:00 UTC, + up to 5 min jitter)

Install + enable:

- `systemctl --user link /home/flip/cryptotrader/systemd/cryptotrader-dossier.service`
- `systemctl --user link /home/flip/cryptotrader/systemd/cryptotrader-dossier.timer`
- `systemctl --user daemon-reload`
- `systemctl --user enable --now cryptotrader-dossier.timer`

Monitor:

- `systemctl --user status cryptotrader-dossier.timer`
- `journalctl --user -u cryptotrader-dossier.service -f`

## Realtime candles into DB + periodic gap repair

Goal:

- Keep the `candles` table continuously updated (near-realtime) using `--resume`.
- Periodically scan and repair missing candles in recent history (gap repair).

### 1) Create instance env files

These templates expect per-instance config under `%h/.config/cryptotrader/`.

Create backfill instance config (example: BTCUSD 1m):

- File: `/home/flip/.config/cryptotrader/bitfinex-backfill-BTCUSD-1m.env`
- Contents:
  - `CT_SYMBOL=BTCUSD`
  - `CT_TIMEFRAME=1m`

Create gap-repair instance config:

- File: `/home/flip/.config/cryptotrader/bitfinex-gap-repair-BTCUSD-1m.env`
- Contents:
  - `CT_SYMBOL=BTCUSD`
  - `CT_TIMEFRAME=1m`
  - Optional: `CT_LOOKBACK_DAYS=30`

Ensure `DATABASE_URL` is set (recommended in `/home/flip/cryptotrader/.env`, see `.env.example`).

### Bootstrap multiple symbols (top pairs)

If you want more symbols to show up in Market Watch (and be chartable), you must first ingest candles for them.

This repo includes a helper script that:

- Runs an initial backfill for a curated list of symbols
- Writes the per-instance env files under `%h/.config/cryptotrader/`
- Enables the `realtime@...` timers (and optionally `gap-repair@...`)

Run (example: 1m candles, last 3 days, enable gap repair timers too):

- `python scripts/bootstrap_symbols.py --timeframe 1m --lookback-days 3 --enable-gap-repair`

Notes:

- The default symbol list is a curated set of common USD pairs; override via `--symbols "BTCUSD,ETHUSD,..."`.
- Some symbols may not exist on Bitfinex; use `--ignore-errors` if you want best-effort.

Timeframes & deep history:

- The dashboard can switch timeframes in the Chart panel.
- For large lookback windows, `1m` history may be limited depending on the exchange/symbol. Prefer higher TFs for deep history (e.g. `1h`, `4h`, `1d`), and bootstrap those timeframes instead.

### 2) Enable timers

Realtime ingest (every 1 minute):

- `systemctl --user link /home/flip/cryptotrader/systemd/cryptotrader-bitfinex-realtime@.timer`
- `systemctl --user link /home/flip/cryptotrader/systemd/cryptotrader-bitfinex-backfill@.service`
- `systemctl --user daemon-reload`
- `systemctl --user enable --now cryptotrader-bitfinex-realtime@BTCUSD-1m.timer`

Periodic gap repair (every ~6 hours by default):

- `systemctl --user link /home/flip/cryptotrader/systemd/cryptotrader-bitfinex-gap-repair@.timer`
- `systemctl --user link /home/flip/cryptotrader/systemd/cryptotrader-bitfinex-gap-repair@.service`
- `systemctl --user daemon-reload`
- `systemctl --user enable --now cryptotrader-bitfinex-gap-repair@BTCUSD-1m.timer`

### 3) Monitor

- Timers: `systemctl --user list-timers --all | grep cryptotrader-bitfinex`
- Recent logs (realtime): `journalctl --user -u cryptotrader-bitfinex-backfill@BTCUSD-1m.service --since "30 minutes ago"`
- Recent logs (gap repair): `journalctl --user -u cryptotrader-bitfinex-gap-repair@BTCUSD-1m.service --since "6 hours ago"`
