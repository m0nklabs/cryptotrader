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

