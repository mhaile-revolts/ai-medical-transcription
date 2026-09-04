from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
from typing import Optional
from uuid import UUID, uuid4

from src.backend.domain.models.clinical_encounter import ClinicalEncounter, EncounterStatus
from src.backend.domain.models.clinical_note import ClinicalNote
from src.backend.domain.models.ehr_connection import EHRConnection
from src.backend.domain.models.ehr_message import EHRMessage
from src.backend.infra.db.ehr_inmemory import (
    ehr_connection_repository,
    ehr_message_repository,
)
from src.backend.infra.db.inmemory import clinical_note_repository, encounter_repository
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
    def _validate_ochin_contract(self, connection: EHRConnection) -> str:
        config = connection.auth_config
        if "ochin_note_write" not in connection.supported_capabilities:
            raise ValueError("Connection is not approved for OCHIN note write-back")
        if config.get("approved_write_resource") != "DocumentReference":
            raise ValueError("OCHIN-approved write resource must be DocumentReference")
        profile = str(config.get("document_reference_profile") or "").strip()
        if not profile:
            raise ValueError("OCHIN-approved DocumentReference profile is required")
        scopes = set(config.get("approved_scopes") or [])
        if not scopes.intersection(
            {"system/DocumentReference.write", "user/DocumentReference.write",
             "system/DocumentReference.rs", "user/DocumentReference.rs"}
        ):
            raise ValueError("OCHIN-approved DocumentReference write scope is required")
        return profile

    @staticmethod
    def _idempotency_key(connection: EHRConnection, note: ClinicalNote) -> str:
        source = f"{connection.id}:{note.id}:{note.updated_at.isoformat()}"
        return hashlib.sha256(source.encode("utf-8")).hexdigest()

    def _validate_delivery(
        self,
        *,
        connection: EHRConnection,
        encounter: ClinicalEncounter,
        note: ClinicalNote,
    ) -> str:
        if not connection.is_active:
            raise ValueError("EHR connection is disabled")
        if encounter.status != EncounterStatus.FINALIZED or not note.is_finalized:
            raise ValueError("Only finalized notes can be exported")
        if not encounter.external_patient_id or not encounter.external_encounter_id:
            raise ValueError("Confirmed external Patient and Encounter are required")
        if not (
            encounter.consent_obtained_at
            and encounter.consent_method
            and encounter.consent_version
        ):
            raise ValueError("Recorded SMART confirmation and consent evidence are required")
        if encounter.consent_revoked_at is not None:
            raise ValueError("Patient consent was revoked")
        if not note.reviewed_by or not note.reviewed_at:
            raise ValueError("Explicit doctor approval is required before export")
        if note.encounter_id != encounter.id:
            raise ValueError("Note does not belong to the encounter")
        return self._validate_ochin_contract(connection)

    async def export_approved_note(
        self,
        *,
        connection: EHRConnection,
        encounter: ClinicalEncounter,
        note: ClinicalNote,
    ) -> EHRMessage:
        tenant_id = get_current_tenant()
        profile = self._validate_delivery(
            connection=connection, encounter=encounter, note=note
        )
        idempotency_key = self._idempotency_key(connection, note)
        resource = fhir_mapper.build_ochin_document_reference(
            note=note, encounter=encounter, profile_url=profile,
            idempotency_key=idempotency_key,
        )
        now = datetime.now(timezone.utc)
        message = EHRMessage(
            id=uuid4(),
            tenant_id=tenant_id,
            connection_id=connection.id,
            resource_type="DocumentReference",
            payload=resource,
            direction="outbound",
            status="pending",
            related_encounter_id=encounter.id,
            related_note_id=note.id,
            created_at=now,
            updated_at=now,
            retry_count=0,
            idempotency_key=idempotency_key,
        )
        claimed = ehr_message_repository.save_if_absent(message)
        if claimed.id != message.id:
            return claimed
        audit_service.log_event(
            action="ehr_export_queued",
            resource_type="ehr_message",
            resource_id=str(message.id),
            extra={
                "connection_id": str(connection.id),
                "encounter_id": str(encounter.id),
                "note_id": str(note.id),
            },
        )
        return await self._deliver_message(
            message=message, connection=connection, encounter=encounter, note=note
        )

    async def retry_message(self, message_id: UUID) -> EHRMessage:
        message = ehr_message_repository.get(message_id)
        if message is None:
            raise ValueError("EHR message not found")
        if message.status == "delivered":
            return message
        connection = ehr_connection_repository.get(message.connection_id)
        if connection is None:
            raise ValueError("EHR connection not found")
        encounter = (
            encounter_repository.get(message.related_encounter_id)
            if message.related_encounter_id else None
        )
        note = (
            clinical_note_repository.get(message.related_note_id)
            if message.related_note_id else None
        )
        if encounter is None or note is None:
            raise ValueError("Related encounter or note not found")
        self._validate_delivery(connection=connection, encounter=encounter, note=note)
        if self._idempotency_key(connection, note) != message.idempotency_key:
            raise ValueError("Queued export no longer matches the approved note version")
        return await self._deliver_message(
            message=message, connection=connection, encounter=encounter, note=note
        )

    async def _deliver_message(
        self,
        *,
        message: EHRMessage,
        connection: EHRConnection,
        encounter: ClinicalEncounter,
        note: ClinicalNote,
    ) -> EHRMessage:
        now = datetime.now(timezone.utc)
        message.status = "pending"
        message.last_attempt_at = now
        message.last_error = None
        ehr_message_repository.save(message)
        audit_service.log_event(
            action="ehr_export_attempted",
            resource_type="ehr_message",
            resource_id=str(message.id),
            extra={"retry_count": message.retry_count},
        )
        try:
            receipt = await self._transport.send_resource(
                connection, message.payload, message.idempotency_key
            )
        except EHRTransportError as exc:
            message.status = "failed"
            message.last_error = str(exc)
            message.retry_count += 1
            message.next_retry_at = (
                now + timedelta(minutes=min(2 ** message.retry_count, 60))
                if exc.retryable else None
            )
            ehr_message_repository.save(message)

            audit_service.log_event(
                action="ehr_export_failed",
                resource_type="ehr_message",
                resource_id=str(message.id),
                extra={
                    "connection_id": str(connection.id),
                    "encounter_id": str(message.related_encounter_id),
                    "note_id": str(message.related_note_id),
                    "error": str(exc),
                    "retryable": exc.retryable,
                    "retry_count": message.retry_count,
                },
            )
            return message
        message.status = "delivered"
        message.remote_resource_id = receipt.remote_resource_id
        message.delivered_at = datetime.now(timezone.utc)
        message.next_retry_at = None
        ehr_message_repository.save(message)

        audit_service.log_event(
            action="ehr_export_sent",
            resource_type="ehr_message",
            resource_id=str(message.id),
            extra={
                "connection_id": str(connection.id),
                "encounter_id": str(message.related_encounter_id),
                "note_id": str(message.related_note_id),
                "remote_resource_id": message.remote_resource_id,
            },
        )
        return message


ehr_integration_service = EHRIntegrationService()
