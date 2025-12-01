from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from src.backend.domain.models.patient_metadata import PatientMetadata
from src.backend.domain.nlp.models import ClinicalEntities, SOAPNote
from src.backend.services.nlp.service import nlp_service
from src.backend.services.audit.service import audit_service
from src.backend.security import get_api_key

router = APIRouter(
    prefix="/nlp",
    tags=["nlp"],
    dependencies=[Depends(get_api_key)],
)


class AnalyzeRequest(BaseModel):
    transcript: str
    patient_metadata: PatientMetadata | None = None


class AnalyzeResponse(BaseModel):
    entities: ClinicalEntities
    soap_note: SOAPNote


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze_transcript(payload: AnalyzeRequest) -> AnalyzeResponse:
    """Run demo clinical NLP pipeline on a transcript string."""

    pm = payload.patient_metadata.model_dump() if payload.patient_metadata else None
    entities, soap = nlp_service.extract_and_summarize(
        payload.transcript,
        patient_metadata=pm,
    )

    audit_service.log_event(
        action="analyze_transcript",
        resource_type="nlp_transcript",
        resource_id=None,
    )

    return AnalyzeResponse(entities=entities, soap_note=soap)
