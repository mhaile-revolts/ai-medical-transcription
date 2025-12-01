from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel


class PatientMetadata(BaseModel):
    """Lightweight, request-scoped view of patient cultural/consent metadata.

    This is intentionally not a persisted patient record; it is meant to carry
    self-reported fields and flags into NLP/CDS pipelines without forcing a
    specific EHR schema.
    """

    cultural_identity: Optional[List[str]] = None
    indigenous_affiliation: Optional[str] = None
    language_preferences: Optional[List[str]] = None

    consent_cultural_ai: Optional[bool] = None
    consent_data_training: Optional[bool] = None

    # Optional contextual hints for risk engines (non-identifying):
    region: Optional[str] = None          # e.g. "malaria_endemic_east_africa"
    environment: Optional[str] = None     # e.g. "outdoor_pastoralist"
    has_historical_trauma_documented: Optional[bool] = None
