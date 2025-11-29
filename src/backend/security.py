from __future__ import annotations

import hashlib
from contextvars import ContextVar
from typing import List, Optional

from fastapi import Depends, HTTPException, Security, status

from src.backend.domain.models.user import User, UserRole
from src.backend.services.users.service import user_service
from fastapi.security import APIKeyHeader

from src.backend.config import settings

# API key is expected in this header when ENABLE_API_AUTH is true.
_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

# Context variable storing a stable, non-raw identifier for the current caller
# (e.g., a hashed API key). This allows downstream consumers such as the
# audit logger to associate events with a subject without exposing the raw
# secret.
_current_subject: ContextVar[Optional[str]] = ContextVar("current_subject", default=None)


def get_current_subject() -> Optional[str]:
    """Return the current subject identifier, if any.

    This is typically set by ``get_api_key`` when API authentication is
    enabled. The value is a stable hash-derived identifier, not the raw
    secret.
    """

    return _current_subject.get()


def _parse_api_keys() -> List[str]:
    """Return the configured API keys as a normalized list.

    API_KEYS is treated as a comma-separated list. Whitespace is stripped and
    empty entries are ignored.
    """

    if not settings.api_keys:
        return []
    return [key.strip() for key in settings.api_keys.split(",") if key.strip()]


async def get_api_key(api_key: Optional[str] = Security(_api_key_header)) -> str:
    """FastAPI dependency for simple API-key based authentication.

    - If ENABLE_API_AUTH is false (default for development/tests), this is a
      no-op and always succeeds.
    - If ENABLE_API_AUTH is true, a valid API key must be supplied in the
      X-API-Key header and match the configured API_KEYS list.
    """

    if not settings.enable_api_auth:
        # Auth disabled – clear any previously set subject and treat as a
        # no-op dependency so existing tests and local development remain
        # unaffected.
        _current_subject.set(None)
        return ""

    allowed_keys = _parse_api_keys()
    if not allowed_keys:
        # Misconfiguration: auth is enabled but no keys are configured.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API authentication is enabled but no API keys are configured.",
        )

    if not api_key or api_key not in allowed_keys:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key.",
        )

    # Derive a non-reversible, stable identifier from the API key for use as a
    # "subject" in audit logs and similar features. This avoids logging the
    # raw secret while still letting us correlate actions by the same caller.
    subject_id = "api-key:" + hashlib.sha256(api_key.encode("utf-8")).hexdigest()[:16]
    _current_subject.set(subject_id)

    return api_key


async def get_current_user(api_key: str = Depends(get_api_key)) -> User:
    """Resolve the current User based on the derived auth subject.

    For the MVP we maintain a small in-memory mapping of auth subjects to
    concrete User objects. In a future iteration this can be replaced with a
    proper database-backed user store or JWT-based authentication without
    changing downstream dependencies.
    """

    # If API auth is disabled, treat the caller as an anonymous admin-like user
    # for development convenience. This branch should not be used in
    # production/pilot environments.
    subject = get_current_subject()
    if subject is None:
        # Synthesize a single admin user when auth is disabled.
        return user_service.upsert_user_for_subject(
            subject="anonymous",
            email="anonymous@example.com",
            role=UserRole.ADMIN,
        )

    user = user_service.get_user_by_subject(subject)
    if user is None:
        # For now, default new subjects to clinician role.
        user = user_service.upsert_user_for_subject(
            subject=subject,
            email=f"user+{subject[:8]}@example.com",
            role=UserRole.CLINICIAN,
        )

    return user


def ensure_can_view_encounter(user: User, clinician_id: Optional[str]) -> None:
    """Raise HTTP 403 if the user is not allowed to view an encounter.

    Admins can view all encounters. Clinicians can only view encounters where
    the clinician_id matches their own user id (stringified UUID).
    """

    if user.role == UserRole.ADMIN:
        return

    if clinician_id is None or str(user.id) != clinician_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to view this encounter",
        )


def ensure_can_edit_encounter(user: User, clinician_id: Optional[str]) -> None:
    """Raise HTTP 403 if the user is not allowed to edit an encounter.

    For the MVP we apply the same rule as for viewing.
    """

    ensure_can_view_encounter(user, clinician_id)


def ensure_is_scribe_or_admin(user: User) -> None:
    """Raise HTTP 403 if the user is not a scribe or admin.

    Used for scribe-panel endpoints that should be restricted to back-office
    scribes and administrators.
    """

    if user.role in {UserRole.ADMIN, UserRole.SCRIBE}:
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Not authorized to access scribe resources",
    )
