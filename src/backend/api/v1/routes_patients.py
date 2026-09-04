from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status

from src.backend.domain.models.patient_timeline import TimelineEvent
from src.backend.domain.models.user import User, UserRole
from src.backend.infra.db.inmemory import (
    clinical_note_repository,
    encounter_repository,
    transcription_job_repository,
)
from src.backend.security import get_api_key, get_current_user, ensure_is_admin
from src.backend.tenancy import tenant_dependency
from src.backend.services.patients.summary_service import patient_summary_service
from src.backend.services.audit.service import audit_service
from src.backend.config import settings


router = APIRouter(
    prefix="/patients",
    tags=["patients"],
    dependencies=[Depends(get_api_key), Depends(tenant_dependency)],
)


@router.get("/{patient_id}/timeline", response_model=List[TimelineEvent])
async def get_patient_timeline(
    patient_id: str, current_user: User = Depends(get_current_user)
) -> List[TimelineEvent]:
    encounters = list(encounter_repository.list_by_filters(patient_id=patient_id))
    if current_user.role != UserRole.ADMIN and not any(
        encounter.clinician_id == str(current_user.id) for encounter in encounters
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to view this patient")
    audit_service.log_event(
        action="get_patient_timeline",
        resource_type="patient",
        resource_id=patient_id,
        extra={"user_id": str(current_user.id), "role": current_user.role.value},
    )
    return patient_summary_service.build_timeline(patient_id)


@router.delete("/{patient_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_patient_data(
    patient_id: str, current_user: User = Depends(get_current_user)
) -> None:
    """Tenant-scoped deletion of active PHI; immutable audit records are retained."""
    ensure_is_admin(current_user)
    encounters = list(encounter_repository.list_by_filters(patient_id=patient_id))
    from src.backend.infra.storage import audio as audio_module

    for encounter in encounters:
        for job_id in encounter.transcription_job_ids:
            job = transcription_job_repository.get(job_id)
            if job is not None:
                audio_module.audio_storage_backend.delete_file(str(job.audio_url))
                transcription_job_repository.delete(job_id)
        clinical_note_repository.delete_by_encounter(encounter.id)
        encounter_repository.delete(encounter.id)
    audit_service.log_event(
        action="delete_patient_data",
        resource_type="patient",
        resource_id=patient_id,
        extra={"user_id": str(current_user.id), "role": current_user.role.value, "count": len(encounters)},
    )


@router.post("/retention/purge")
async def purge_expired_phi(current_user: User = Depends(get_current_user)) -> dict[str, int]:
    """Run the tenant-scoped active-PHI retention policy; audit records are excluded."""
    ensure_is_admin(current_user)
    now = datetime.now(timezone.utc)
    audio_cutoff = now - timedelta(days=settings.phi_audio_retention_days)
    transcript_cutoff = now - timedelta(days=settings.phi_transcript_retention_days)
    from src.backend.infra.storage import audio as audio_module

    audio_deleted = 0
    records_deleted = 0
    for encounter in list(encounter_repository.list_by_filters()):
        remaining_jobs = []
        for job_id in encounter.transcription_job_ids:
            job = transcription_job_repository.get(job_id)
            if job is None:
                continue
            created_at = job.created_at
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            if created_at < audio_cutoff and str(job.audio_url):
                audio_module.audio_storage_backend.delete_file(str(job.audio_url))
                audio_deleted += 1
            if created_at < transcript_cutoff:
                transcription_job_repository.delete(job_id)
                records_deleted += 1
            else:
                remaining_jobs.append(job_id)
        encounter.transcription_job_ids = remaining_jobs
        encounter_created = encounter.created_at
        if encounter_created.tzinfo is None:
            encounter_created = encounter_created.replace(tzinfo=timezone.utc)
        if encounter_created < transcript_cutoff:
            clinical_note_repository.delete_by_encounter(encounter.id)
            encounter_repository.delete(encounter.id)
            records_deleted += 1
        else:
            encounter_repository.save(encounter)

    # Jobs may be created directly, by a live WebSocket, or attached only to a
    # conversation session. Retention must not depend on encounter attachment.
    for job in list(transcription_job_repository.list_all()):
        created_at = job.created_at
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        if created_at < audio_cutoff and str(job.audio_url):
            audio_module.audio_storage_backend.delete_file(str(job.audio_url))
            audio_deleted += 1
        if created_at < transcript_cutoff:
            transcription_job_repository.delete(job.id)
            records_deleted += 1

    audit_service.log_event(
        action="purge_expired_phi",
        resource_type="retention_policy",
        extra={
            "user_id": str(current_user.id),
            "role": current_user.role.value,
            "count": records_deleted,
        },
    )
    return {"audio_deleted": audio_deleted, "records_deleted": records_deleted}
