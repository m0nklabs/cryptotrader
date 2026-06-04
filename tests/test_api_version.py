"""Tests for the /version API endpoint."""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """Create a test client."""
    from api.main import app

    return TestClient(app)


def test_version_endpoint_default(client):
    """Test /version endpoint returns default version when APP_VERSION is unset."""
    # Ensure APP_VERSION is not set
    env_before = os.environ.pop("APP_VERSION", None)

    try:
        response = client.get("/version")

        assert response.status_code == 200
        data = response.json()
        assert "version" in data
        assert data["version"] == "0.1.0"
    finally:
        if env_before is not None:
            os.environ["APP_VERSION"] = env_before


def test_version_endpoint_with_env(client):
    """Test /version endpoint reads APP_VERSION from environment."""
    os.environ["APP_VERSION"] = "2.0.0"

    try:
        response = client.get("/version")

        assert response.status_code == 200
        data = response.json()
        assert data["version"] == "2.0.0"
    finally:
        os.environ.pop("APP_VERSION", None)


def test_version_endpoint_response_shape(client):
    """Test /version response has correct JSON shape."""
    response = client.get("/version")

    assert response.status_code == 200
    data = response.json()

    # Must be a dict with exactly one key "version"
    assert isinstance(data, dict)
    assert set(data.keys()) == {"version"}
    assert isinstance(data["version"], str)
    assert len(data["version"]) > 0


def test_version_endpoint_content_type(client):
    """Test /version returns application/json content type."""
    response = client.get("/version")

    assert response.status_code == 200
    assert "application/json" in response.headers["content-type"]
