"""Authentication and authorization primitives.

Production requests are authenticated exclusively with a verified Clerk JWT.
The development/test override is intentionally conspicuous and cannot be
enabled merely by supplying a header in a deployed environment.
"""
from __future__ import annotations

from contextvars import ContextVar
from typing import Any, Optional

import jwt
from fastapi import Depends, HTTPException, Request, WebSocket, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.backend.config import settings
from src.backend.domain.models.user import User, UserRole
from src.backend.services.users.service import user_service
from src.backend.tenancy import set_current_tenant

_bearer = HTTPBearer(auto_error=False)
_current_subject: ContextVar[Optional[str]] = ContextVar("current_subject", default=None)
_current_claims: ContextVar[Optional[dict[str, Any]]] = ContextVar("current_claims", default=None)


def get_current_subject() -> Optional[str]:
    return _current_subject.get()


def _development_override_allowed() -> bool:
    return settings.app_env in {"development", "test"}


def _role(value: Any) -> UserRole:
    if not value:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="JWT clinic role is required")
    normalized = str(value).lower().replace("org:", "")
    try:
        return UserRole(normalized)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="JWT has no permitted clinic role")


def _verify_token(token: str) -> dict[str, Any]:
    try:
        kwargs: dict[str, Any] = {
            "algorithms": ["RS256", "RS384", "RS512", "ES256", "ES384", "ES512"],
            "options": {"require": ["sub", "exp"]},
        }
        if settings.clerk_issuer:
            kwargs["issuer"] = settings.clerk_issuer
        if settings.clerk_audience:
            kwargs["audience"] = settings.clerk_audience
        else:
            kwargs["options"]["verify_aud"] = False
        if settings.clerk_jwt_public_key:
            return jwt.decode(token, settings.clerk_jwt_public_key, **kwargs)
        if settings.clerk_jwks_url:
            key = jwt.PyJWKClient(settings.clerk_jwks_url).get_signing_key_from_jwt(token).key
            return jwt.decode(token, key, **kwargs)
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication token") from exc
    raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="JWT verification is not configured")


async def get_api_key(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> str:
    """Compatibility-named authentication dependency; API keys are not accepted."""
    token = credentials.credentials if credentials else request.cookies.get("__session")
    if token:
        claims = _verify_token(token)
        subject = claims.get("sub")
        tenant = claims.get("org_id") or claims.get("tenant_id")
        if not subject or not tenant:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="JWT tenant membership is required")
        _current_subject.set(str(subject))
        _current_claims.set(claims)
        set_current_tenant(str(tenant))
        return str(subject)

    # This override provides compatibility for isolated developer tests.  It
    # is impossible in staging/production regardless of supplied headers.
    if _development_override_allowed():
        subject = request.headers.get("X-Test-Subject", "development-user")
        tenant = request.headers.get("X-Test-Tenant") or request.headers.get("X-Tenant-ID") or "default"
        role = request.headers.get("X-Test-Role", "admin")
        _current_subject.set(subject)
        _current_claims.set({"sub": subject, "tenant_id": tenant, "role": role})
        set_current_tenant(tenant)
        return subject
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")


async def get_current_user(subject: str = Depends(get_api_key)) -> User:
    claims = _current_claims.get() or {}
    tenant = claims.get("org_id") or claims.get("tenant_id")
    if not tenant:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant membership is required")
    role = _role(claims.get("org_role") or claims.get("role"))
    email = str(claims.get("email") or f"{subject}@example.com")
    # The service is tenant-context aware; do not permit a subject from one
    # organization to reuse a User record created in another organization.
    user = user_service.get_user_by_subject(subject)
    if user is None:
        user = user_service.upsert_user_for_subject(subject=subject, email=email, role=role)
    elif user.tenant_id != str(tenant):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant membership mismatch")
    elif user.role != role:
        # Roles are identity-provider claims, not mutable API input.
        user = user_service.upsert_user_for_subject(subject=subject, email=email, role=role)
    return user


async def get_websocket_user(websocket: WebSocket) -> User:
    """Authenticate a WebSocket before accepting PHI-bearing audio frames."""
    authorization = websocket.headers.get("authorization", "")
    token = authorization.removeprefix("Bearer ").strip() or websocket.cookies.get("__session")
    if token:
        claims = _verify_token(token)
        subject = claims.get("sub")
        tenant = claims.get("org_id") or claims.get("tenant_id")
        if not subject or not tenant:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="JWT tenant membership is required")
    elif _development_override_allowed():
        subject = websocket.headers.get("X-Test-Subject", "development-user")
        tenant = (
            websocket.headers.get("X-Test-Tenant")
            or websocket.headers.get("X-Tenant-ID")
            or "default"
        )
        claims = {
            "sub": subject,
            "tenant_id": tenant,
            "role": websocket.headers.get("X-Test-Role", "admin"),
        }
    else:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")

    _current_subject.set(str(subject))
    _current_claims.set(claims)
    set_current_tenant(str(tenant))
    return await get_current_user(str(subject))


def ensure_can_view_encounter(user: User, clinician_id: Optional[str]) -> None:
    if user.role == UserRole.ADMIN:
        return
    if clinician_id is None or str(user.id) != clinician_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to view this encounter")


def ensure_can_edit_encounter(user: User, clinician_id: Optional[str]) -> None:
    ensure_can_view_encounter(user, clinician_id)


def ensure_is_admin(user: User) -> None:
    if user.role != UserRole.ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Administrator access required")


def ensure_is_scribe_or_admin(user: User) -> None:
    if user.role not in {UserRole.ADMIN, UserRole.SCRIBE}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to access scribe resources")