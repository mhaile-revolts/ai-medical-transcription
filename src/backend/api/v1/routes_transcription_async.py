from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, status
from pydantic import BaseModel, HttpUrl

from src.backend.domain.models.transcription_job import TranscriptJob
from src.backend.services.transcription.service import transcription_service
from src.backend.services.audit.service import audit_service
from src.backend.security import get_api_key
from src.backend.tenancy import tenant_dependency

router = APIRouter(
    prefix="/transcriptions",
    tags=["transcription-async"],
    dependencies=[Depends(get_api_key), Depends(tenant_dependency)],
)


class CreateAsyncTranscriptionRequest(BaseModel):
    audio_url: HttpUrl | str
    language_code: Optional[str] = None
    target_language: Optional[str] = None


@router.post("/async", response_model=TranscriptJob, status_code=status.HTTP_202_ACCEPTED)
async def create_transcription_async(
    request: CreateAsyncTranscriptionRequest,
    background_tasks: BackgroundTasks,
) -> TranscriptJob:
    """Create a transcription job that is processed in the background.

    Returns a job in PENDING state; clients should poll the job resource until
    its status becomes COMPLETED or FAILED.
    """

    job = transcription_service.enqueue_job(
        audio_url=str(request.audio_url),
        language_code=request.language_code,
        target_language=request.target_language,
    )
    background_tasks.add_task(transcription_service.process_job, job.id)

    audit_service.log_event(
        action="enqueue_transcription",
        resource_type="transcription_job",
        resource_id=str(job.id),
        extra={"async": True},
    )

    return job
