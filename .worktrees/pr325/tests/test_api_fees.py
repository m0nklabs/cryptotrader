"""Tests for POST /fees/estimate."""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient

# Add project root to path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_fees_estimate_endpoint_exists():
    from api.main import app

    routes = [route.path for route in app.routes]
    assert "/fees/estimate" in routes


def test_fees_estimate_happy_path():
    from api.main import app

    client = TestClient(app)

    resp = client.post(
        "/fees/estimate",
        json={
            "taker": True,
            "gross_notional": "1000",
            "currency": "USD",
            "maker_fee_rate": "0.001",
            "taker_fee_rate": "0.002",
            "assumed_spread_bps": 5,
            "assumed_slippage_bps": 10,
        },
    )

    assert resp.status_code == 200
    data = resp.json()

    assert Decimal(str(data["fee_total"])) == Decimal("2.00000000")
    assert Decimal(str(data["spread_cost"])) == Decimal("0.50000000")
    assert Decimal(str(data["slippage_cost"])) == Decimal("1.00000000")
    assert Decimal(str(data["minimum_edge_rate"])) == Decimal("0.00350000")
    assert Decimal(str(data["minimum_edge_bps"])) == Decimal("35.00")


def test_fees_estimate_rejects_non_positive_gross_notional():
    from api.main import app

    client = TestClient(app)

    resp = client.post(
        "/fees/estimate",
        json={
            "taker": True,
            "gross_notional": "0",
            "currency": "USD",
            "maker_fee_rate": "0.001",
            "taker_fee_rate": "0.002",
            "assumed_spread_bps": 5,
            "assumed_slippage_bps": 10,
        },
    )

    assert resp.status_code == 422
