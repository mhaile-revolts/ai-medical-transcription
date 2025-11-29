from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class EncounterStatus(str, Enum):
    CREATED = "CREATED"
    IN_PROGRESS = "IN_PROGRESS"
    READY_FOR_REVIEW = "READY_FOR_REVIEW"
    FINALIZED = "FINALIZED"


class ClinicalEncounter(BaseModel):
    """Represents a clinical encounter grouping one or more transcription jobs.

    This is a higher-level construct than a raw transcription job or
    ConversationSession and is intended to model a single visit/interaction for
    a patient with a clinician.
    """

    id: UUID
    created_at: datetime
    clinician_id: Optional[str] = None
    patient_id: Optional[str] = None
    status: EncounterStatus = EncounterStatus.CREATED
    title: Optional[str] = None
    transcription_job_ids: List[UUID] = Field(default_factory=list)
    # Optional assigned scribe (stringified user id) for human-in-the-loop flows.
    assigned_scribe_id: Optional[str] = None
    # Logical tenant/organization this encounter belongs to.
    tenant_id: str
