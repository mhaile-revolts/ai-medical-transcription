from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from src.backend.domain.models.conversation_session import ConversationSession
from src.backend.domain.nlp.models import ClinicalEntities, SOAPNote, TranscriptSegment
from src.backend.domain.nlp.coding_models import CodeAssignment, BillingRiskSummary
from src.backend.domain.models.transcription_job import TranscriptJobStatus
from src.backend.services.conversation.service import conversation_service
from src.backend.services.nlp.service import nlp_service
from src.backend.services.nlp.coding_orchestrator import coding_orchestrator
from src.backend.services.nlp.relevance_classifier import relevance_classifier
from src.backend.services.nlp.emotion_classifier import emotion_classifier
from src.backend.services.transcription.service import transcription_service
from src.backend.services.audit.service import audit_service
from src.backend.security import get_api_key
from src.backend.tenancy import tenant_dependency

router = APIRouter(
    prefix="/sessions",
    tags=["sessions"],
    dependencies=[Depends(get_api_key), Depends(tenant_dependency)],
)


class CreateSessionRequest(BaseModel):
    title: Optional[str] = None


class AttachTranscriptionRequest(BaseModel):
    job_id: UUID


class SessionAnalyzeResponse(BaseModel):
    entities: ClinicalEntities
    soap_note: SOAPNote
    codes: list[CodeAssignment] = []
    billing_risk: BillingRiskSummary | None = None
    segments: list[TranscriptSegment] = []


@router.post("/", response_model=ConversationSession, status_code=status.HTTP_201_CREATED)
async def create_session(payload: CreateSessionRequest) -> ConversationSession:
    session = conversation_service.create_session(title=payload.title)

    audit_service.log_event(
        action="create_session",
        resource_type="conversation_session",
        resource_id=str(session.id),
    )

    return session


@router.get("/{session_id}", response_model=ConversationSession)
async def get_session(session_id: UUID) -> ConversationSession:
    session = conversation_service.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    audit_service.log_event(
        action="get_session",
        resource_type="conversation_session",
        resource_id=str(session_id),
    )

    return session


@router.post("/{session_id}/transcriptions", response_model=ConversationSession)
async def attach_transcription(session_id: UUID, payload: AttachTranscriptionRequest) -> ConversationSession:
    session = conversation_service.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    job = transcription_service.get_job(payload.job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transcription job not found")

    updated = conversation_service.attach_job(session_id=session_id, job_id=payload.job_id)

    audit_service.log_event(
        action="attach_transcription_to_session",
        resource_type="conversation_session",
        resource_id=str(session_id),
        extra={"job_id": str(payload.job_id)},
    )

    return updated


@router.post("/{session_id}/analyze", response_model=SessionAnalyzeResponse)
async def analyze_session(session_id: UUID) -> SessionAnalyzeResponse:
    """Analyze all completed transcription jobs attached to a session.

    Concatenates the text of all COMPLETED jobs (in arbitrary order) and feeds
    it into the NLP pipeline to produce entities and a SOAP note.
    """

    session = conversation_service.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    texts = []
    for job_id in session.transcription_job_ids:
        job = transcription_service.get_job(job_id)
        if job and job.status == TranscriptJobStatus.COMPLETED and job.result_text:
            texts.append(job.result_text)

    if not texts:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No completed transcription results available for this session",
        )

    combined = "\n\n".join(texts)
    entities, soap = nlp_service.extract_and_summarize(combined)
    codes, billing_risk = coding_orchestrator.assign_codes(entities, soap)
    segments = relevance_classifier.classify_segments(combined)
    segments = emotion_classifier.classify_segments(segments)

    audit_service.log_event(
        action="analyze_session",
        resource_type="conversation_session",
        resource_id=str(session_id),
        extra={
            "job_count": len(texts),
            "has_codes": bool(codes),
            "billing_risk_level": billing_risk.level.value if billing_risk else None,
            "segment_count": len(segments),
        },
    )

    return SessionAnalyzeResponse(
        entities=entities,
        soap_note=soap,
        codes=codes,
        billing_risk=billing_risk,
        segments=segments,
    )
