from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from src.backend.domain.models.patient_metadata import PatientMetadata
from src.backend.domain.nlp.models import ClinicalEntities, SOAPNote
from src.backend.domain.nlp.coding_models import CodeAssignment, BillingRiskSummary
from src.backend.services.nlp.service import nlp_service
from src.backend.services.nlp.coding_orchestrator import coding_orchestrator
from src.backend.services.nlp.backends import UmlsCodingBackend
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
    codes: list[CodeAssignment] = []
    billing_risk: BillingRiskSummary | None = None


class CodingDebugRequest(BaseModel):
    text: str


class CodingDebugMatch(BaseModel):
    name: str
    code: str | None = None
    system: str | None = None
    similarity: float


class CodingDebugResponse(BaseModel):
    best_match: CodingDebugMatch | None = None


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze_transcript(payload: AnalyzeRequest) -> AnalyzeResponse:
    """Run clinical NLP pipeline on a transcript string with coding support."""

    pm = payload.patient_metadata.model_dump() if payload.patient_metadata else None
    entities, soap = nlp_service.extract_and_summarize(
        payload.transcript,
        patient_metadata=pm,
    )

    codes, billing_risk = coding_orchestrator.assign_codes(entities, soap)

    audit_service.log_event(
        action="analyze_transcript",
        resource_type="nlp_transcript",
        resource_id=None,
        extra={
            "has_codes": bool(codes),
            "billing_risk_level": billing_risk.level.value if billing_risk else None,
        },
    )

    return AnalyzeResponse(
        entities=entities,
        soap_note=soap,
        codes=codes,
        billing_risk=billing_risk,
    )


@router.post("/debug/code", response_model=CodingDebugResponse)
async def debug_code(payload: CodingDebugRequest) -> CodingDebugResponse:
    """Debug endpoint exposing the best terminology match for free text.

    This is intended for operators and internal tools to verify how the
    configured UMLS/terminology concepts file is being used for coding.
    """

    backend = UmlsCodingBackend()
    concept, score = backend.debug_best_match(payload.text)

    best: CodingDebugMatch | None = None
    if concept is not None:
        best = CodingDebugMatch(
            name=str(concept.get("name", "")),
            code=concept.get("code"),
            system=concept.get("system"),
            similarity=score,
        )

    audit_service.log_event(
        action="debug_code",
        resource_type="nlp_debug",
        resource_id=None,
        extra={
            "has_match": bool(best),
            "similarity": score if best is not None else None,
        },
    )

    return CodingDebugResponse(best_match=best)
