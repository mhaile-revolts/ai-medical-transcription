from fastapi import APIRouter

router = APIRouter(prefix="", tags=["system"])


@router.get("/health")
async def health_check_v1() -> dict:
    """API v1 health endpoint."""
    return {"status": "ok", "version": "v1"}
