from __future__ import annotations

from datetime import datetime
from typing import Dict, Optional
from uuid import UUID, uuid4

from src.backend.domain.models.transcription_job import TranscriptJob, TranscriptJobStatus
from src.backend.tenancy import get_current_tenant
from src.backend.services.transcription.backends import (
    ASRBackend,
    TranslationBackend,
    demo_asr_backend,
    demo_translation_backend,
    get_asr_backend_from_env,
    get_translation_backend_from_env,
)


class InMemoryTranscriptionService:
    """Simple in-memory implementation of a transcription job service.

    This is intended for early prototyping and tests only. It will later be
    replaced by a persistence-backed implementation that orchestrates real ASR
    and NLP in background workers.
    """

    def __init__(
        self,
        *,
        asr_backend: Optional[ASRBackend] = None,
        translation_backend: Optional[TranslationBackend] = None,
    ) -> None:
        self._jobs: Dict[UUID, TranscriptJob] = {}
        self._asr_backend = asr_backend or get_asr_backend_from_env()
        self._translation_backend = translation_backend or get_translation_backend_from_env()

    def create_job(
        self,
        *,
        audio_url: str,
        language_code: Optional[str] = None,
        target_language: Optional[str] = None,
    ) -> TranscriptJob:
        """Create and immediately process a transcription job synchronously.

        This is convenient for tests and for simple, low-volume use cases.
        """

        job_id = self.enqueue_job(
            audio_url=audio_url,
            language_code=language_code,
            target_language=target_language,
        ).id
        return self._run_job(job_id)

    def enqueue_job(
        self,
        *,
        audio_url: str,
        language_code: Optional[str] = None,
        target_language: Optional[str] = None,
    ) -> TranscriptJob:
        """Create a new transcription job but leave it in PENDING state.

        Intended to be used with a background task or worker that later calls
        ``process_job``.
        """

        job_id = uuid4()
        job = TranscriptJob(
            id=job_id,
            created_at=datetime.utcnow(),
            status=TranscriptJobStatus.PENDING,
            audio_url=audio_url,
            language_code=language_code,
            target_language=target_language,
            result_text=None,
            translated_text=None,
            tenant_id=get_current_tenant(),
        )
        self._jobs[job_id] = job
        return job

    def process_job(self, job_id: UUID) -> TranscriptJob:
        """Run the transcription pipeline for an existing job.

        Safe to be called from FastAPI BackgroundTasks or a worker process.
        """

        return self._run_job(job_id)

    def _run_job(self, job_id: UUID) -> TranscriptJob:
        job = self._jobs[job_id]
        job.status = TranscriptJobStatus.PROCESSING

        base_text = self._asr_backend.transcribe(
            audio_url=str(job.audio_url),
            language_code=job.language_code,
        )
        translated_text = None
        if job.target_language:
            translated_text = self._translation_backend.translate(
                text=base_text,
                target_language=job.target_language,
                source_language=job.language_code,
            )

        job.result_text = base_text
        job.translated_text = translated_text
        job.status = TranscriptJobStatus.COMPLETED
        self._jobs[job_id] = job
        return job

    def get_job(self, job_id: UUID) -> Optional[TranscriptJob]:
        job = self._jobs.get(job_id)
        if job is None:
            return None
        if job.tenant_id != get_current_tenant():
            return None
        return job


# Default singleton instance for simple use in routers during early stages.
transcription_service = InMemoryTranscriptionService()
