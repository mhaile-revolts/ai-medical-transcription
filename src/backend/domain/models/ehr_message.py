from __future__ import annotations

from datetime import datetime
from typing import Dict, Literal, Optional
from uuid import UUID

from pydantic import BaseModel


class EHRMessage(BaseModel):
    """Tracks an outbound or inbound EHR payload for auditing and retries.

    Payloads are typically FHIR JSON Bundles or resources, but this model is
    intentionally generic enough to support HL7 v2 or other serialized formats
    represented as JSON.
    """

    id: UUID
    tenant_id: str
    connection_id: UUID
    resource_type: str
    payload: Dict
    direction: Literal["outbound", "inbound"] = "outbound"
    status: Literal["pending", "sent", "failed", "acknowledged"] = "pending"
    last_error: Optional[str] = None
    related_encounter_id: Optional[UUID] = None
    related_note_id: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime
    retry_count: int = 0
