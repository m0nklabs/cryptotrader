"""Wallet balances endpoint for the dashboard.

Serves ``GET /wallet/balances`` from the main API so the dashboard's wallet
card works through the vite ``/api`` proxy. Before this route existed the
endpoint only lived on the legacy helper (``scripts/api_server.py`` on :8787),
which the dashboard does not proxy to (issue #452).

The Bitfinex REST call is blocking, so it runs on a worker thread and never
blocks the FastAPI event loop (same pattern as the other route modules).
"""

import asyncio
import os
from typing import Any

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/wallet", tags=["wallet"])

# Mock balances for paper-trading mode (no API keys configured) — mirrors the
# legacy helper so the dashboard renders identically in both modes.
_MOCK_WALLETS: list[dict[str, Any]] = [
    {"type": "exchange", "currency": "USD", "balance": 10000.0, "available": 10000.0},
    {"type": "exchange", "currency": "BTC", "balance": 0.5, "available": 0.5},
    {"type": "exchange", "currency": "ETH", "balance": 2.0, "available": 2.0},
]


def _bitfinex_credentials() -> tuple[str | None, str | None]:
    """Resolve API credentials from the environment (main, then sub variants)."""
    api_key = (
        os.environ.get("BITFINEX_API_KEY")
        or os.environ.get("BITFINEX_API_KEY_SUB")
        or os.environ.get("BITFINEX_API_KEY_MAIN")
    )
    api_secret = (
        os.environ.get("BITFINEX_API_SECRET")
        or os.environ.get("BITFINEX_API_SECRET_SUB")
        or os.environ.get("BITFINEX_API_SECRET_MAIN")
    )
    return api_key, api_secret


def _fetch_wallet_balances() -> dict[str, Any]:
    """Fetch wallet balances from Bitfinex, or return mock balances in paper mode."""
    api_key, api_secret = _bitfinex_credentials()

    if not api_key or not api_secret:
        return {"wallets": [dict(w) for w in _MOCK_WALLETS]}

    # Imported lazily: only needed (and only importable) with credentials set.
    from cex.bitfinex.api.bitfinex_client_v2 import BitfinexClient

    client = BitfinexClient(api_key=api_key, api_secret=api_secret)
    wallets = client.get_wallets()

    out: list[dict[str, Any]] = []
    for wallet in wallets:
        out.append(
            {
                "type": wallet["type"],
                "currency": wallet["currency"],
                "balance": wallet["balance"],
                "available": wallet.get("available_balance", wallet["balance"]),
            }
        )
    return {"wallets": out}


@router.get("/balances")
async def wallet_balances() -> dict[str, Any]:
    """Wallet balances for the dashboard card (paper-mode mock without keys)."""
    loop = asyncio.get_running_loop()
    try:
        return await loop.run_in_executor(None, _fetch_wallet_balances)
    except Exception as exc:  # noqa: BLE001 — surface upstream failure to the dashboard
        raise HTTPException(status_code=502, detail=f"wallet_error: {exc}") from exc
