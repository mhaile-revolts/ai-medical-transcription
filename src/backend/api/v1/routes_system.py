from fastapi import APIRouter

from src.backend.config import settings
from src.backend.services.blockchain.multichain import get_multichain_client

router = APIRouter(prefix="", tags=["system"])


@router.get("/health")
async def health_check_v1() -> dict:
    """API v1 health endpoint."""
    return {"status": "ok", "version": "v1"}


@router.get("/system/blockchain/health")
async def blockchain_health_v1() -> dict:
    """Health check for the optional MultiChain integration.

    - When MultiChain is disabled (default), returns ``{"status": "disabled"}``.
    - When enabled but misconfigured, returns ``{"status": "misconfigured"}``.
    - When enabled but unreachable, returns ``{"status": "unreachable"}``.
    - On success, returns ``{"status": "ok", "info": ...}`` where ``info``
      is the result of the `getinfo` RPC (no PHI).
    """

    if not settings.multichain_enabled:
        return {"status": "disabled"}

    client = get_multichain_client()
    if client is None:
        return {"status": "misconfigured"}

    info = client.get_info()
    if info is None:
        return {"status": "unreachable"}

    return {"status": "ok", "info": info}
