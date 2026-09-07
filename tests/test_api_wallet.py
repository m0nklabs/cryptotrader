"""API contract tests for GET /wallet/balances (issue #452).

The dashboard wallet card calls /api/wallet/balances on the main API. These
tests verify the HTTP contract in paper-trading mode (no keys -> mock
balances), with a mocked BitfinexClient (real-credential path), and on
upstream failure (502). No network access.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)

_KEY_VARS = (
    "BITFINEX_API_KEY",
    "BITFINEX_API_KEY_SUB",
    "BITFINEX_API_KEY_MAIN",
    "BITFINEX_API_SECRET",
    "BITFINEX_API_SECRET_SUB",
    "BITFINEX_API_SECRET_MAIN",
)


@pytest.fixture(autouse=True)
def _no_bitfinex_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure paper-trading mode unless a test explicitly installs fake creds."""
    for var in _KEY_VARS:
        monkeypatch.delenv(var, raising=False)


def test_wallet_balances_mock_in_paper_mode() -> None:
    """Without credentials the endpoint returns the mock wallets."""
    resp = client.get("/wallet/balances")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {"wallets"}
    wallets = body["wallets"]
    assert isinstance(wallets, list) and len(wallets) == 3
    for w in wallets:
        assert set(w) == {"type", "currency", "balance", "available"}
    currencies = {w["currency"] for w in wallets}
    assert currencies == {"USD", "BTC", "ETH"}


def test_wallet_balances_real_client_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """With credentials the endpoint transforms BitfinexClient.get_wallets()."""

    class _FakeClient:
        def __init__(self, api_key: str, api_secret: str) -> None:
            assert api_key == "k" and api_secret == "s"

        def get_wallets(self) -> list[dict[str, Any]]:
            return [
                {"type": "exchange", "currency": "USD", "balance": 5.0,
                 "available_balance": 4.0},
                {"type": "margin", "currency": "BTC", "balance": 1.0},
            ]

    monkeypatch.setenv("BITFINEX_API_KEY", "k")
    monkeypatch.setenv("BITFINEX_API_SECRET", "s")
    monkeypatch.setattr(
        "cex.bitfinex.api.bitfinex_client_v2.BitfinexClient", _FakeClient
    )

    resp = client.get("/wallet/balances")
    assert resp.status_code == 200
    wallets = resp.json()["wallets"]
    assert wallets == [
        {"type": "exchange", "currency": "USD", "balance": 5.0, "available": 4.0},
        # falls back to balance when available_balance is missing
        {"type": "margin", "currency": "BTC", "balance": 1.0, "available": 1.0},
    ]


def test_wallet_balances_upstream_failure_is_502(monkeypatch: pytest.MonkeyPatch) -> None:
    """An upstream client failure surfaces as a 502 wallet_error."""

    class _BrokenClient:
        def __init__(self, api_key: str, api_secret: str) -> None:
            pass

        def get_wallets(self) -> list[dict[str, Any]]:
            raise RuntimeError("boom")

    monkeypatch.setenv("BITFINEX_API_KEY", "k")
    monkeypatch.setenv("BITFINEX_API_SECRET", "s")
    monkeypatch.setattr(
        "cex.bitfinex.api.bitfinex_client_v2.BitfinexClient", _BrokenClient
    )

    resp = client.get("/wallet/balances")
    assert resp.status_code == 502
    assert "wallet_error" in resp.json()["detail"]
