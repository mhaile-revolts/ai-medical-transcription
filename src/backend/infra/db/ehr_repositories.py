from __future__ import annotations

from abc import ABC, abstractmethod
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
    def save(self, message: EHRMessage) -> None:
        raise NotImplementedError
