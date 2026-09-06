# systemd unit templates (single stack)

All cryptotrader units are **systemd user units**. The source of truth is the `systemd/` directory in this repo; `~/.config/systemd/user/` only holds symlinks into it. Edit the template in `systemd/`, then reload — never create a second copy of a unit or a second stack.

Prerequisites before enabling the services:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt -r requirements-dev.txt
cd frontend && npm install && npm run build
```

(`cryptotrader-frontend.service` runs `vite preview`, which serves `frontend/dist/`, so the frontend must be built.)

## Install (symlink deployment pattern)

```bash
ln -sf /home/flip/cryptotrader/systemd/cryptotrader-*.service \
       /home/flip/cryptotrader/systemd/cryptotrader-*.timer \
       ~/.config/systemd/user/
systemctl --user daemon-reload
```

Templated units are enabled per instance, e.g. `systemctl --user enable --now cryptotrader-bitfinex-realtime@BTCUSD-1m.timer`.

## Current unit set

| Unit | What it runs | Notes |
|---|---|---|
| `cryptotrader-api.service` | `uvicorn api.main:app` on `:8000` | `EnvironmentFile=%h/cryptotrader/.env`; `--timeout-graceful-shutdown 15` so a stop never hangs 90 s |
| `cryptotrader-frontend.service` | `vite preview` on `:5176` | `Environment=VITE_API_PROXY_TARGET=http://127.0.0.1:8000` (proxies `/api` to the main API) |
| `cryptotrader-dashboard-api.service` | legacy `scripts/api_server.py` on `:8787` | serves `/api/wallet/balances` (issue #452) |
| `cryptotrader-approve-workflows.service` | approval-workflow daemon | no port |
| `cryptotrader-bitfinex-realtime@.timer` + `cryptotrader-bitfinex-backfill@.service` | realtime candle ingest (1 min) | enable per instance, e.g. `@BTCUSD-1m` |
| `cryptotrader-bitfinex-gap-repair@.timer` + `.service` | periodic candle gap repair (~6 h) | enable per instance |
| `cryptotrader-dossier.service` + `.timer` | daily dossier generation | 08:00 UTC + jitter |

## Enable

```bash
systemctl --user enable --now cryptotrader-api cryptotrader-frontend cryptotrader-dashboard-api cryptotrader-approve-workflows
systemctl --user enable --now cryptotrader-bitfinex-realtime@BTCUSD-1m.timer cryptotrader-bitfinex-gap-repair@BTCUSD-1m.timer cryptotrader-dossier.timer
```

Status / logs (user units: no `sudo`):

```bash
systemctl --user status cryptotrader-api
journalctl --user -u cryptotrader-api -f
```

## Precedence gotcha

`EnvironmentFile=` (`.env`) **overrides** `Environment=` lines in the unit. Do not add fallback env lines (e.g. a fallback `DATABASE_URL` `Environment=` line): the `.env` value always wins, so the fallback is dead config that misled debugging before.

## Retired stacks (copilot / hermes)

The former dual-stack setup is decommissioned — do not reinstall or resurrect it:

- The copilot units `ct-backend-copilot` / `ct-frontend-copilot` / `ct-legacy-copilot` (ports 50000 / 50176 / 50787) and the hermes units `ct-*-hermes` (port 51000) are removed; the workspaces `/home/flip/cryptotrader_copilot` and `/home/flip/cryptotrader_hermes` were deleted.
- The template directories `deployment/systemd/copilot/` and `deployment/systemd/hermes/` were removed as well; their history stays retrievable via git.

No standalone `ct-ingestion-*` daemon is shipped. Ingestion stays timer-based via the `cryptotrader-bitfinex-*` units.
