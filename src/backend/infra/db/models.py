from __future__ import annotations

from datetime import datetime
from typing import List
from uuid import UUID

from sqlalchemy import DateTime, String, Text, UniqueConstraint, LargeBinary
from sqlalchemy import Uuid
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class EncounterORM(Base):  # pragma: no cover - not wired yet
    __tablename__ = "encounters"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    clinician_id: Mapped[str | None] = mapped_column(String, nullable=True)
    patient_id: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str | None] = mapped_column(String, nullable=True)
    assigned_scribe_id: Mapped[str | None] = mapped_column(String, nullable=True)
    # For the MVP we store transcription_job_ids as a simple comma-separated
    # list of UUID strings. A more normalized schema can be introduced later.
    transcription_job_ids: Mapped[str | None] = mapped_column(String, nullable=True)
    # Tenant/organization identifier for multitenancy.
    tenant_id: Mapped[str] = mapped_column(String, nullable=False)

    @classmethod
    def from_domain(cls, encounter: "ClinicalEncounter") -> "EncounterORM":  # type: ignore[name-defined]
        from src.backend.domain.models.clinical_encounter import ClinicalEncounter

        job_ids = ",".join(str(j) for j in encounter.transcription_job_ids) if encounter.transcription_job_ids else None
        return cls(
            id=encounter.id,
            created_at=encounter.created_at,
            clinician_id=encounter.clinician_id,
            patient_id=encounter.patient_id,
            status=encounter.status.value,
            title=encounter.title,
            assigned_scribe_id=encounter.assigned_scribe_id,
            transcription_job_ids=job_ids,
            tenant_id=encounter.tenant_id,
        )

    def to_domain(self) -> "ClinicalEncounter":  # type: ignore[name-defined]
        from src.backend.domain.models.clinical_encounter import ClinicalEncounter, EncounterStatus

        job_ids: List[UUID] = []
        if self.transcription_job_ids:
            from uuid import UUID as _UUID

            job_ids = [_UUID(v) for v in self.transcription_job_ids.split(",") if v]

        return ClinicalEncounter(
            id=self.id,
            created_at=self.created_at,
            clinician_id=self.clinician_id,
            patient_id=self.patient_id,
            status=EncounterStatus(self.status),
            title=self.title,
            assigned_scribe_id=self.assigned_scribe_id,
            transcription_job_ids=job_ids,
            tenant_id=self.tenant_id,
        )


class UserORM(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    subject: Mapped[str] = mapped_column(String, nullable=False)
    email: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False)

    __table_args__ = (UniqueConstraint("subject", "tenant_id", name="uq_users_subject_tenant"),)


class AudioBlobORM(Base):
    """Private audio payload; the opaque reference is stored on the job."""
    __tablename__ = "audio_blobs"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    filename: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)


class ConversationSessionORM(Base):
    __tablename__ = "conversation_sessions"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    title: Mapped[str | None] = mapped_column(String, nullable=True)
    transcription_job_ids: Mapped[str | None] = mapped_column(Text, nullable=True)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False, index=True)

    @classmethod
    def from_domain(cls, session: "ConversationSession") -> "ConversationSessionORM":  # type: ignore[name-defined]
        return cls(
            id=session.id,
            created_at=session.created_at,
            ended_at=session.ended_at,
            title=session.title,
            transcription_job_ids=",".join(str(job_id) for job_id in session.transcription_job_ids) or None,
            tenant_id=session.tenant_id,
        )

    def to_domain(self) -> "ConversationSession":  # type: ignore[name-defined]
        from src.backend.domain.models.conversation_session import ConversationSession

        return ConversationSession(
            id=self.id,
            created_at=self.created_at,
            ended_at=self.ended_at,
            title=self.title,
            transcription_job_ids=[
                UUID(value) for value in (self.transcription_job_ids or "").split(",") if value
            ],
            tenant_id=self.tenant_id,
        )
