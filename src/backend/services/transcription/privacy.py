from __future__ import annotations

from fastapi import HTTPException, status

from src.backend.config import settings
from src.backend.domain.models.clinical_encounter import ClinicalEncounter
from src.backend.services.encounters.service import encounter_service


ELEVENLABS_CONSENT_VERSION = "mobile-recording-consent-elevenlabs-v1"
DEFAULT_RECORDING_CONSENT_VERSION = "mobile-recording-consent-v1"


def external_asr_consent_version() -> str | None:
    if settings.asr_backend.lower() == "elevenlabs":
        return ELEVENLABS_CONSENT_VERSION
    return None


def require_external_asr_consent(encounter: ClinicalEncounter) -> None:
    """Fail closed unless the confirmed encounter consent covers this provider."""
    required_version = external_asr_consent_version()
    if required_version is None:
        return
    if not encounter_service.is_confirmed_recording_allowed(encounter):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Encounter requires active confirmation and unrevoked recording consent",
        )
    if encounter.consent_version != required_version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Recording consent does not cover the configured transcription provider; confirm consent again",
        )
