from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from src.backend.domain.models.clinical_encounter import ClinicalEncounter, EncounterStatus
from src.backend.domain.models.clinical_note import ClinicalNote
from src.backend.domain.models.ehr_connection import EHRConnection
from src.backend.domain.models.ehr_message import EHRMessage
from src.backend.domain.nlp.models import ClinicalEntities, SOAPNote
from src.backend.infra.db.ehr_inmemory import (
    ehr_connection_repository,
    ehr_message_repository,
)
from src.backend.services.ehr import fhir_mapper
from src.backend.services.ehr.transport import EHRTransport, HttpFHIRTransport, EHRTransportError
from src.backend.services.audit.service import audit_service
from src.backend.tenancy import get_current_tenant


class EHRIntegrationService:
    """High-level service for building and dispatching EHR payloads.

    This service is intentionally minimal for now:
    * Supports outbound FHIR document bundles for finalized encounters.
    * Uses in-memory repositories for connections/messages (SQL can be added later).
    """

    def __init__(self, transport: Optional[EHRTransport] = None) -> None:
        self._transport = transport or HttpFHIRTransport()

    # Connection helpers
    def list_active_connections(self) -> list[EHRConnection]:
        return list(ehr_connection_repository.list_active())

    def get_connection(self, connection_id: UUID) -> Optional[EHRConnection]:
        return ehr_connection_repository.get(connection_id)

    def save_connection(self, connection: EHRConnection) -> None:
        ehr_connection_repository.save(connection)

    # Message helpers
    def get_message(self, message_id: UUID) -> Optional[EHRMessage]:
        return ehr_message_repository.get(message_id)

    def list_messages_by_status(self, *statuses: str) -> list[EHRMessage]:
        return list(ehr_message_repository.list_by_status(*statuses))

    # Core export path
    def build_bundle_for_encounter(
        self,
        *,
        encounter: ClinicalEncounter,
        note: ClinicalNote,
        entities: ClinicalEntities,
        soap_note: SOAPNote,
    ) -> dict:
        bundle_id = uuid4()
        return fhir_mapper.build_document_bundle(
            bundle_id=bundle_id,
            entities=entities,
            soap_note=soap_note,
            encounter=encounter,
        )

    async def enqueue_and_send_bundle(
        self,
        *,
        connection: EHRConnection,
        encounter: ClinicalEncounter,
        note: ClinicalNote,
        entities: ClinicalEntities,
        soap_note: SOAPNote,
    ) -> EHRMessage:
        """Build, persist, and attempt to send a bundle to the EHR.

        For now this is synchronous (awaits on the HTTP call). A future
        enhancement can split enqueueing from dispatch into a background
        scheduler.
        """

        tenant_id = get_current_tenant()
        bundle = self.build_bundle_for_encounter(
            encounter=encounter,
            note=note,
            entities=entities,
            soap_note=soap_note,
        )

        now = datetime.utcnow()
        message = EHRMessage(
            id=uuid4(),
            tenant_id=tenant_id,
            connection_id=connection.id,
            resource_type=bundle.get("resourceType", "Bundle"),
            payload=bundle,
            direction="outbound",
            status="pending",
            related_encounter_id=encounter.id,
            related_note_id=note.id,
            created_at=now,
            updated_at=now,
            retry_count=0,
        )
        ehr_message_repository.save(message)

        try:
            await self._transport.send_bundle(connection, bundle)
        except EHRTransportError as exc:
            message.status = "failed"
            message.last_error = str(exc)
            message.retry_count += 1
            ehr_message_repository.save(message)

            audit_service.log_event(
                action="ehr_export_failed",
                resource_type="ehr_message",
                resource_id=str(message.id),
                extra={
                    "connection_id": str(connection.id),
                    "encounter_id": str(encounter.id),
                    "note_id": str(note.id),
                    "error": str(exc),
                },
            )
            return message

        message.status = "sent"
        message.updated_at = datetime.utcnow()
        ehr_message_repository.save(message)

        audit_service.log_event(
            action="ehr_export_sent",
            resource_type="ehr_message",
            resource_id=str(message.id),
            extra={
                "connection_id": str(connection.id),
                "encounter_id": str(encounter.id),
                "note_id": str(note.id),
            },
        )

        return message


ehr_integration_service = EHRIntegrationService()
