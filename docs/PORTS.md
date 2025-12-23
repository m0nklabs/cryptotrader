# Ports (cryptotrader)

This document tracks ports used by this repository on the shared server to avoid conflicts.

## Conventions

- Prefer a single reserved port per always-on service.
- Document LAN URLs using the host IP (example: `192.168.1.6`).

## Inventory

| Service | Port | Proto | Notes |
|--------|------|-------|-------|
| Frontend dashboard (Vite preview via systemd) | 5176 | TCP | `cryptotrader-frontend.service` |
| Dashboard API (DB-backed candles) | 8787 | TCP | `python scripts/api_server.py` (dev helper) |

