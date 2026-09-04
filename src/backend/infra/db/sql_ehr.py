from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, Optional
from uuid import UUID

from sqlalchemy.exc import IntegrityError

from src.backend.domain.models.ehr_connection import EHRConnection
from src.backend.domain.models.ehr_message import EHRMessage
from src.backend.infra.db.ehr_repositories import EHRConnectionRepository, EHRMessageRepository
from src.backend.infra.db.models_ehr import EHRConnectionORM, EHRMessageORM
from src.backend.infra.db.session import SessionFactory
from src.backend.tenancy import get_current_tenant


def _connection(row: EHRConnectionORM) -> EHRConnection:
    return EHRConnection(**{column.name: getattr(row, column.name) for column in row.__table__.columns})


def _message(row: EHRMessageORM) -> EHRMessage:
    return EHRMessage(**{column.name: getattr(row, column.name) for column in row.__table__.columns})


class SqlEHRConnectionRepository(EHRConnectionRepository):
    def __init__(self, factory: SessionFactory) -> None:
        self.factory = factory

    def get(self, connection_id: UUID) -> Optional[EHRConnection]:
        with self.factory() as session:
            row = session.get(EHRConnectionORM, connection_id)
            return _connection(row) if row and row.tenant_id == get_current_tenant() else None

    def list_active(self) -> Iterable[EHRConnection]:
        with self.factory() as session:
            rows = session.query(EHRConnectionORM).filter_by(
                tenant_id=get_current_tenant(), is_active=True
            ).all()
            return [_connection(row) for row in rows]

    def save(self, connection: EHRConnection) -> None:
        connection.updated_at = datetime.now(timezone.utc)
        with self.factory() as session:
            session.merge(EHRConnectionORM(**{
                **connection.model_dump(exclude={"base_url"}),
                "base_url": str(connection.base_url) if connection.base_url else None,
            }))
            session.commit()


class SqlEHRMessageRepository(EHRMessageRepository):
    def __init__(self, factory: SessionFactory) -> None:
        self.factory = factory

    def get(self, message_id: UUID) -> Optional[EHRMessage]:
        with self.factory() as session:
            row = session.get(EHRMessageORM, message_id)
            return _message(row) if row and row.tenant_id == get_current_tenant() else None

    def list_by_status(self, *statuses: str) -> Iterable[EHRMessage]:
        with self.factory() as session:
            rows = session.query(EHRMessageORM).filter(
                EHRMessageORM.tenant_id == get_current_tenant(),
                EHRMessageORM.status.in_(statuses),
            ).all()
            return [_message(row) for row in rows]

    def get_by_idempotency_key(self, idempotency_key: str) -> Optional[EHRMessage]:
        with self.factory() as session:
            row = session.query(EHRMessageORM).filter_by(
                tenant_id=get_current_tenant(), idempotency_key=idempotency_key
            ).first()
            return _message(row) if row else None

    def save(self, message: EHRMessage) -> None:
        message.updated_at = datetime.now(timezone.utc)
        with self.factory() as session:
            session.merge(EHRMessageORM(**message.model_dump()))
            session.commit()

    def save_if_absent(self, message: EHRMessage) -> EHRMessage:
        with self.factory() as session:
            try:
                session.add(EHRMessageORM(**message.model_dump()))
                session.commit()
                return message
            except IntegrityError:
                session.rollback()
        existing = self.get_by_idempotency_key(message.idempotency_key)
        if existing is None:
            raise RuntimeError("Idempotency claim failed without an existing message")
        return existing