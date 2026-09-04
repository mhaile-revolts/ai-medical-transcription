from __future__ import annotations

from datetime import datetime
from typing import Dict, Iterable, Optional
from threading import Lock
from uuid import UUID

from src.backend.domain.models.ehr_connection import EHRConnection
from src.backend.domain.models.ehr_message import EHRMessage
from src.backend.infra.db.ehr_repositories import EHRConnectionRepository, EHRMessageRepository
from src.backend.tenancy import get_current_tenant
from src.backend.infra.db.inmemory import RepositoryProxy


class InMemoryEHRConnectionRepository(EHRConnectionRepository):
    """Simple in-memory EHRConnection storage keyed by (tenant_id, id)."""

    def __init__(self) -> None:
        self._connections: Dict[UUID, EHRConnection] = {}

    def get(self, connection_id: UUID) -> Optional[EHRConnection]:
        conn = self._connections.get(connection_id)
        if conn is None:
            return None
        if conn.tenant_id != get_current_tenant():
            return None
        return conn

    def list_active(self) -> Iterable[EHRConnection]:
        current_tenant = get_current_tenant()
        for conn in self._connections.values():
            if conn.tenant_id != current_tenant:
                continue
            if not conn.is_active:
                continue
            yield conn

    def save(self, connection: EHRConnection) -> None:
        now = datetime.utcnow()
        if connection.created_at is None:
            connection.created_at = now
        connection.updated_at = now
        self._connections[connection.id] = connection


class InMemoryEHRMessageRepository(EHRMessageRepository):
    """Simple in-memory EHRMessage storage keyed by id.

    This is sufficient for pilots and tests; SQL-backed storage can be added
    later following the same pattern as encounters/notes/jobs.
    """

    def __init__(self) -> None:
        self._messages: Dict[UUID, EHRMessage] = {}
        self._lock = Lock()

    def get(self, message_id: UUID) -> Optional[EHRMessage]:
        msg = self._messages.get(message_id)
        if msg is None:
            return None
        if msg.tenant_id != get_current_tenant():
            return None
        return msg

    def list_by_status(self, *statuses: str) -> Iterable[EHRMessage]:
        current_tenant = get_current_tenant()
        status_set = set(statuses)
        for msg in self._messages.values():
            if msg.tenant_id != current_tenant:
                continue
            if msg.status not in status_set:
                continue
            yield msg

    def get_by_idempotency_key(self, idempotency_key: str) -> Optional[EHRMessage]:
        current_tenant = get_current_tenant()
        return next(
            (
                message
                for message in self._messages.values()
                if message.tenant_id == current_tenant
                and message.idempotency_key == idempotency_key
            ),
            None,
        )

    def save(self, message: EHRMessage) -> None:
        now = datetime.utcnow()
        if message.created_at is None:
            message.created_at = now
        message.updated_at = now
        self._messages[message.id] = message

    def save_if_absent(self, message: EHRMessage) -> EHRMessage:
        with self._lock:
            existing = self.get_by_idempotency_key(message.idempotency_key)
            if existing is not None:
                return existing
            self.save(message)
            return message


ehr_connection_repository = RepositoryProxy(InMemoryEHRConnectionRepository())
ehr_message_repository = RepositoryProxy(InMemoryEHRMessageRepository())
