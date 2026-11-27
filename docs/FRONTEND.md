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

## Observability: view error boundaries

The dashboard ships two React error boundaries, so a rendering bug degrades one
region of the UI instead of blanking the whole page.

| Boundary | Where | Catches | What the operator sees |
|---|---|---|---|
| Per-view boundary | `<main>` in `frontend/src/App.tsx`, keyed on `activeView` | A render error inside the currently selected view | Inline panel: "This view failed to render", the view id, the error message and a "Retry this view" button. Sidebar, header and footer stay usable. |
| App-shell boundary | `frontend/src/main.tsx`, around `<QueryClientProvider><App /></QueryClientProvider>` | A render error in the shell itself (sidebar, header, providers) | Full-page "The dashboard failed to start" panel with the error message plus "Try again" and "Reload page". |

Both fallbacks are styled with the FLIP tokens from `frontend/src/index.css`
(`--panel`, `--line`, `--danger`, `--muted`, …), so they follow the light/dark
theme. Keep it that way: no literal colours in fallback UI.

### Behaviour notes

- The per-view boundary carries `key={activeView}`. Switching views remounts it
  and clears a latched error, so one broken view cannot pin the dashboard in an
  error state. Do not remove that key.
- "Retry this view" resets the boundary state in place and re-renders the same
  view; if the cause is still present the fallback comes straight back.
- Both boundaries log to the browser console (`[ErrorBoundary]`, error plus
  component stack) — the first place to look when an operator reports a screen
  that used to work.
- These boundaries catch render and lifecycle errors. Async failures (a rejected
  fetch, an unreachable backend) are still handled by each view's own
  loading/error state; aligning those onto `StatefulPanel`/`ViewWrapper` is item
  2 of issue #170 and deliberately not part of the wiring above.

### Adding a new view under the boundary

Add the view id to `VIEW_IDS` in `frontend/src/nav.ts`, then render it inside the
existing boundary block in `App.tsx` — do not add another wrapper:

```tsx
{activeView === VIEW_IDS.MY_VIEW && <MyView />}
```

Nothing else is required: the surrounding `<ErrorBoundary key={activeView}>`
already covers it. Add a separate boundary only for an independent subtree that
should fail on its own (for example a chart canvas inside a panel); reuse
`ErrorBoundary` from `frontend/src/components/ErrorBoundary.tsx` with a local
fallback in that case.

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

If you need to proxy to a self-signed HTTPS backend in local development, set `VITE_DISABLE_SSL_VERIFY=true` before running the dev server.

### Legacy dashboard API (optional)

This repo also contains a legacy DB-backed helper API used in older iterations:

- Script: `python scripts/api_server.py` (binds to `127.0.0.1:8787`)
- Systemd unit: `systemd/cryptotrader-dashboard-api.service`

Install + start:

- `systemctl --user link /home/flip/cryptotrader/systemd/cryptotrader-dashboard-api.service`
- `systemctl --user daemon-reload`
- `systemctl --user enable --now cryptotrader-dashboard-api.service`

The unit loads `DATABASE_URL` from `/home/flip/cryptotrader/.env` (see `.env.example`).
