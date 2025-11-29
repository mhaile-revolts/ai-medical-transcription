from __future__ import annotations

from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from src.backend.domain.models.clinical_encounter import ClinicalEncounter, EncounterStatus
from src.backend.domain.models.clinical_note import ClinicalNote
from src.backend.domain.models.user import User
from src.backend.services.encounters.service import encounter_service
from src.backend.infra.db.inmemory import encounter_repository, clinical_note_repository
from src.backend.services.transcription.service import transcription_service
from src.backend.services.audit.service import audit_service
from src.backend.security import (
    get_api_key,
    get_current_user,
    ensure_is_scribe_or_admin,
)
from src.backend.tenancy import tenant_dependency


router = APIRouter(
    prefix="/scribe",
    tags=["scribe"],
    dependencies=[Depends(get_api_key), Depends(tenant_dependency)],
)


class ScribeEncounterSummary(BaseModel):
    id: UUID
    created_at: str
    clinician_id: str | None
    patient_id: str | None
    title: str | None
    assigned_scribe_id: str | None
    status: EncounterStatus


class ScribeEncounterDetail(BaseModel):
    encounter: ClinicalEncounter
    jobs: List[dict]
    note: ClinicalNote | None = None


class ScribeUpdateNoteRequest(BaseModel):
    subjective: str
    objective: str
    assessment: str
    plan: str


@router.get("/queue", response_model=List[ScribeEncounterSummary])
async def list_scribe_queue(
    current_user: User = Depends(get_current_user),
) -> List[ScribeEncounterSummary]:
    """List encounters that are good candidates for scribe review.

    For now this returns encounters in the current tenant that:
    - are not FINALIZED, and
    - do not yet have a note attached.
    """

    ensure_is_scribe_or_admin(current_user)

    summaries: List[ScribeEncounterSummary] = []
    for enc in encounter_repository.list_by_filters():
        if enc.status == EncounterStatus.FINALIZED:
            continue
        note = clinical_note_repository.get_by_encounter(enc.id)
        if note is not None:
            continue

        summaries.append(
            ScribeEncounterSummary(
                id=enc.id,
                created_at=enc.created_at.isoformat(),
                clinician_id=enc.clinician_id,
                patient_id=enc.patient_id,
                title=enc.title,
                assigned_scribe_id=enc.assigned_scribe_id,
                status=enc.status,
            )
        )

    audit_service.log_event(
        action="scribe_queue_list",
        resource_type="clinical_encounter",
        extra={"user_id": str(current_user.id), "count": len(summaries)},
    )

    return summaries


@router.post("/queue/{encounter_id}/claim", response_model=ClinicalEncounter)
async def claim_encounter_for_scribing(
    encounter_id: UUID,
    current_user: User = Depends(get_current_user),
) -> ClinicalEncounter:
    """Assign the current scribe to an encounter if it is unclaimed.

    This does not modify clinical content; it only sets `assigned_scribe_id`.
    """

    ensure_is_scribe_or_admin(current_user)

    encounter = encounter_repository.get(encounter_id)
    if encounter is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Encounter not found")

    if encounter.assigned_scribe_id is None:
        encounter.assigned_scribe_id = str(current_user.id)
        encounter_repository.save(encounter)

    audit_service.log_event(
        action="scribe_claim_encounter",
        resource_type="clinical_encounter",
        resource_id=str(encounter_id),
        extra={"user_id": str(current_user.id)},
    )

    return encounter


@router.get("/encounters/{encounter_id}", response_model=ScribeEncounterDetail)
async def get_scribe_encounter_detail(
    encounter_id: UUID,
    current_user: User = Depends(get_current_user),
) -> ScribeEncounterDetail:
    """Return encounter, jobs, and note for scribe review/editing."""

    ensure_is_scribe_or_admin(current_user)

    encounter = encounter_repository.get(encounter_id)
    if encounter is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Encounter not found")

    jobs: List[dict] = []
    for job_id in encounter.transcription_job_ids:
        job = transcription_service.get_job(job_id)
        if job is not None:
            jobs.append(job.model_dump())

    note = clinical_note_repository.get_by_encounter(encounter_id)

    audit_service.log_event(
        action="scribe_get_encounter",
        resource_type="clinical_encounter",
        resource_id=str(encounter_id),
        extra={"user_id": str(current_user.id)},
    )

    return ScribeEncounterDetail(encounter=encounter, jobs=jobs, note=note)


@router.put("/encounters/{encounter_id}/note", response_model=ClinicalNote)
async def scribe_update_note(
    encounter_id: UUID,
    payload: ScribeUpdateNoteRequest,
    current_user: User = Depends(get_current_user),
) -> ClinicalNote:
    """Create or update a note for an encounter as a scribe.

    This uses the same underlying encounter service as clinician edits but does
    not finalize the encounter.
    """

    ensure_is_scribe_or_admin(current_user)

    encounter = encounter_repository.get(encounter_id)
    if encounter is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Encounter not found")

    note = encounter_service.upsert_note_from_soap(
        encounter_id=encounter_id,
        subjective=payload.subjective,
        objective=payload.objective,
        assessment=payload.assessment,
        plan=payload.plan,
        editor_id=str(current_user.id),
        finalize=False,
    )

    encounter_repository.save(encounter)
    clinical_note_repository.save(note)

    audit_service.log_event(
        action="scribe_update_note",
        resource_type="clinical_encounter",
        resource_id=str(encounter_id),
        extra={"user_id": str(current_user.id)},
    )

    return note