"""Tests for the Guardian status probe path."""

from __future__ import annotations

import pytest

from core.signals.llm import check_guardian


class _FakeResponse:
    """Small fake httpx response for Guardian model listing."""

    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        """Fake success response."""

    def json(self) -> dict:
        """Return the canned JSON payload."""
        return self._payload


class _FakeAsyncClient:
    """AsyncClient stand-in that records Guardian model calls."""

    def __init__(self, *args, **kwargs) -> None:
        self.calls = kwargs["_calls"]
        self.payload = kwargs["_payload"]

    async def __aenter__(self) -> _FakeAsyncClient:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False

    async def get(self, url: str, timeout: float = 5.0) -> _FakeResponse:
        self.calls.append((url, timeout))
        return _FakeResponse(self.payload)


@pytest.mark.asyncio
async def test_check_guardian_without_key_short_circuits(monkeypatch):
    """check_guardian should return a clear disabled state without polling Guardian."""
    monkeypatch.delenv("GUARDIAN_API_KEY", raising=False)
    monkeypatch.setenv("GUARDIAN_HOST", "http://guardian.test")

    result = await check_guardian()

    assert result == {
        "available": False,
        "host": "http://guardian.test",
        "default_model": "GLM-4.7-Flash",
        "available_models": [],
        "reason": "GUARDIAN_API_KEY not set",
    }


@pytest.mark.asyncio
async def test_check_guardian_with_key_polls_models_once(monkeypatch):
    """check_guardian should fetch Guardian models once per status probe."""
    calls: list[tuple[str, float]] = []
    payload = {"data": [{"id": "GLM-4.7-Flash"}, {"id": "Qwen3"}]}

    monkeypatch.setenv("GUARDIAN_API_KEY", "present")
    monkeypatch.setenv("GUARDIAN_HOST", "http://guardian.test")

    def _fake_client(*args, **kwargs):
        return _FakeAsyncClient(*args, _calls=calls, _payload=payload, **kwargs)

    monkeypatch.setattr("core.signals.llm.httpx.AsyncClient", _fake_client)

    result = await check_guardian()

    assert result == {
        "available": True,
        "host": "http://guardian.test",
        "default_model": "GLM-4.7-Flash",
        "available_models": ["GLM-4.7-Flash", "Qwen3"],
    }
    assert calls == [("http://guardian.test/v1/models", 5.0)]
