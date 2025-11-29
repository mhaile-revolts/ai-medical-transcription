from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import Boolean, DateTime, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.backend.infra.db.models import Base


class ClinicalNoteORM(Base):  # pragma: no cover - not wired yet
    __tablename__ = "clinical_notes"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    encounter_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by: Mapped[str | None] = mapped_column(String, nullable=True)
    last_edited_by: Mapped[str | None] = mapped_column(String, nullable=True)
    is_finalized: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reviewed_by: Mapped[str | None] = mapped_column(String, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    subjective: Mapped[str] = mapped_column(Text, nullable=False)
    objective: Mapped[str] = mapped_column(Text, nullable=False)
    assessment: Mapped[str] = mapped_column(Text, nullable=False)
    plan: Mapped[str] = mapped_column(Text, nullable=False)
    # Tenant/organization identifier for multitenancy.
    tenant_id: Mapped[str] = mapped_column(String, nullable=False)

    @classmethod
    def from_domain(cls, note: "ClinicalNote") -> "ClinicalNoteORM":  # type: ignore[name-defined]
        from src.backend.domain.models.clinical_note import ClinicalNote

        return cls(
            id=note.id,
            encounter_id=note.encounter_id,
            created_at=note.created_at,
            updated_at=note.updated_at,
            created_by=note.created_by,
            last_edited_by=note.last_edited_by,
            is_finalized=note.is_finalized,
            reviewed_by=note.reviewed_by,
            reviewed_at=note.reviewed_at,
            review_comment=note.review_comment,
            subjective=note.subjective.text,
            objective=note.objective.text,
            assessment=note.assessment.text,
            plan=note.plan.text,
            tenant_id=note.tenant_id,
        )

    def to_domain(self) -> "ClinicalNote":  # type: ignore[name-defined]
        from src.backend.domain.models.clinical_note import ClinicalNote, ClinicalNoteSection

        return ClinicalNote(
            id=self.id,
            encounter_id=self.encounter_id,
            created_at=self.created_at,
            updated_at=self.updated_at,
            created_by=self.created_by,
            last_edited_by=self.last_edited_by,
            is_finalized=self.is_finalized,
            reviewed_by=self.reviewed_by,
            reviewed_at=self.reviewed_at,
            review_comment=self.review_comment,
            subjective=ClinicalNoteSection(text=self.subjective),
            objective=ClinicalNoteSection(text=self.objective),
            assessment=ClinicalNoteSection(text=self.assessment),
            plan=ClinicalNoteSection(text=self.plan),
            tenant_id=self.tenant_id,
        )


class TranscriptJobORM(Base):  # pragma: no cover - not wired yet
    __tablename__ = "transcription_jobs"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    audio_url: Mapped[str] = mapped_column(String, nullable=False)
    language_code: Mapped[str | None] = mapped_column(String, nullable=True)
    target_language: Mapped[str | None] = mapped_column(String, nullable=True)
    result_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    translated_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Tenant/organization identifier for multitenancy.
    tenant_id: Mapped[str] = mapped_column(String, nullable=False)

    @classmethod
    def from_domain(cls, job: "TranscriptJob") -> "TranscriptJobORM":  # type: ignore[name-defined]
        from src.backend.domain.models.transcription_job import TranscriptJob

        return cls(
            id=job.id,
            created_at=job.created_at,
            status=job.status.value,
            audio_url=str(job.audio_url),
            language_code=job.language_code,
            target_language=job.target_language,
            result_text=job.result_text,
            translated_text=job.translated_text,
            tenant_id=job.tenant_id,
        )

    def to_domain(self) -> "TranscriptJob":  # type: ignore[name-defined]
        from src.backend.domain.models.transcription_job import TranscriptJob, TranscriptJobStatus

        return TranscriptJob(
            id=self.id,
            created_at=self.created_at,
            status=TranscriptJobStatus(self.status),
            audio_url=self.audio_url,
            language_code=self.language_code,
            target_language=self.target_language,
            result_text=self.result_text,
            translated_text=self.translated_text,
            tenant_id=self.tenant_id,
        )
