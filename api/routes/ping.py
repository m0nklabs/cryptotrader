"""Simple ping endpoint — zero DB, zero external dependencies."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/ping", tags=["Health"])
async def ping() -> dict[str, str]:
    """Return a simple pong response.

    Returns:
        JSON with status: "pong".
    """
    return {"status": "pong"}
