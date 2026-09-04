from __future__ import annotations

from typing import Any, Iterable, Optional
from uuid import UUID

from src.backend.domain.models.clinical_encounter import ClinicalEncounter, EncounterStatus
from src.backend.domain.models.clinical_note import ClinicalNote
from src.backend.domain.models.transcription_job import TranscriptJob
from src.backend.infra.db.repositories import (
    EncounterRepository,
    ClinicalNoteRepository,
    TranscriptionJobRepository,
)
from src.backend.services.encounters.service import encounter_service
from src.backend.services.transcription.service import transcription_service
from src.backend.tenancy import get_current_tenant


class InMemoryEncounterRepository(EncounterRepository):
    def get(self, encounter_id: UUID) -> Optional[ClinicalEncounter]:
        enc = encounter_service.get_encounter(encounter_id)
        if enc is None:
            return None
        if enc.tenant_id != get_current_tenant():
            return None
        return enc

    def list_by_filters(
        self,
        *,
        clinician_id: Optional[str] = None,
        patient_id: Optional[str] = None,
        status: Optional[EncounterStatus] = None,
    ) -> Iterable[ClinicalEncounter]:
        current_tenant = get_current_tenant()
        for enc in encounter_service._encounters.values():  # type: ignore[attr-defined]
            if enc.tenant_id != current_tenant:
                continue
            if clinician_id is not None and enc.clinician_id != clinician_id:
                continue
            if patient_id is not None and enc.patient_id != patient_id:
                continue
            if status is not None and enc.status != status:
                continue
            yield enc

    def save(self, encounter: ClinicalEncounter) -> None:
        # The underlying service mutates encounters in-place; assigning back keeps
        # semantics consistent for now.
        encounter_service._encounters[encounter.id] = encounter  # type: ignore[attr-defined]

    def delete(self, encounter_id: UUID) -> None:
        encounter = self.get(encounter_id)
        if encounter is not None:
            encounter_service._encounters.pop(encounter_id, None)  # type: ignore[attr-defined]


class InMemoryClinicalNoteRepository(ClinicalNoteRepository):
    def get(self, note_id: UUID) -> Optional[ClinicalNote]:
        note = encounter_service.get_note(note_id)
        if note is None:
            return None
        if note.tenant_id != get_current_tenant():
            return None
        return note

    def get_by_encounter(self, encounter_id: UUID) -> Optional[ClinicalNote]:
        note = encounter_service._find_note_for_encounter(encounter_id)  # type: ignore[attr-defined]
        if note is None:
            return None
        if note.tenant_id != get_current_tenant():
            return None
        return note

    def save(self, note: ClinicalNote) -> None:
        encounter_service._notes[note.id] = note  # type: ignore[attr-defined]

    def delete_by_encounter(self, encounter_id: UUID) -> None:
        note = self.get_by_encounter(encounter_id)
        if note is not None:
            encounter_service._notes.pop(note.id, None)  # type: ignore[attr-defined]


class InMemoryTranscriptionJobRepository(TranscriptionJobRepository):
    def get(self, job_id: UUID) -> Optional[TranscriptJob]:
        job = transcription_service._jobs.get(job_id)  # type: ignore[attr-defined]
        if job is None or job.tenant_id != get_current_tenant():
            return None
        return job

    def save(self, job: TranscriptJob) -> None:
        transcription_service._jobs[job.id] = job  # type: ignore[attr-defined]

    def list_all(self) -> Iterable[TranscriptJob]:
        current_tenant = get_current_tenant()
        return [
            job
            for job in transcription_service._jobs.values()  # type: ignore[attr-defined]
            if job.tenant_id == current_tenant
        ]

    def delete(self, job_id: UUID) -> None:
        job = self.get(job_id)
        if job is not None:
            transcription_service._jobs.pop(job_id, None)  # type: ignore[attr-defined]


class RepositoryProxy:
    """Stable import-time repository handle.

    Route modules import repositories during application construction.  Mutating
    a module global later does not update those imports, so a forwarding proxy is
    used to make bootstrap switches visible to every already-imported route.
    """
    def __init__(self, target: Any) -> None:
        self.target = target

    def set_target(self, target: Any) -> None:
        self.target = target

    def __getattr__(self, name: str) -> Any:
        return getattr(self.target, name)


encounter_repository = RepositoryProxy(InMemoryEncounterRepository())
clinical_note_repository = RepositoryProxy(InMemoryClinicalNoteRepository())
transcription_job_repository = RepositoryProxy(InMemoryTranscriptionJobRepository())
