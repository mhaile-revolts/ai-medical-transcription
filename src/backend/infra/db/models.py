from __future__ import annotations

from datetime import datetime
from typing import List
from uuid import UUID

from sqlalchemy import Column, DateTime, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class EncounterORM(Base):  # pragma: no cover - not wired yet
    __tablename__ = "encounters"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    clinician_id: Mapped[str | None] = mapped_column(String, nullable=True)
    patient_id: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str | None] = mapped_column(String, nullable=True)
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
            transcription_job_ids=job_ids,
            tenant_id=self.tenant_id,
        )
