from __future__ import annotations

from contextvars import ContextVar
from typing import Optional

from fastapi import Header


# Context variable storing the current tenant identifier for the in-flight request.
# Defaults to "default" so existing single-tenant clients/tests continue to work
# without specifying X-Tenant-ID.
_current_tenant: ContextVar[str] = ContextVar("current_tenant", default="default")


def get_current_tenant() -> str:
    """Return the current tenant identifier.

    In HTTP requests this is set by :func:`tenant_dependency`. In non-request
    contexts (e.g., direct service calls in tests) it falls back to "default".
    """

    return _current_tenant.get()


async def tenant_dependency(
    x_tenant_id: Optional[str] = Header(None, alias="X-Tenant-ID"),
) -> str:
    """FastAPI dependency that establishes the tenant context for a request.

    If the header is absent, we fall back to the "default" tenant.
    """

    tenant_id = x_tenant_id or "default"
    _current_tenant.set(tenant_id)
    return tenant_id
