from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional
from uuid import UUID, uuid4

from src.backend.tenancy import get_current_tenant


@dataclass
class CultureFeedbackItem:
    id: UUID
    created_at: datetime
    tenant_id: str

    encounter_id: Optional[UUID]
    job_id: Optional[UUID]
    note_id: Optional[UUID]

    community_group: Optional[str]
    indigenous_affiliation: Optional[str]

    issue_type: str
    comment: str


class CultureFeedbackService:
    """In-memory storage for culture/cultural-safety feedback items.

    This is intentionally simple and per-process only. For a real deployment,
    this should be backed by a database table or external system with access
    controls and review workflows.
    """

    def __init__(self) -> None:
        self._items: Dict[UUID, CultureFeedbackItem] = {}

    def submit_feedback(
        self,
        *,
        encounter_id: Optional[UUID] = None,
        job_id: Optional[UUID] = None,
        note_id: Optional[UUID] = None,
        community_group: Optional[str] = None,
        indigenous_affiliation: Optional[str] = None,
        issue_type: str,
        comment: str,
    ) -> CultureFeedbackItem:
        tenant_id = get_current_tenant()
        item_id = uuid4()
        now = datetime.now(timezone.utc)

        item = CultureFeedbackItem(
            id=item_id,
            created_at=now,
            tenant_id=tenant_id,
            encounter_id=encounter_id,
            job_id=job_id,
            note_id=note_id,
            community_group=community_group,
            indigenous_affiliation=indigenous_affiliation,
            issue_type=issue_type,
            comment=comment,
        )
        self._items[item_id] = item
        return item

    def list_for_tenant(self, tenant_id: str | None = None) -> List[CultureFeedbackItem]:
        current = tenant_id or get_current_tenant()
        return [i for i in self._items.values() if i.tenant_id == current]


culture_feedback_service = CultureFeedbackService()
