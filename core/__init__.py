"""Core domain modules.

This package contains the v2 core building blocks intended for delegated development:

- market_data: OHLCV ingestion and normalization
- fees: fee/cost modeling (maker/taker, spread, slippage)
- signals: signal aggregation and opportunity scoring
- execution: paper/live execution adapters (paper by default)
- automation: policies and safety checks (dry-run by default)
- risk: risk limits and validation helpers
- portfolio: positions and balances (interfaces)
- persistence: persistence boundary (interfaces)
- storage: reserved for concrete persistence implementations

Authoritative specs live in `docs/` (see `docs/ARCHITECTURE.md` and `docs/TODO.md`).
"""
