from __future__ import annotations

from contextvars import ContextVar
from typing import Optional

from fastapi import HTTPException, status


# Context variable storing the current tenant identifier for the in-flight request.
# There is deliberately no production default tenant.  A tenant exists only
# after a verified identity has selected it.
_current_tenant: ContextVar[Optional[str]] = ContextVar("current_tenant", default=None)


def get_current_tenant() -> str:
    """Return the current tenant identifier.

    In HTTP requests this is set by :func:`tenant_dependency`. In non-request
    contexts (e.g., direct service calls in tests) it falls back to "default".
    """

    tenant = _current_tenant.get()
    if not tenant:
        from src.backend.config import settings

        if settings.app_env in {"development", "test"}:
            return "default"
        raise RuntimeError("Tenant context has not been established")
    return tenant


def set_current_tenant(tenant_id: str):
    """Set tenant context for non-HTTP dependency flows such as WebSockets."""
    return _current_tenant.set(tenant_id)


def reset_current_tenant(token) -> None:
    """Restore the tenant context captured before ``set_current_tenant``."""
    _current_tenant.reset(token)


async def tenant_dependency() -> str:
    """Return the tenant established by verified authentication.

    Route authentication calls ``get_current_user`` before repository access;
    this dependency is retained for compatibility and rejects unbound context.
    """
    tenant_id = _current_tenant.get()
    if not tenant_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Tenant membership is required")
    return tenant_id
