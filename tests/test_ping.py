"""Tests for the /ping endpoint."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Add project root to path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_ping_route_registered():
    """Test that the /ping route is registered in the app."""
    from api.main import app

    routes = [route.path for route in app.routes]
    assert "/ping" in routes


@pytest.mark.asyncio
async def test_ping_returns_200():
    """Test that /ping returns HTTP 200 status code."""
    from fastapi.testclient import TestClient

    from api.main import app

    client = TestClient(app)
    response = client.get("/ping")

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_ping_returns_pong_body():
    """Test that /ping returns JSON body with status: pong."""
    from fastapi.testclient import TestClient

    from api.main import app

    client = TestClient(app)
    response = client.get("/ping")

    assert response.json() == {"status": "pong"}


@pytest.mark.asyncio
async def test_ping_no_authentication():
    """Test that /ping requires no authentication."""
    from fastapi.testclient import TestClient

    from api.main import app

    client = TestClient(app)
    # Should succeed without any Authorization header
    response = client.get("/ping")

    assert response.status_code == 200
    assert "www-authenticate" not in response.headers
