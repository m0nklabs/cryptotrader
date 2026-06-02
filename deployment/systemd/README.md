# Dual-stack systemd templates

These units are intended for system-scope installation on the shared host:

```bash
sudo cp deployment/systemd/copilot/*.service /etc/systemd/system/
sudo cp deployment/systemd/hermes/*.service /etc/systemd/system/
sudo systemctl daemon-reload
```

Copilot stack:

```bash
sudo systemctl enable --now ct-backend-copilot ct-frontend-copilot ct-legacy-copilot
```

Hermes stack:

```bash
sudo systemctl enable --now ct-backend-hermes ct-frontend-hermes ct-legacy-hermes
```

No standalone `ct-ingestion-*` daemon is shipped in this repo yet. The current ingestion flow is timer-based via `cryptotrader-bitfinex-*` units, while `INGESTION_PORT` is only reserved for a future standalone market-data daemon.