from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Iterable, Optional
from uuid import UUID

from src.backend.domain.models.ehr_connection import EHRConnection
from src.backend.domain.models.ehr_message import EHRMessage


class EHRConnectionRepository(ABC):
    """Abstract repository for EHRConnection records.

    Implementations must enforce tenant scoping (typically via get_current_tenant).
    """

    @abstractmethod
    def get(self, connection_id: UUID) -> Optional[EHRConnection]:
        raise NotImplementedError

    @abstractmethod
    def list_active(self) -> Iterable[EHRConnection]:
        """List active connections for the current tenant."""

    @abstractmethod
    def save(self, connection: EHRConnection) -> None:
        raise NotImplementedError


class EHRMessageRepository(ABC):
    """Abstract repository for EHRMessage tracking.

    Used for auditing, retries, and status inspection.
    """

    @abstractmethod
    def get(self, message_id: UUID) -> Optional[EHRMessage]:
        raise NotImplementedError

    @abstractmethod
    def list_by_status(self, *statuses: str) -> Iterable[EHRMessage]:
        """List messages for the current tenant filtered by status."""

    @abstractmethod
    def get_by_idempotency_key(self, idempotency_key: str) -> Optional[EHRMessage]:
        raise NotImplementedError

    @abstractmethod
    def save_if_absent(self, message: EHRMessage) -> EHRMessage:
        """Atomically persist a new idempotency key, or return its existing message."""
        raise NotImplementedError

    @abstractmethod
    def save(self, message: EHRMessage) -> None:
        raise NotImplementedError

    @abstractmethod
    def claim_due(
        self,
        *,
        worker_id: str,
        now: datetime,
        limit: int,
        lease_duration: timedelta,
        max_retries: int,
    ) -> list[EHRMessage]:
        """Atomically lease due messages across tenants for a background worker."""
        raise NotImplementedError

    @abstractmethod
    def claim_message(
        self, message_id: UUID, *, worker_id: str, now: datetime,
        lease_duration: timedelta,
    ) -> Optional[EHRMessage]:
        """Reserve one non-delivered message unless another live claim owns it."""
        raise NotImplementedError

    @abstractmethod
    def renew_claim(
        self, message_id: UUID, *, worker_id: str, expires_at: datetime,
    ) -> bool:
        raise NotImplementedError

    @abstractmethod
    def save_if_claimed(self, message: EHRMessage, *, worker_id: str) -> bool:
        """Persist an outcome only when the caller still owns the processing claim."""
        raise NotImplementedError
