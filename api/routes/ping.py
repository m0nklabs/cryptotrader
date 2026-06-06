"""Ping API endpoint."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["ping"])


@router.get("/ping")
async def ping():
    """Get a simple ping response.

    Returns HTTP 200 with a JSON pong.
    """
    return {"status": "pong"}
