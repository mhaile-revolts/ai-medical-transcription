from __future__ import annotations

from typing import Dict, Optional, Any
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
        self._session_factory: Any = None

    def configure_persistence(self, session_factory: Any) -> None:
        self._session_factory = session_factory

    def upsert_user_for_subject(
        self,
        *,
        subject: str,
        email: str,
        role: UserRole,
    ) -> User:
        existing = self.get_user_by_subject(subject)
        if existing is not None:
            return existing

        user = User(id=uuid4(), email=email, role=role, tenant_id=get_current_tenant())
        self._by_subject[subject] = user
        if self._session_factory is not None:
            from src.backend.infra.db.models import UserORM
            session = self._session_factory()
            try:
                session.add(UserORM(id=user.id, subject=subject, email=user.email,
                                    role=user.role.value, tenant_id=user.tenant_id))
                session.commit()
            except Exception:
                session.rollback()
                raise
            finally:
                session.close()
        return user

    def get_user_by_subject(self, subject: str) -> Optional[User]:
        if self._session_factory is not None:
            from src.backend.infra.db.models import UserORM
            session = self._session_factory()
            try:
                row = (session.query(UserORM)
                       .filter(UserORM.subject == subject,
                               UserORM.tenant_id == get_current_tenant()).first())
                return (User(id=row.id, email=row.email, role=UserRole(row.role),
                             tenant_id=row.tenant_id) if row else None)
            finally:
                session.close()
        return self._by_subject.get(subject)


user_service = InMemoryUserService()
