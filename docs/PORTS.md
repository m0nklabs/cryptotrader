# Ports (cryptotrader)

This document tracks ports used by this repository on the shared server to avoid conflicts.

## Conventions

- Prefer a single reserved port per always-on service.
- Document LAN URLs using the host IP (example: `192.168.1.6`).

## Inventory (current)

| Service | Port | Proto | Unit | Notes |
|--------|------|-------|------|-------|
| Frontend dashboard | 5176 | TCP | `cryptotrader-frontend.service` | `vite preview` (serves `frontend/dist/`); proxies `/api` → `127.0.0.1:8000` via `VITE_API_PROXY_TARGET` set in the unit |
| Main FastAPI backend | 8000 | TCP | `cryptotrader-api.service` | `uvicorn api.main:app` with `--timeout-graceful-shutdown 15` |
| Legacy dashboard API | 8787 | TCP | `cryptotrader-dashboard-api.service` | `scripts/api_server.py`; serves `/api/wallet/balances` (issue #452: wallet card 404s through the proxy chain) |
| PostgreSQL (docker) | 50432 | TCP | docker container `cryptotrader-postgres` (`postgres:16`) | Databases: `cryptotrader` (live, used via `DATABASE_URL` in `.env`), `cryptotrader_archive_20260602` (frozen 2026-06-02 snapshot), `cryptotrader_test` (empty) |

- LAN URL example (if host is `192.168.1.6`): `http://192.168.1.6:5176/`
- No port: `cryptotrader-approve-workflows.service` (daemon) and the timers (`cryptotrader-dossier.timer`, `cryptotrader-bitfinex-realtime@…`, `cryptotrader-bitfinex-gap-repair@…`) run without a listener.

## Retired ports

The former copilot stack (`ct-*-copilot`, workspace `/home/flip/cryptotrader_copilot`) and hermes stack (`ct-*-hermes`, workspace `/home/flip/cryptotrader_hermes`) are decommissioned: their units were removed and both workspace directories were deleted. Do not document or treat these as live.

| Port | Former use |
|------|-----------|
| 50000 | Copilot FastAPI backend (`ct-backend-copilot.service`) — retired |
| 50100 | Copilot ingestion daemon (reserved, never deployed) — retired |
| 50176 | Copilot frontend dashboard (`ct-frontend-copilot.service`) — retired |
| 50787 | Copilot legacy dashboard API (`ct-legacy-copilot.service`) — retired |
| 51000 | Hermes backend (`ct-backend-hermes.service`) — retired |
| 51100 | Hermes ingestion daemon (reserved, never deployed) — retired |
| 51176 | Hermes frontend dashboard (`ct-frontend-hermes.service`) — retired |
| 51787 | Hermes legacy dashboard API (`ct-legacy-hermes.service`) — retired |

Note: `frontend/vite.config.ts` falls back to `http://127.0.0.1:8000` (the main API) when `VITE_API_PROXY_TARGET` is unset. The `cryptotrader-frontend.service` unit pins the same target explicitly, so dev servers and preview agree on the main API.

## Ingestion

Market-data ingestion is timer-based via systemd user units (`cryptotrader-bitfinex-realtime@SYMBOL-TIMEFRAME.timer`, `cryptotrader-bitfinex-gap-repair@SYMBOL-TIMEFRAME.timer`); no standalone ingestion daemon exists and no port is reserved for one. See [OPERATIONS.md](OPERATIONS.md) for the runbook.
