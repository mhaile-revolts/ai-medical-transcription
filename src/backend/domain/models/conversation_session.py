from __future__ import annotations

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class ConversationSession(BaseModel):
    """Represents a logical conversation/encounter spanning one or more transcripts."""

    id: UUID
    created_at: datetime
    ended_at: Optional[datetime] = None
    title: Optional[str] = None
    transcription_job_ids: List[UUID] = Field(default_factory=list)

    # Logical tenant/organization this session belongs to.
    tenant_id: str
