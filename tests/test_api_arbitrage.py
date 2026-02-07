from __future__ import annotations

from fastapi.testclient import TestClient

import api.routes.arbitrage as arbitrage
from api.main import app


class _StubStores:
    def __init__(self, rows):
        self._rows = rows

    def get_latest_candle_closes(self, *, exchanges, timeframe, symbols=None):
        return self._rows


def test_arbitrage_opportunities_returns_results(monkeypatch):
    stub = _StubStores(
        [
            ("bitfinex", "BTCUSD", 100),
            ("binance", "BTCUSD", 105),
        ]
    )
    monkeypatch.setattr(arbitrage, "_get_stores", lambda: stub)
    client = TestClient(app)

    response = client.get("/arbitrage/opportunities?exchanges=bitfinex,binance&timeframe=1m")

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 1
    assert payload["opportunities"][0]["symbol"] == "BTCUSD"
    assert payload["opportunities"][0]["buy_exchange"] == "bitfinex"
    assert payload["opportunities"][0]["sell_exchange"] == "binance"


def test_arbitrage_opportunities_empty(monkeypatch):
    stub = _StubStores([])
    monkeypatch.setattr(arbitrage, "_get_stores", lambda: stub)
    client = TestClient(app)

    response = client.get("/arbitrage/opportunities?exchanges=bitfinex,binance&timeframe=1m")

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 0
    assert payload["opportunities"] == []


def test_arbitrage_opportunities_requires_exchange():
    client = TestClient(app)

    response = client.get("/arbitrage/opportunities?exchanges=")

    assert response.status_code == 400
