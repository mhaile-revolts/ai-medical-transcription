from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, Optional
from uuid import UUID, uuid4

from src.backend.domain.models.clinical_encounter import ClinicalEncounter, EncounterStatus
from src.backend.domain.models.clinical_note import ClinicalNote, ClinicalNoteSection
from src.backend.tenancy import get_current_tenant
from src.backend.config import settings


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
            created_at=datetime.now(timezone.utc),
            clinician_id=clinician_id,
            patient_id=patient_id,
            title=title,
            status=EncounterStatus.CREATED,
            tenant_id=get_current_tenant(),
        )
        self._encounters[encounter_id] = encounter
        if self._durable():
            from src.backend.infra.db.inmemory import encounter_repository
            encounter_repository.save(encounter)
        return encounter

    @staticmethod
    def _durable() -> bool:
        return settings.app_mode != "demo" or settings.use_sql_repos

    def get_encounter(self, encounter_id: UUID) -> Optional[ClinicalEncounter]:
        if self._durable():
            from src.backend.infra.db.inmemory import encounter_repository
            return encounter_repository.get(encounter_id)
        enc = self._encounters.get(encounter_id)
        if enc is None:
            return None
        if enc.tenant_id != get_current_tenant():
            return None
        return enc

    def attach_job(self, encounter_id: UUID, job_id: UUID) -> ClinicalEncounter:
        encounter = self.get_encounter(encounter_id)
        if encounter is None:
            raise KeyError(encounter_id)
        if encounter.tenant_id != get_current_tenant():
            raise KeyError("Encounter does not belong to current tenant")
        if job_id not in encounter.transcription_job_ids:
            encounter.transcription_job_ids.append(job_id)
            if encounter.status == EncounterStatus.CREATED:
                encounter.status = EncounterStatus.IN_PROGRESS
            self._encounters[encounter_id] = encounter
            if self._durable():
                from src.backend.infra.db.inmemory import encounter_repository
                encounter_repository.save(encounter)
        return encounter

    @staticmethod
    def is_confirmed_recording_allowed(encounter: ClinicalEncounter) -> bool:
        return bool(
            encounter.external_patient_id
            and encounter.external_encounter_id
            and encounter.external_encounter_status in {"arrived", "triaged", "in-progress", "onleave"}
            and encounter.consent_obtained_at
            and not encounter.consent_revoked_at
        )

    # Notes

    def find_encounter_for_job(self, job_id: UUID) -> Optional[ClinicalEncounter]:
        """Return the first encounter that references the given transcription job.

        This helper is intentionally simple and linear over the small in-memory
        store; a persistence-backed implementation would use a proper index or
        join instead.
        """

        if self._durable():
            from src.backend.infra.db.inmemory import encounter_repository
            return next((e for e in encounter_repository.list_by_filters()
                         if job_id in e.transcription_job_ids), None)
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
        """Create or update a clinical note from a SOAP structure.

        When a note has already been finalized via the review/finalization
        workflow, this helper will **not** overwrite it unless `Finalize` is
        explicitly requested. This protects clinician-reviewed notes from being
        clobbered by later NLP re-analysis of the same encounter.
        """

        now = datetime.now(timezone.utc)

        existing = self._find_note_for_encounter(encounter_id)
        if existing is not None and existing.is_finalized:
            # Approved content is immutable. Any future amendment workflow must
            # create a new note version and collect fresh doctor approval.
            return existing

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
        if self._durable():
            from src.backend.infra.db.inmemory import clinical_note_repository
            clinical_note_repository.save(note)

        # Optionally advance encounter status when a note exists
        encounter = self.get_encounter(encounter_id)
        if encounter is not None:
            if finalize:
                encounter.status = EncounterStatus.FINALIZED
            elif encounter.status in {EncounterStatus.CREATED, EncounterStatus.IN_PROGRESS}:
                encounter.status = EncounterStatus.READY_FOR_REVIEW
            self._encounters[encounter_id] = encounter
            if self._durable():
                from src.backend.infra.db.inmemory import encounter_repository
                encounter_repository.save(encounter)

        return note

    def get_note(self, note_id: UUID) -> Optional[ClinicalNote]:
        if self._durable():
            from src.backend.infra.db.inmemory import clinical_note_repository
            return clinical_note_repository.get(note_id)
        note = self._notes.get(note_id)
        if note is None:
            return None
        if note.tenant_id != get_current_tenant():
            return None
        return note

    def _find_note_for_encounter(self, encounter_id: UUID) -> Optional[ClinicalNote]:
        if self._durable():
            from src.backend.infra.db.inmemory import clinical_note_repository
            return clinical_note_repository.get_by_encounter(encounter_id)
        current_tenant = get_current_tenant()
        for note in self._notes.values():
            if note.tenant_id != current_tenant:
                continue
            if note.encounter_id == encounter_id:
                return note
        return None


encounter_service = InMemoryEncounterService()
