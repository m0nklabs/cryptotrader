"""Tests for the /ping endpoint."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """Create a test client."""
    from api.main import app

    return TestClient(app)


def test_ping_returns_200(client):
    """Test /ping returns HTTP 200."""
    response = client.get("/ping")
    assert response.status_code == 200


def test_ping_returns_pong(client):
    """Test /ping returns {"status": "pong"}."""
    response = client.get("/ping")
    data = response.json()
    assert data == {"status": "pong"}


def test_ping_no_auth_required(client):
    """Test /ping works without any authentication."""
    response = client.get("/ping")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert data["status"] == "pong"


def test_ping_response_shape(client):
    """Test /ping response has exactly {"status": "pong"}."""
    response = client.get("/ping")
    data = response.json()
    assert set(data.keys()) == {"status"}
    assert data["status"] == "pong"
