from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, HttpUrl


class TranscriptJobStatus(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class TranscriptJob(BaseModel):
    id: UUID
    created_at: datetime
    status: TranscriptJobStatus
    audio_url: HttpUrl | str
    language_code: Optional[str] = None  # Source language (e.g., "en-US")
    target_language: Optional[str] = None  # Desired translation target (e.g., "es-ES")
    result_text: Optional[str] = None  # Transcript in source language
    translated_text: Optional[str] = None  # Transcript translated to target_language, if requested

    # Logical tenant/organization this job belongs to.
    tenant_id: str
