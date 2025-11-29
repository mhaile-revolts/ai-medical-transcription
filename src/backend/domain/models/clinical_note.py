from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class ClinicalNoteSection(BaseModel):
    text: str


class ClinicalNote(BaseModel):
    """Represents a clinical note (typically SOAP-style) for an encounter.

    For the pilot MVP we keep this intentionally simple: one active note per
    encounter with optional finalized flag and basic timestamps.
    """

    id: UUID
    encounter_id: UUID
    created_at: datetime
    updated_at: datetime
    created_by: Optional[str] = None
    last_edited_by: Optional[str] = None
    is_finalized: bool = False

    # Optional human review metadata
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    review_comment: Optional[str] = None

    subjective: ClinicalNoteSection
    objective: ClinicalNoteSection
    assessment: ClinicalNoteSection
    plan: ClinicalNoteSection

    # Logical tenant/organization this note belongs to. Should always match the
    # tenant_id of its parent encounter.
    tenant_id: str
