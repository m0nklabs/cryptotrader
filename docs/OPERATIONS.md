# Operations (runbook)

This document covers how to run the `cryptotrader` dashboard and related v2 components on a multi-project server.

## Ports

- Frontend dashboard (this repo): `5176`
  - LAN URL example (if host is `192.168.1.6`): `http://192.168.1.6:5176/`

Notes:

- Port `5176` is reserved to avoid conflicts with other projects on the same server.

## Frontend service (systemd --user)

The frontend is served as a **built** UI using `npm run preview`.

- Unit file: `systemd/cryptotrader-frontend.service`

Install + start:

- `systemctl --user link /home/flip/cryptotrader/systemd/cryptotrader-frontend.service`
- `systemctl --user daemon-reload`
- `systemctl --user enable --now cryptotrader-frontend.service`

Status / logs:

- `systemctl --user status cryptotrader-frontend.service`
- `journalctl --user -u cryptotrader-frontend.service -f`

Restart / stop:

- `systemctl --user restart cryptotrader-frontend.service`
- `systemctl --user stop cryptotrader-frontend.service`

## Offline vs online

- Dashboard UI can run without internet once it is built and served locally.
- Market data ingestion (Bitfinex candle downloads) requires internet.

## Common checks

- Verify port is listening:
  - `ss -tulpen | grep 5176`

- If the unit file changed:
  - `systemctl --user daemon-reload`

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

- Check status: `docker compose ps`
- Tail logs: `docker compose logs -f postgres`
- Quick health query: `docker compose exec postgres psql -U postgres -d cryptotrader -c 'SELECT 1;'`
- Restart the DB container if needed: `docker compose restart postgres`

### systemd --user timers/services

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
