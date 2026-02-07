# Frontend (dashboard skeleton)

This repo includes a minimal frontend skeleton under `frontend/`.

## Goals

- Sticky header + sticky footer
- Panel-based dashboard layout
- Minimalistic UI with small font sizes
- Dark mode (toggle in header)
- Everything expandable/collapsible (panels)

## Run locally

From repo root:

- `cd frontend`
- `npm install`
- `npm run dev`

Open:

- `http://localhost:5176/`

If you run the dev server on a machine in your LAN, you can also open it via that machine's IP address.
Example (if your machine IP is `192.168.1.6`):

- `http://192.168.1.6:5176/`

## Dark mode

The dashboard includes a simple theme toggle in the header.
Theme state is stored in `localStorage` under the key `theme` and applied by toggling the `dark` class on the document root.

## Build

- `cd frontend`
- `npm run build`
- `npm run preview`

Note: the dashboard uses relative paths and is proxied by Vite to the FastAPI backend.

## Chart zoom (mouse wheel)

The candlestick chart supports mouse-wheel zoom:

- Scroll up: zoom in (fewer candles)
- Scroll down: zoom out (more candles)

This adjusts the candle window size fetched from `/api/candles`.

Candles are also streamed in near real-time via Server-Sent Events (SSE) on `/candles/stream`.

Live prices are streamed via WebSocket on `/ws/prices`.

Note: Candle WebSocket streaming is currently enabled for Bitfinex only (`CANDLE_WS_SUPPORT`). Other exchanges rely on polling for chart candles, while live price updates still use `/ws/prices`.

## Chart timeframe

The chart supports selecting the candle timeframe (e.g. `1m`, `5m`, `1h`) via the timeframe dropdown in the Chart panel header.

Note: for “deep history” backfills, `1m` can be limited depending on the exchange/symbol. In that case, ingest a higher timeframe (e.g. `1h`, `4h`, `1d`) and select it in the UI.

## Run as a service (systemd --user)

This repo includes a user-level systemd unit:

- `systemd/cryptotrader-frontend.service`

Install + start:

- `systemctl --user link /home/flip/cryptotrader/systemd/cryptotrader-frontend.service`
- `systemctl --user daemon-reload`
- `systemctl --user enable --now cryptotrader-frontend.service`

Status / logs:

- `systemctl --user status cryptotrader-frontend.service`
- `journalctl --user -u cryptotrader-frontend.service -f`

The service serves the built UI via `npm run preview` on port 5176.

### Dashboard API (DB-backed candles)

To render charts from our Postgres `candles` table, run the FastAPI backend:

- Command: `python -m api.main` (binds to `127.0.0.1:8000`)

The frontend proxies:

- `/api/*` → FastAPI (with `/api` prefix stripped)
- `/candles/*`, `/market-watch`, `/gaps`, `/arbitrage/*`, `/dossier/*`, `/export/*`, etc. → FastAPI
- `/ws/*` → FastAPI (WebSocket)

### Legacy dashboard API (optional)

This repo also contains a legacy DB-backed helper API used in older iterations:

- Script: `python scripts/api_server.py` (binds to `127.0.0.1:8787`)
- Systemd unit: `systemd/cryptotrader-dashboard-api.service`

Install + start:

- `systemctl --user link /home/flip/cryptotrader/systemd/cryptotrader-dashboard-api.service`
- `systemctl --user daemon-reload`
- `systemctl --user enable --now cryptotrader-dashboard-api.service`

The unit loads `DATABASE_URL` from `/home/flip/cryptotrader/.env` (see `.env.example`).
