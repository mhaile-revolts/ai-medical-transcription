from __future__ import annotations

from typing import Iterable, Optional
from uuid import UUID

from src.backend.domain.models.clinical_encounter import ClinicalEncounter, EncounterStatus
from src.backend.infra.db.repositories import EncounterRepository
from src.backend.infra.db.session import SessionFactory
from src.backend.infra.db.models import EncounterORM
from src.backend.tenancy import get_current_tenant


class SqlEncounterRepository(EncounterRepository):  # pragma: no cover - skeleton only
    """SQL-backed EncounterRepository skeleton.

    This implementation is intentionally incomplete and is not wired into the
    application yet. It exists as a reference for how to structure a
    database-backed repository using a SessionFactory that produces ORM
    sessions (for example, SQLAlchemy sessions).
    """

    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    def get(self, encounter_id: UUID) -> Optional[ClinicalEncounter]:
        """Load a ClinicalEncounter from the database by primary key.

        Enforces tenant scoping using the current tenant context.
        """

        session = self._session_factory()
        try:
            orm = session.get(EncounterORM, encounter_id)
            if orm is None:
                return None
            if orm.tenant_id != get_current_tenant():
                return None
            return orm.to_domain()
        finally:
            session.close()

    def list_by_filters(
        self,
        *,
        clinician_id: Optional[str] = None,
        patient_id: Optional[str] = None,
        status: Optional[EncounterStatus] = None,
    ) -> Iterable[ClinicalEncounter]:
        """Yield ClinicalEncounter instances matching optional filters.

        Results are automatically scoped to the current tenant.
        """

        session = self._session_factory()
        try:
            current_tenant = get_current_tenant()
            query = session.query(EncounterORM).filter(EncounterORM.tenant_id == current_tenant)
            if clinician_id is not None:
                query = query.filter(EncounterORM.clinician_id == clinician_id)
            if patient_id is not None:
                query = query.filter(EncounterORM.patient_id == patient_id)
            if status is not None:
                query = query.filter(EncounterORM.status == status.value)

            for orm in query.all():
                yield orm.to_domain()
        finally:
            session.close()

    def save(self, encounter: ClinicalEncounter) -> None:
        """Insert or update a ClinicalEncounter in the database."""

        session = self._session_factory()
        try:
            existing = session.get(EncounterORM, encounter.id)
            if existing is None:
                orm = EncounterORM.from_domain(encounter)
                session.add(orm)
            else:
                # Update fields in-place from domain model.
                existing.created_at = encounter.created_at
                existing.clinician_id = encounter.clinician_id
                existing.patient_id = encounter.patient_id
                existing.status = encounter.status.value
                existing.title = encounter.title
                existing.transcription_job_ids = ",".join(
                    str(j) for j in encounter.transcription_job_ids
                ) if encounter.transcription_job_ids else None
                existing.tenant_id = encounter.tenant_id

            session.commit()
        finally:
            session.close()
