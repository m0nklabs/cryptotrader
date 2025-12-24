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
  - Add manual spacing between requests if needed.

## Quickstart: systemd user units

This section provides a quickstart for managing systemd user units for market data ingestion.

### Reloading systemd user units

After installing or modifying unit files:

- `systemctl --user daemon-reload`

### Enabling and starting timers

To enable and start a timer (e.g., for backfill or gap repair):

- `systemctl --user enable --now cryptotrader-bitfinex-backfill@10.timer`
- `systemctl --user enable --now cryptotrader-bitfinex-gap-repair@30.timer`

### Verifying timer status

To list all timers and their status:

- `systemctl --user list-timers --all`

To check the status of a specific timer:

- `systemctl --user status cryptotrader-bitfinex-backfill@10.timer`

### Viewing logs

To view logs for a specific unit:

- `journalctl --user -u cryptotrader-bitfinex-backfill@10.service --since "1 hour ago"`

To view logs for a specific timer:

- `journalctl --user -u cryptotrader-bitfinex-gap-repair@30.timer --since "1 hour ago"`

### Examples

#### Backfill timer

- Enable: `systemctl --user enable --now cryptotrader-bitfinex-backfill@10.timer`
- Status: `systemctl --user status cryptotrader-bitfinex-backfill@10.timer`
- Logs: `journalctl --user -u cryptotrader-bitfinex-backfill@10.service --since "1 hour ago"`

#### Gap repair timer

- Enable: `systemctl --user enable --now cryptotrader-bitfinex-gap-repair@30.timer`
- Status: `systemctl --user status cryptotrader-bitfinex-gap-repair@30.timer`
- Logs: `journalctl --user -u cryptotrader-bitfinex-gap-repair@30.service --since "1 hour ago"`

#### Frontend service

- Enable: `systemctl --user enable --now cryptotrader-frontend.service`
- Status: `systemctl --user status cryptotrader-frontend.service`
- Logs: `journalctl --user -u cryptotrader-frontend.service --since "1 hour ago"`
