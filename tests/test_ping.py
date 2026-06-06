"""Tests for the /ping endpoint."""

from fastapi.testclient import TestClient

from api.main import app


def test_ping_returns_pong():
    """GET /ping returns 200 with status: pong."""
    client = TestClient(app)
    response = client.get("/ping")
    assert response.status_code == 200
    assert response.json() == {"status": "pong"}


def test_ping_no_db_dependency():
    """Ping works without any DB connection — no stores init needed."""
    import os

    # Remove DATABASE_URL to ensure no DB is needed
    old_db = os.environ.pop("DATABASE_URL", None)
    try:
        client = TestClient(app)
        response = client.get("/ping")
        assert response.status_code == 200
        assert response.json() == {"status": "pong"}
    finally:
        if old_db:
            os.environ["DATABASE_URL"] = old_db


def test_ping_returns_json_content_type():
    """Ping returns application/json content type."""
    client = TestClient(app)
    response = client.get("/ping")
    assert "application/json" in response.headers["content-type"]
