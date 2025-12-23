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

Note: the dashboard’s `/api/*` endpoints are expected to be served by the local dashboard API (DB-backed).

## Chart zoom (mouse wheel)

The candlestick chart supports mouse-wheel zoom:

- Scroll up: zoom in (fewer candles)
- Scroll down: zoom out (more candles)

This adjusts the candle window size fetched from `/api/candles`.

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

To render charts from our Postgres `candles` table, run the local API:

- Script: `python scripts/api_server.py` (binds to `127.0.0.1:8787`)
- Systemd unit: `systemd/cryptotrader-dashboard-api.service`

Install + start:

- `systemctl --user link /home/flip/cryptotrader/systemd/cryptotrader-dashboard-api.service`
- `systemctl --user daemon-reload`
- `systemctl --user enable --now cryptotrader-dashboard-api.service`

The unit loads `DATABASE_URL` from `/home/flip/cryptotrader/.env` (see `.env.example`).

