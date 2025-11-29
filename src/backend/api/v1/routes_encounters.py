from __future__ import annotations

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from src.backend.domain.models.clinical_encounter import ClinicalEncounter, EncounterStatus
from src.backend.domain.models.clinical_note import ClinicalNote
from src.backend.domain.models.user import User
from src.backend.domain.nlp.decision_support import DecisionSupportSuggestion
from src.backend.services.transcription.service import transcription_service
from src.backend.services.audit.service import audit_service
from src.backend.services.nlp.service import nlp_service
from src.backend.services.nlp.decision_support_service import decision_support_service
from src.backend.security import get_api_key, get_current_user, ensure_can_view_encounter, ensure_can_edit_encounter
from src.backend.infra.db.inmemory import (
    encounter_repository,
    clinical_note_repository,
)
from src.backend.services.encounters.service import encounter_service
from src.backend.tenancy import tenant_dependency


router = APIRouter(
    prefix="/encounters",
    tags=["encounters"],
    dependencies=[Depends(get_api_key), Depends(tenant_dependency)],
)


class EncounterCreateRequest(BaseModel):
    patient_id: Optional[str] = None
    title: Optional[str] = None


class EncounterSummary(BaseModel):
    id: UUID
    created_at: datetime
    clinician_id: Optional[str]
    patient_id: Optional[str]
    status: EncounterStatus
    title: Optional[str] = None


class EncounterDetailResponse(BaseModel):
    encounter: ClinicalEncounter
    jobs: List[dict]
    note: Optional[ClinicalNote] = None


class EncounterNoteUpdateRequest(BaseModel):
    subjective: str
    objective: str
    assessment: str
    plan: str
    finalize: bool = False


class EncounterDecisionSupportResponse(BaseModel):
    suggestions: list[DecisionSupportSuggestion]


class EncounterRegulatedDecisionSupportResponse(BaseModel):
    enabled: bool
    suggestions: list[DecisionSupportSuggestion]


class EncounterFinalizeRequest(BaseModel):
    review_comment: str | None = None


@router.post("/", response_model=ClinicalEncounter, status_code=status.HTTP_201_CREATED)
async def create_encounter(
    payload: EncounterCreateRequest,
    current_user: User = Depends(get_current_user),
) -> ClinicalEncounter:
    encounter = encounter_service.create_encounter(
        clinician_id=str(current_user.id),
        patient_id=payload.patient_id,
        title=payload.title,
    )
    # Persist via repository abstraction for future DB-backed implementations.
    encounter_repository.save(encounter)

    audit_service.log_event(
        action="create_encounter",
        resource_type="clinical_encounter",
        resource_id=str(encounter.id),
        extra={"user_id": str(current_user.id), "role": current_user.role.value},
    )

    return encounter


@router.get("/{encounter_id}", response_model=EncounterDetailResponse)
async def get_encounter_detail(
    encounter_id: UUID,
    current_user: User = Depends(get_current_user),
) -> EncounterDetailResponse:
    encounter = encounter_repository.get(encounter_id)
    if encounter is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Encounter not found")

    ensure_can_view_encounter(current_user, encounter.clinician_id)

    jobs = []
    for job_id in encounter.transcription_job_ids:
        job = transcription_service.get_job(job_id)
        if job is not None:
            jobs.append(job.model_dump())

    note = clinical_note_repository.get_by_encounter(encounter_id)

    audit_service.log_event(
        action="get_encounter",
        resource_type="clinical_encounter",
        resource_id=str(encounter_id),
        extra={"user_id": str(current_user.id), "role": current_user.role.value},
    )

    return EncounterDetailResponse(encounter=encounter, jobs=jobs, note=note)


@router.get("/", response_model=List[EncounterSummary])
async def list_encounters(
    status_filter: Optional[EncounterStatus] = Query(None, alias="status"),
    patient_id: Optional[str] = None,
    own_only: bool = True,
    current_user: User = Depends(get_current_user),
) -> List[EncounterSummary]:
    results: List[EncounterSummary] = []
    # Use repository abstraction to list encounters matching optional filters.
    encounters_iter = encounter_repository.list_by_filters(
        clinician_id=str(current_user.id) if own_only and current_user.role != current_user.role.ADMIN else None,
        patient_id=patient_id,
        status=status_filter,
    )
    for encounter in encounters_iter:
        results.append(
            EncounterSummary(
                id=encounter.id,
                created_at=encounter.created_at,
                clinician_id=encounter.clinician_id,
                patient_id=encounter.patient_id,
                status=encounter.status,
                title=encounter.title,
            )
        )

    audit_service.log_event(
        action="list_encounters",
        resource_type="clinical_encounter",
        resource_id=None,
        extra={"user_id": str(current_user.id), "role": current_user.role.value, "count": len(results)},
    )

    return results


@router.put("/{encounter_id}/note", response_model=ClinicalNote)
async def update_encounter_note(
    encounter_id: UUID,
    payload: EncounterNoteUpdateRequest,
    current_user: User = Depends(get_current_user),
) -> ClinicalNote:
    encounter = encounter_repository.get(encounter_id)
    if encounter is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Encounter not found")

    ensure_can_edit_encounter(current_user, encounter.clinician_id)

    note = encounter_service.upsert_note_from_soap(
        encounter_id=encounter_id,
        subjective=payload.subjective,
        objective=payload.objective,
        assessment=payload.assessment,
        plan=payload.plan,
        editor_id=str(current_user.id),
        finalize=payload.finalize,
    )
    # Persist updated encounter/note via repositories; the in-memory service
    # already mutated its state, so we simply save current objects.
    encounter_repository.save(encounter)
    clinical_note_repository.save(note)

    audit_service.log_event(
        action="update_encounter_note",
        resource_type="clinical_encounter",
        resource_id=str(encounter_id),
        extra={
            "user_id": str(current_user.id),
            "role": current_user.role.value,
            "finalize": payload.finalize,
        },
    )

    return note


@router.post("/{encounter_id}/submit-for-review", response_model=ClinicalEncounter)
async def submit_for_review(
    encounter_id: UUID,
    current_user: User = Depends(get_current_user),
) -> ClinicalEncounter:
    encounter = encounter_repository.get(encounter_id)
    if encounter is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Encounter not found")

    ensure_can_edit_encounter(current_user, encounter.clinician_id)

    if encounter.status in {EncounterStatus.CREATED, EncounterStatus.IN_PROGRESS}:
        encounter.status = EncounterStatus.READY_FOR_REVIEW
        encounter_repository.save(encounter)

    audit_service.log_event(
        action="submit_encounter_for_review",
        resource_type="clinical_encounter",
        resource_id=str(encounter_id),
        extra={
            "user_id": str(current_user.id),
            "role": current_user.role.value,
            "status": encounter.status.value,
        },
    )

    return encounter


@router.post("/{encounter_id}/finalize", response_model=ClinicalNote)
async def finalize_encounter(
    encounter_id: UUID,
    payload: EncounterFinalizeRequest,
    current_user: User = Depends(get_current_user),
) -> ClinicalNote:
    encounter = encounter_repository.get(encounter_id)
    if encounter is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Encounter not found")

    ensure_can_edit_encounter(current_user, encounter.clinician_id)

    note = clinical_note_repository.get_by_encounter(encounter_id)
    if note is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="No note available to finalize")

    from datetime import datetime

    now = datetime.utcnow()
    note.is_finalized = True
    note.reviewed_by = str(current_user.id)
    note.reviewed_at = now
    note.review_comment = payload.review_comment

    clinical_note_repository.save(note)

    encounter.status = EncounterStatus.FINALIZED
    encounter_repository.save(encounter)

    audit_service.log_event(
        action="finalize_encounter",
        resource_type="clinical_encounter",
        resource_id=str(encounter_id),
        extra={
            "user_id": str(current_user.id),
            "role": current_user.role.value,
        },
    )

    return note


@router.post("/{encounter_id}/decision-support", response_model=EncounterDecisionSupportResponse)
async def encounter_decision_support(
    encounter_id: UUID,
    current_user: User = Depends(get_current_user),
) -> EncounterDecisionSupportResponse:
    """Generate advisory decision-support suggestions for an encounter.

    For now this recomputes entities/SOAP from the concatenated job transcripts
    attached to the encounter using the demo NLP pipeline.
    """

    encounter = encounter_repository.get(encounter_id)
    if encounter is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Encounter not found")

    ensure_can_view_encounter(current_user, encounter.clinician_id)

    texts: list[str] = []
    for job_id in encounter.transcription_job_ids:
        job = transcription_service.get_job(job_id)
        if job and job.result_text:
            texts.append(job.result_text)

    if not texts:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No transcription results available for this encounter",
        )

    combined = "\n\n".join(texts)
    entities, soap = nlp_service.extract_and_summarize(combined)
    suggestions = decision_support_service.suggest(entities, soap)

    audit_service.log_event(
        action="encounter_decision_support",
        resource_type="clinical_encounter",
        resource_id=str(encounter_id),
        extra={
            "user_id": str(current_user.id),
            "role": current_user.role.value,
            "suggestion_count": len(suggestions),
        },
    )

    return EncounterDecisionSupportResponse(suggestions=suggestions)


@router.post("/{encounter_id}/decision-support/regulated", response_model=EncounterRegulatedDecisionSupportResponse)
async def encounter_decision_support_regulated(
    encounter_id: UUID,
    current_user: User = Depends(get_current_user),
) -> EncounterRegulatedDecisionSupportResponse:
    """Stub endpoint for a future regulated CDS lane.

    Currently always returns enabled=False and no suggestions to make it clear
    that regulated CDS is not active yet.
    """

    encounter = encounter_repository.get(encounter_id)
    if encounter is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Encounter not found")

    ensure_can_view_encounter(current_user, encounter.clinician_id)

    audit_service.log_event(
        action="encounter_decision_support_regulated",
        resource_type="clinical_encounter",
        resource_id=str(encounter_id),
        extra={
            "user_id": str(current_user.id),
            "role": current_user.role.value,
            "enabled": False,
        },
    )

    return EncounterRegulatedDecisionSupportResponse(enabled=False, suggestions=[])
