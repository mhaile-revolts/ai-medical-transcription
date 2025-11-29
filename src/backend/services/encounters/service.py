from __future__ import annotations

from datetime import datetime
from typing import Dict, Optional
from uuid import UUID, uuid4

from src.backend.domain.models.clinical_encounter import ClinicalEncounter, EncounterStatus
from src.backend.domain.models.clinical_note import ClinicalNote, ClinicalNoteSection
from src.backend.tenancy import get_current_tenant


class InMemoryEncounterService:
    """In-memory service for managing clinical encounters and notes.

    This is intended for early prototyping and tests only. A future
    implementation will persist encounters/notes in a database.
    """

    def __init__(self) -> None:
        self._encounters: Dict[UUID, ClinicalEncounter] = {}
        self._notes: Dict[UUID, ClinicalNote] = {}

    # Encounters

    def create_encounter(
        self,
        *,
        clinician_id: Optional[str] = None,
        patient_id: Optional[str] = None,
        title: Optional[str] = None,
    ) -> ClinicalEncounter:
        encounter_id = uuid4()
        encounter = ClinicalEncounter(
            id=encounter_id,
            created_at=datetime.utcnow(),
            clinician_id=clinician_id,
            patient_id=patient_id,
            title=title,
            status=EncounterStatus.CREATED,
            tenant_id=get_current_tenant(),
        )
        self._encounters[encounter_id] = encounter
        return encounter

    def get_encounter(self, encounter_id: UUID) -> Optional[ClinicalEncounter]:
        enc = self._encounters.get(encounter_id)
        if enc is None:
            return None
        if enc.tenant_id != get_current_tenant():
            return None
        return enc

    def attach_job(self, encounter_id: UUID, job_id: UUID) -> ClinicalEncounter:
        encounter = self._encounters[encounter_id]
        if encounter.tenant_id != get_current_tenant():
            raise KeyError("Encounter does not belong to current tenant")
        if job_id not in encounter.transcription_job_ids:
            encounter.transcription_job_ids.append(job_id)
            if encounter.status == EncounterStatus.CREATED:
                encounter.status = EncounterStatus.IN_PROGRESS
            self._encounters[encounter_id] = encounter
        return encounter

    # Notes

    def find_encounter_for_job(self, job_id: UUID) -> Optional[ClinicalEncounter]:
        """Return the first encounter that references the given transcription job.

        This helper is intentionally simple and linear over the small in-memory
        store; a persistence-backed implementation would use a proper index or
        join instead.
        """

        current_tenant = get_current_tenant()
        for encounter in self._encounters.values():
            if encounter.tenant_id != current_tenant:
                continue
            if job_id in encounter.transcription_job_ids:
                return encounter
        return None

    def upsert_note_from_soap(
        self,
        *,
        encounter_id: UUID,
        subjective: str,
        objective: str,
        assessment: str,
        plan: str,
        editor_id: Optional[str] = None,
        finalize: bool = False,
    ) -> ClinicalNote:
        now = datetime.utcnow()

        existing = self._find_note_for_encounter(encounter_id)
        if existing is None:
            note_id = uuid4()
            note = ClinicalNote(
                id=note_id,
                encounter_id=encounter_id,
                created_at=now,
                updated_at=now,
                created_by=editor_id,
                last_edited_by=editor_id,
                is_finalized=finalize,
                subjective=ClinicalNoteSection(text=subjective),
                objective=ClinicalNoteSection(text=objective),
                assessment=ClinicalNoteSection(text=assessment),
                plan=ClinicalNoteSection(text=plan),
                tenant_id=get_current_tenant(),
            )
        else:
            note = existing
            note.updated_at = now
            note.last_edited_by = editor_id or note.last_edited_by
            note.is_finalized = note.is_finalized or finalize
            note.subjective.text = subjective
            note.objective.text = objective
            note.assessment.text = assessment
            note.plan.text = plan

        self._notes[note.id] = note

        # Optionally advance encounter status when a note exists
        encounter = self._encounters.get(encounter_id)
        if encounter is not None:
            if finalize:
                encounter.status = EncounterStatus.FINALIZED
            elif encounter.status in {EncounterStatus.CREATED, EncounterStatus.IN_PROGRESS}:
                encounter.status = EncounterStatus.READY_FOR_REVIEW
            self._encounters[encounter_id] = encounter

        return note

    def get_note(self, note_id: UUID) -> Optional[ClinicalNote]:
        note = self._notes.get(note_id)
        if note is None:
            return None
        if note.tenant_id != get_current_tenant():
            return None
        return note

    def _find_note_for_encounter(self, encounter_id: UUID) -> Optional[ClinicalNote]:
        current_tenant = get_current_tenant()
        for note in self._notes.values():
            if note.tenant_id != current_tenant:
                continue
            if note.encounter_id == encounter_id:
                return note
        return None


encounter_service = InMemoryEncounterService()
