from fastapi import APIRouter

router = APIRouter()


@router.get("/smoke", tags=["Smoke Test"])
async def smoke_test() -> dict[str, bool | str]:
    """Simple smoke test endpoint."""
    return {"ok": True, "mode": "tier1-smoke"}
