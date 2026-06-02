# Dual-stack systemd templates

These units are intended for system-scope installation on the shared host:

Prerequisites before enabling the services:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt -r requirements-dev.txt
cd frontend && npm install
```

The units run from `/home/flip/cryptotrader_copilot` or `/home/flip/cryptotrader_hermes`, so they must be allowed to access those repo paths under `/home/flip`.

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