from __future__ import annotations

from typing import Iterable, Optional
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


class InMemoryTranscriptionJobRepository(TranscriptionJobRepository):
    def get(self, job_id: UUID) -> Optional[TranscriptJob]:
        job = transcription_service.get_job(job_id)
        # transcription_service.get_job already scopes by tenant; no extra check.
        return job


encounter_repository: EncounterRepository = InMemoryEncounterRepository()
clinical_note_repository: ClinicalNoteRepository = InMemoryClinicalNoteRepository()
transcription_job_repository: TranscriptionJobRepository = InMemoryTranscriptionJobRepository()
