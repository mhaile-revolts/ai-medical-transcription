from __future__ import annotations

from datetime import datetime, timedelta, timezone
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
        return msg.model_copy(deep=True)

    def list_by_status(self, *statuses: str) -> Iterable[EHRMessage]:
        current_tenant = get_current_tenant()
        status_set = set(statuses)
        for msg in self._messages.values():
            if msg.tenant_id != current_tenant:
                continue
            if msg.status not in status_set:
                continue
            yield msg.model_copy(deep=True)

    def get_by_idempotency_key(self, idempotency_key: str) -> Optional[EHRMessage]:
        current_tenant = get_current_tenant()
        message = next(
            (
                message
                for message in self._messages.values()
                if message.tenant_id == current_tenant
                and message.idempotency_key == idempotency_key
            ),
            None,
        )
        return message.model_copy(deep=True) if message else None

    def save(self, message: EHRMessage) -> None:
        now = datetime.utcnow()
        if message.created_at is None:
            message.created_at = now
        message.updated_at = now
        self._messages[message.id] = message.model_copy(deep=True)

    def save_if_absent(self, message: EHRMessage) -> EHRMessage:
        with self._lock:
            existing = self.get_by_idempotency_key(message.idempotency_key)
            if existing is not None:
                return existing
            self.save(message)
            return message

    def claim_due(
        self, *, worker_id: str, now: datetime, limit: int,
        lease_duration: timedelta, max_retries: int,
    ) -> list[EHRMessage]:
        claimed = []
        with self._lock:
            for message in sorted(self._messages.values(), key=lambda item: item.created_at):
                due_failure = (
                    message.status == "failed"
                    and message.retry_count < max_retries
                    and message.next_retry_at is not None
                    and message.next_retry_at <= now
                )
                expired_claim = (
                    message.status == "processing"
                    and message.claim_expires_at is not None
                    and message.claim_expires_at <= now
                    and message.retry_count < max_retries
                )
                if not (due_failure or expired_claim):
                    continue
                message.status = "processing"
                message.claimed_by = worker_id
                message.claim_expires_at = now + lease_duration
                message.updated_at = datetime.now(timezone.utc)
                claimed.append(message.model_copy(deep=True))
                if len(claimed) >= limit:
                    break
        return claimed

    def claim_message(
        self, message_id: UUID, *, worker_id: str, now: datetime,
        lease_duration: timedelta,
    ) -> Optional[EHRMessage]:
        with self._lock:
            message = self._messages.get(message_id)
            if message is None or message.tenant_id != get_current_tenant():
                return None
            live_other_claim = (
                message.status == "processing"
                and message.claimed_by != worker_id
                and message.claim_expires_at is not None
                and message.claim_expires_at > now
            )
            if message.status == "delivered" or live_other_claim:
                return None
            message.status = "processing"
            message.claimed_by = worker_id
            message.claim_expires_at = now + lease_duration
            message.updated_at = now
            return message.model_copy(deep=True)

    def renew_claim(
        self, message_id: UUID, *, worker_id: str, expires_at: datetime,
    ) -> bool:
        with self._lock:
            message = self._messages.get(message_id)
            if (
                message is None or message.status != "processing"
                or message.claimed_by != worker_id
            ):
                return False
            message.claim_expires_at = expires_at
            message.updated_at = datetime.now(timezone.utc)
            return True

    def save_if_claimed(self, message: EHRMessage, *, worker_id: str) -> bool:
        with self._lock:
            current = self._messages.get(message.id)
            if (
                current is None or current.status != "processing"
                or current.claimed_by != worker_id
            ):
                return False
            message.updated_at = datetime.now(timezone.utc)
            self._messages[message.id] = message
            return True


ehr_connection_repository = RepositoryProxy(InMemoryEHRConnectionRepository())
ehr_message_repository = RepositoryProxy(InMemoryEHRMessageRepository())
