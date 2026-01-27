from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, HttpUrl


class EHRConnection(BaseModel):
    """Represents an external EHR/FHIR endpoint for a given tenant.

    This model is intentionally vendor-agnostic. It captures where to send
    FHIR/HL7 payloads and how to authenticate, leaving vendor-specific details
    to transport/adapters.
    """

    id: UUID
    tenant_id: str
    name: str
    base_url: Optional[HttpUrl] = None
    auth_type: Literal["none", "api_key", "oauth2_client_credentials"] = "none"
    # Opaque, minimally-typed auth configuration. For example:
    # {"api_key_header": "Authorization", "api_key_env": "HOSPITAL_A_FHIR_KEY"}
    # or OAuth2 client credentials metadata.
    auth_config: Dict[str, Any] = {}
    # High-level capabilities enabled for this connection
    # e.g. ["encounter_export", "note_export", "patient_sync"].
    supported_capabilities: List[str] = []
    is_active: bool = True
    created_at: datetime
    updated_at: datetime
