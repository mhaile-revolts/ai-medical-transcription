from __future__ import annotations

from typing import Iterable, Optional
from uuid import UUID

from src.backend.domain.models.clinical_note import ClinicalNote
from src.backend.domain.models.transcription_job import TranscriptJob
from src.backend.infra.db.models_notes_jobs import ClinicalNoteORM, TranscriptJobORM
from src.backend.infra.db.repositories import ClinicalNoteRepository, TranscriptionJobRepository
from src.backend.infra.db.session import SessionFactory
from src.backend.tenancy import get_current_tenant


class SqlClinicalNoteRepository(ClinicalNoteRepository):  # pragma: no cover - not wired yet
    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    def get(self, note_id: UUID) -> Optional[ClinicalNote]:
        session = self._session_factory()
        try:
            orm = session.get(ClinicalNoteORM, note_id)
            if orm is None:
                return None
            if orm.tenant_id != get_current_tenant():
                return None
            return orm.to_domain()
        finally:
            session.close()

    def get_by_encounter(self, encounter_id: UUID) -> Optional[ClinicalNote]:
        session = self._session_factory()
        try:
            current_tenant = get_current_tenant()
            orm = (
                session.query(ClinicalNoteORM)
                .filter(
                    ClinicalNoteORM.encounter_id == encounter_id,
                    ClinicalNoteORM.tenant_id == current_tenant,
                )
                .order_by(ClinicalNoteORM.created_at.desc())
                .first()
            )
            return orm.to_domain() if orm is not None else None
        finally:
            session.close()

    def save(self, note: ClinicalNote) -> None:
        session = self._session_factory()
        try:
            existing = session.get(ClinicalNoteORM, note.id)
            if existing is None:
                orm = ClinicalNoteORM.from_domain(note)
                session.add(orm)
            else:
                existing.encounter_id = note.encounter_id
                existing.created_at = note.created_at
                existing.updated_at = note.updated_at
                existing.created_by = note.created_by
                existing.last_edited_by = note.last_edited_by
                existing.is_finalized = note.is_finalized
                existing.reviewed_by = note.reviewed_by
                existing.reviewed_at = note.reviewed_at
                existing.review_comment = note.review_comment
                existing.subjective = note.subjective.text
                existing.objective = note.objective.text
                existing.assessment = note.assessment.text
                existing.plan = note.plan.text
                existing.tenant_id = note.tenant_id
            session.commit()
        finally:
            session.close()


class SqlTranscriptionJobRepository(TranscriptionJobRepository):  # pragma: no cover - not wired yet
    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    def get(self, job_id: UUID) -> Optional[TranscriptJob]:
        session = self._session_factory()
        try:
            orm = session.get(TranscriptJobORM, job_id)
            if orm is None:
                return None
            if orm.tenant_id != get_current_tenant():
                return None
            return orm.to_domain()
        finally:
            session.close()
