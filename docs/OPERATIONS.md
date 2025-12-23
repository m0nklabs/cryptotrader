# Operations (runbook)

This document covers how to run the `cryptotrader` dashboard and related v2 components on a multi-project server.

## Ports

- Frontend dashboard (this repo): `5176`
  - LAN URL example (if host is `192.168.1.6`): `http://192.168.1.6:5176/`

Notes:

- Port `5176` is reserved to avoid conflicts with other projects on the same server.

## Quickstart: systemd --user units

This section provides copy/paste commands to install, enable, and monitor the systemd user units in `systemd/`.

**⚠️ Security reminder:** Never print or log secrets (e.g., `DATABASE_URL`, API keys) when debugging. Use `systemctl status` and `journalctl` instead of echoing environment variables.

### 1. Initial setup

After cloning the repo or updating unit files, reload systemd to pick up changes:

```bash
systemctl --user daemon-reload
```

### 2. Enable and start units

**Frontend service:**

```bash
# Link the unit file (adjust path as needed)
systemctl --user link ~/cryptotrader/systemd/cryptotrader-frontend.service

# Enable and start immediately
systemctl --user enable --now cryptotrader-frontend.service
```

**Ingestion timers (when available):**

When timer units are added to `systemd/`, use the following pattern to enable them:

```bash
# Example for backfill timer (adjust symbol and timeframe as needed)
systemctl --user enable --now cryptotrader-bitfinex-backfill@BTCUSD-1m.timer

# Example for gap-repair timer
systemctl --user enable --now cryptotrader-bitfinex-gap-repair@BTCUSD-1m.timer
```

### 3. Verify timers and services

List all timers (including inactive ones):

```bash
systemctl --user list-timers --all
```

Filter for cryptotrader timers:

```bash
systemctl --user list-timers --all | grep cryptotrader
```

Check status of specific units:

```bash
# Frontend service
systemctl --user status cryptotrader-frontend.service

# Timer examples (when available)
systemctl --user status cryptotrader-bitfinex-backfill@BTCUSD-1m.timer
systemctl --user status cryptotrader-bitfinex-gap-repair@BTCUSD-1m.timer
```

### 4. View logs

Recent logs for frontend service:

```bash
# Last hour
journalctl --user -u cryptotrader-frontend.service --since "1 hour ago"

# Follow live logs
journalctl --user -u cryptotrader-frontend.service -f
```

Logs for ingestion services (when available):

```bash
# Backfill service (last 2 hours)
journalctl --user -u cryptotrader-bitfinex-backfill@BTCUSD-1m.service --since "2 hours ago"

# Gap-repair service (last 2 hours)
journalctl --user -u cryptotrader-bitfinex-gap-repair@BTCUSD-1m.service --since "2 hours ago"
```

### 5. Stop or disable units

Stop a running service:

```bash
systemctl --user stop cryptotrader-frontend.service
```

Disable a timer (prevents automatic start):

```bash
systemctl --user disable cryptotrader-bitfinex-backfill@BTCUSD-1m.timer
```

Stop and disable in one command:

```bash
systemctl --user disable --now cryptotrader-frontend.service
```

## Frontend service details

The frontend is served as a **built** UI using `npm run preview` on port `5176`.

**Unit file:** `systemd/cryptotrader-frontend.service`

**Service lifecycle:**

- On start, the unit runs `npm run build` to ensure the latest UI is served
- The built assets are served via `npm run preview -- --host 0.0.0.0 --port 5176 --strictPort`
- Restarts automatically on failure after 2 seconds

**Manual operations:**

```bash
# Restart the service (e.g., after code changes)
systemctl --user restart cryptotrader-frontend.service

# Temporarily stop the service
systemctl --user stop cryptotrader-frontend.service
```

For installation and log viewing, see the [Quickstart section](#quickstart-systemd---user-units).

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

For basic operations (enable, status, logs), see the [Quickstart section](#quickstart-systemd---user-units).

**Additional troubleshooting commands:**

Force a one-off run of a service (outside of any timer):

```bash
# Frontend service
systemctl --user start cryptotrader-frontend.service

# Ingestion services (when available)
systemctl --user start cryptotrader-bitfinex-backfill@BTCUSD-1m.service
systemctl --user start cryptotrader-bitfinex-gap-repair@BTCUSD-1m.service
```

Check which timers are enabled and their next/last run times:

```bash
systemctl --user list-timers --all | grep -E 'cryptotrader-(bitfinex|frontend)'
```
