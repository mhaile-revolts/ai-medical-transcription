from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, status
from pydantic import BaseModel, HttpUrl

from src.backend.domain.models.transcription_job import TranscriptJob
from src.backend.services.transcription.service import transcription_service
from src.backend.services.audit.service import audit_service
from src.backend.security import get_api_key, get_current_user, ensure_can_edit_encounter, ensure_can_view_encounter
from src.backend.domain.models.user import User
from src.backend.services.encounters.service import encounter_service
from src.backend.config import settings
from fastapi import HTTPException
from uuid import UUID
from src.backend.tenancy import tenant_dependency
from src.backend.services.transcription.privacy import (
    external_asr_consent_version,
    require_external_asr_consent,
)

router = APIRouter(
    prefix="/transcriptions",
    tags=["transcription-async"],
    dependencies=[Depends(get_api_key), Depends(tenant_dependency)],
)


class CreateAsyncTranscriptionRequest(BaseModel):
    audio_url: HttpUrl | str
    encounter_id: Optional[UUID] = None
    language_code: Optional[str] = None
    target_language: Optional[str] = None


@router.post("/async", response_model=TranscriptJob, status_code=status.HTTP_202_ACCEPTED)
async def create_transcription_async(
    request: CreateAsyncTranscriptionRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
) -> TranscriptJob:
    """Create a transcription job that is processed in the background.

    Returns a job in PENDING state; clients should poll the job resource until
    its status becomes COMPLETED or FAILED.
    """

    if settings.app_env not in {"development", "test"} and request.encounter_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="encounter_id is required for PHI transcription jobs",
        )
    encounter = None
    if request.encounter_id is not None:
        encounter = encounter_service.get_encounter(request.encounter_id)
        if encounter is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Encounter not found")
        ensure_can_view_encounter(current_user, encounter.clinician_id)
        if external_asr_consent_version():
            ensure_can_edit_encounter(current_user, encounter.clinician_id)
            require_external_asr_consent(encounter)
    elif external_asr_consent_version():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="External transcription requires a confirmed encounter and provider-specific consent",
        )
    job = transcription_service.enqueue_job(
        audio_url=str(request.audio_url),
        language_code=request.language_code,
        target_language=request.target_language,
    )
    if encounter is not None:
        encounter_service.attach_job(encounter_id=encounter.id, job_id=job.id)
    background_tasks.add_task(transcription_service.process_job, job.id)

    audit_service.log_event(
        action="enqueue_transcription",
        resource_type="transcription_job",
        resource_id=str(job.id),
        extra={"async": True},
    )

    return job
