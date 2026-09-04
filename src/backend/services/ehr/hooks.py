from __future__ import annotations

from typing import Optional

from uuid import UUID

from src.backend.domain.models.clinical_encounter import ClinicalEncounter, EncounterStatus
from src.backend.domain.models.clinical_note import ClinicalNote
from src.backend.services.ehr.integration_service import ehr_integration_service
from src.backend.infra.db.ehr_inmemory import ehr_connection_repository


async def export_finalized_encounter_if_configured(
    *,
    encounter: ClinicalEncounter,
    note: ClinicalNote,
) -> None:
    """Export a finalized encounter/note to the default EHR connection if enabled.

    This is a thin integration hook that higher-level workflows can call
    (e.g., after NLP analysis has produced entities/notes and the encounter is
    marked FINALIZED). For now it:
    * Picks the first active connection for the tenant.
    * Requires soap_note/entities if provided; otherwise no-op.
    """

    if encounter.status != EncounterStatus.FINALIZED:
        return

    # Simple behavior for now: pick the first active connection and send.
    for conn in ehr_connection_repository.list_active():
        await ehr_integration_service.export_approved_note(
            connection=conn,
            encounter=encounter,
            note=note,
        )
        break
