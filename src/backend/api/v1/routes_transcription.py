from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, HttpUrl

from src.backend.domain.models.transcription_job import TranscriptJob
from src.backend.services.transcription.service import transcription_service
from src.backend.services.nlp.service import nlp_service
from src.backend.domain.nlp.models import ClinicalEntities, SOAPNote
from src.backend.domain.nlp.coding_models import CodeAssignment, BillingRiskSummary
from src.backend.domain.nlp.models import TranscriptSegment
from src.backend.services.nlp.coding_orchestrator import coding_orchestrator
from src.backend.services.nlp.relevance_classifier import relevance_classifier
from src.backend.services.nlp.emotion_classifier import emotion_classifier
from src.backend.services.ehr.service import demo_fhir_exporter
from src.backend.services.encounters.service import encounter_service
from src.backend.services.audit.service import audit_service
from src.backend.security import get_api_key
from src.backend.tenancy import tenant_dependency

router = APIRouter(
    prefix="/transcriptions",
    tags=["transcription"],
    dependencies=[Depends(get_api_key), Depends(tenant_dependency)],
)


class CreateTranscriptionRequest(BaseModel):
    audio_url: HttpUrl | str
    language_code: Optional[str] = None  # Source language
    target_language: Optional[str] = None  # Desired translation target


@router.post("/", response_model=TranscriptJob, status_code=status.HTTP_201_CREATED)
async def create_transcription(request: CreateTranscriptionRequest) -> TranscriptJob:
    """Submit a new transcription job from an existing audio URL.

    In this initial prototype, jobs are processed synchronously and stored in
    memory. A future version will support uploaded audio blobs and background
    processing.
    """

    job = transcription_service.create_job(
        audio_url=str(request.audio_url),
        language_code=request.language_code,
        target_language=request.target_language,
    )

    audit_service.log_event(
        action="create_transcription",
        resource_type="transcription_job",
        resource_id=str(job.id),
        extra={"async": False},
    )

    return job


@router.get("/{job_id}", response_model=TranscriptJob)
async def get_transcription(job_id: UUID) -> TranscriptJob:
    job = transcription_service.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transcription job not found")

    audit_service.log_event(
        action="get_transcription",
        resource_type="transcription_job",
        resource_id=str(job_id),
    )

    return job


class AnalyzeTranscriptionResponse(BaseModel):
    entities: ClinicalEntities
    soap_note: SOAPNote
    codes: list[CodeAssignment] = []
    billing_risk: BillingRiskSummary | None = None
    segments: list[TranscriptSegment] = []


class FHIRExportResponse(BaseModel):
    bundle: dict


@router.post("/{job_id}/analyze", response_model=AnalyzeTranscriptionResponse)
async def analyze_transcription(job_id: UUID) -> AnalyzeTranscriptionResponse:
    """Run clinical NLP pipeline on an existing transcription job.

    Uses the job's result_text as input. The job must be COMPLETED.
    """

    job = transcription_service.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transcription job not found")
    if not job.result_text:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Transcription result not available yet")

    entities, soap = nlp_service.extract_and_summarize(job.result_text)
    codes, billing_risk = coding_orchestrator.assign_codes(entities, soap)
    segments = relevance_classifier.classify_segments(job.result_text)
    segments = emotion_classifier.classify_segments(segments)

    # Best-effort: attach or update a clinical note for any encounter that
    # already references this transcription job.
    try:
        encounter = encounter_service.find_encounter_for_job(job_id)
        if encounter is not None:
            encounter_service.upsert_note_from_soap(
                encounter_id=encounter.id,
                subjective=soap.subjective.text,
                objective=soap.objective.text,
                assessment=soap.assessment.text,
                plan=soap.plan.text,
                editor_id=None,
                finalize=False,
            )
    except Exception:  # pragma: no cover - defensive around early wiring
        pass

    audit_service.log_event(
        action="analyze_transcription",
        resource_type="transcription_job",
        resource_id=str(job_id),
        extra={
            "has_codes": bool(codes),
            "billing_risk_level": billing_risk.level.value if billing_risk else None,
            "segment_count": len(segments),
        },
    )

    return AnalyzeTranscriptionResponse(
        entities=entities,
        soap_note=soap,
        codes=codes,
        billing_risk=billing_risk,
        segments=segments,
    )


@router.post("/{job_id}/export/fhir", response_model=FHIRExportResponse)
async def export_transcription_fhir(job_id: UUID) -> FHIRExportResponse:
    """Export a completed transcription job as a demo FHIR Bundle.

    This reuses the NLP pipeline internally, then maps the results into a
    lightweight FHIR-like document bundle.
    """

    job = transcription_service.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transcription job not found")
    if not job.result_text:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Transcription result not available yet")

    entities, soap = nlp_service.extract_and_summarize(job.result_text)
    bundle = demo_fhir_exporter.build_fhir_bundle(job_id=job_id, entities=entities, soap_note=soap)

    audit_service.log_event(
        action="export_transcription_fhir",
        resource_type="transcription_job",
        resource_id=str(job_id),
        extra={"bundle_entry_count": len(bundle.get("entry", []))},
    )

    return FHIRExportResponse(bundle=bundle)
