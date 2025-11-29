from __future__ import annotations

from typing import Dict, Optional
from uuid import UUID, uuid4

from src.backend.domain.models.user import User, UserRole
from src.backend.tenancy import get_current_tenant


class InMemoryUserService:
    """Very small in-memory user store keyed by auth subject.

    For the MVP, we map the hashed auth subject (from the security layer) to a
    concrete User object so that downstream code can reason about clinicians
    and admins without exposing raw API secrets.
    """

    def __init__(self) -> None:
        self._by_subject: Dict[str, User] = {}

    def upsert_user_for_subject(
        self,
        *,
        subject: str,
        email: str,
        role: UserRole,
    ) -> User:
        existing = self._by_subject.get(subject)
        if existing is not None:
            return existing

        user = User(id=uuid4(), email=email, role=role, tenant_id=get_current_tenant())
        self._by_subject[subject] = user
        return user

    def get_user_by_subject(self, subject: str) -> Optional[User]:
        return self._by_subject.get(subject)


user_service = InMemoryUserService()
