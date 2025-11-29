from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class TimelineEventType(str, Enum):
    ENCOUNTER = "ENCOUNTER"
    DIAGNOSIS = "DIAGNOSIS"
    MEDICATION = "MEDICATION"
    SYMPTOM = "SYMPTOM"
    LAB_REFERENCE = "LAB_REFERENCE"


class TimelineEvent(BaseModel):
    type: TimelineEventType
    timestamp: datetime
    encounter_id: Optional[UUID] = None
    label: str
    details: Optional[str] = None
