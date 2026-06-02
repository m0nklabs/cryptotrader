# Ports (cryptotrader)

This document tracks ports used by this repository on the shared server to avoid conflicts.

## Conventions

- Prefer a single reserved port per always-on service.
- Document LAN URLs using the host IP (example: `192.168.1.6`).

## Inventory

| Service | Port | Proto | Notes |
|--------|------|-------|-------|
| Shared PostgreSQL | 50432 | TCP | Shared DB container for `cryptotrader_copilot` and `../cryptotrader_hermes` |
| FastAPI backend API (Copilot default) | 50000 | TCP | `scripts/run_api.py`, compose `api`, `ct-backend-copilot.service` |
| Frontend dashboard (Copilot default) | 50176 | TCP | Vite dev/preview, compose `frontend`, `ct-frontend-copilot.service` |
| Market data daemon (Copilot reserved) | 50100 | TCP | Reserved for a future standalone ingestion daemon; current repo still uses timer-based ingest workers |
| Legacy dashboard API (Copilot default) | 50787 | TCP | `scripts/api_server.py`, compose `legacy`, `ct-legacy-copilot.service` |
| FastAPI backend API (Hermes reserved) | 51000 | TCP | Reserved for `ct-backend-hermes.service` |
| Frontend dashboard (Hermes reserved) | 51176 | TCP | Reserved for `ct-frontend-hermes.service` |
| Market data daemon (Hermes reserved) | 51100 | TCP | Reserved for a future standalone ingestion daemon in `../cryptotrader_hermes` |
| Legacy dashboard API (Hermes reserved) | 51787 | TCP | Reserved for `ct-legacy-hermes.service` |
