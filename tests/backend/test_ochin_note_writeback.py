import asyncio
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.backend.domain.models.clinical_encounter import ClinicalEncounter, EncounterStatus
from src.backend.domain.models.clinical_note import ClinicalNote, ClinicalNoteSection
from src.backend.domain.models.ehr_connection import EHRConnection
from src.backend.services.ehr.integration_service import EHRIntegrationService
from src.backend.services.ehr.transport import (
    EHRDeliveryReceipt, EHRTransport, EHRTransportError, HttpFHIRTransport,
)
from src.backend.infra.db.models import Base
from src.backend.infra.db.sql_ehr import SqlEHRConnectionRepository, SqlEHRMessageRepository
from src.backend.infra.db.inmemory import clinical_note_repository, encounter_repository
from src.backend.infra.db.ehr_inmemory import InMemoryEHRMessageRepository
from src.backend.tenancy import set_current_tenant


class RecordingTransport(EHRTransport):
    def __init__(self, errors=None):
        self.calls = []
        self.errors = list(errors or [])

    async def send_resource(self, connection, resource, idempotency_key):
        self.calls.append((resource, idempotency_key))
        if self.errors:
            raise self.errors.pop(0)
        return EHRDeliveryReceipt(remote_resource_id="epic-doc-1")


class HangingTransport(EHRTransport):
    def __init__(self):
        self.started = asyncio.Event()

    async def send_resource(self, connection, resource, idempotency_key):
        self.started.set()
        await asyncio.Event().wait()


def fixtures():
    now = datetime.now(timezone.utc)
    encounter = ClinicalEncounter(
        id=uuid4(), created_at=now, clinician_id="doctor", patient_id="local",
        external_patient_id="patient-123", external_encounter_id="encounter-456",
        external_encounter_status="in-progress", consent_obtained_at=now,
        consent_method="mobile_checkbox", consent_version="v1",
        status=EncounterStatus.FINALIZED, tenant_id="ochin-clinic",
    )
    note = ClinicalNote(
        id=uuid4(), encounter_id=encounter.id, created_at=now, updated_at=now,
        is_finalized=True, reviewed_by="doctor", reviewed_at=now,
        subjective=ClinicalNoteSection(text="S"), objective=ClinicalNoteSection(text="O"),
        assessment=ClinicalNoteSection(text="A"), plan=ClinicalNoteSection(text="P"),
        tenant_id="ochin-clinic",
    )
    connection = EHRConnection(
        id=uuid4(), tenant_id="ochin-clinic", name="OCHIN", base_url="https://fhir.test",
        supported_capabilities=["ochin_note_write"],
        auth_config={
            "approved_write_resource": "DocumentReference",
            "document_reference_profile": "https://ochin.example/fhir/StructureDefinition/approved-note",
            "approved_scopes": ["system/DocumentReference.write"],
        },
        created_at=now, updated_at=now,
    )
    return encounter, note, connection


@pytest.mark.asyncio
async def test_approved_note_uses_configured_profile_links_and_idempotency():
    set_current_tenant("ochin-clinic")
    encounter, note, connection = fixtures()
    transport = RecordingTransport()
    service = EHRIntegrationService(transport)
    service.save_connection(connection)

    first = await service.export_approved_note(connection=connection, encounter=encounter, note=note)
    duplicate = await service.export_approved_note(connection=connection, encounter=encounter, note=note)

    assert first.id == duplicate.id
    assert first.status == "delivered"
    assert len(transport.calls) == 1
    resource = first.payload
    assert resource["resourceType"] == "DocumentReference"
    assert resource["meta"]["profile"] == [connection.auth_config["document_reference_profile"]]
    assert resource["subject"]["reference"] == "Patient/patient-123"
    assert resource["context"]["encounter"][0]["reference"] == "Encounter/encounter-456"
    assert resource["docStatus"] == "final"


@pytest.mark.asyncio
async def test_unapproved_or_unprofiled_note_is_rejected_before_transport():
    set_current_tenant("ochin-clinic")
    encounter, note, connection = fixtures()
    transport = RecordingTransport()
    service = EHRIntegrationService(transport)
    note.reviewed_by = None
    with pytest.raises(ValueError, match="doctor approval"):
        await service.export_approved_note(connection=connection, encounter=encounter, note=note)
    note.reviewed_by = "doctor"
    connection.auth_config["document_reference_profile"] = ""
    with pytest.raises(ValueError, match="profile"):
        await service.export_approved_note(connection=connection, encounter=encounter, note=note)
    assert transport.calls == []


@pytest.mark.asyncio
async def test_disabled_connection_cannot_export_or_retry():
    set_current_tenant("ochin-disabled")
    encounter, note, connection = fixtures()
    encounter.tenant_id = note.tenant_id = connection.tenant_id = "ochin-disabled"
    connection.is_active = False
    transport = RecordingTransport()
    service = EHRIntegrationService(transport)
    service.save_connection(connection)
    with pytest.raises(ValueError, match="disabled"):
        await service.export_approved_note(connection=connection, encounter=encounter, note=note)
    assert transport.calls == []


@pytest.mark.asyncio
async def test_missing_or_revoked_confirmation_consent_blocks_phi_delivery():
    set_current_tenant("ochin-consent")
    encounter, note, connection = fixtures()
    encounter.tenant_id = note.tenant_id = connection.tenant_id = "ochin-consent"
    transport = RecordingTransport()
    service = EHRIntegrationService(transport)
    encounter.consent_obtained_at = None
    with pytest.raises(ValueError, match="consent evidence"):
        await service.export_approved_note(connection=connection, encounter=encounter, note=note)
    encounter.consent_obtained_at = datetime.now(timezone.utc)
    encounter.consent_revoked_at = datetime.now(timezone.utc)
    with pytest.raises(ValueError, match="revoked"):
        await service.export_approved_note(connection=connection, encounter=encounter, note=note)
    assert transport.calls == []


@pytest.mark.asyncio
async def test_retry_reuses_payload_and_idempotency_key_after_retryable_error():
    set_current_tenant("ochin-retry")
    encounter, note, connection = fixtures()
    encounter.tenant_id = note.tenant_id = connection.tenant_id = "ochin-retry"
    transport = RecordingTransport([EHRTransportError("503 unavailable", retryable=True)])
    service = EHRIntegrationService(transport)
    service.save_connection(connection)
    encounter_repository.save(encounter)
    clinical_note_repository.save(note)
    failed = await service.export_approved_note(connection=connection, encounter=encounter, note=note)
    assert failed.status == "failed"
    assert failed.next_retry_at is not None

    delivered = await service.retry_message(failed.id)
    assert delivered.status == "delivered"
    assert delivered.remote_resource_id == "epic-doc-1"
    assert transport.calls[0][0] == transport.calls[1][0]
    assert transport.calls[0][1] == transport.calls[1][1]


@pytest.mark.asyncio
async def test_retry_rechecks_revocation_and_approval_before_transport():
    set_current_tenant("ochin-retry-safety")
    encounter, note, connection = fixtures()
    encounter.tenant_id = note.tenant_id = connection.tenant_id = "ochin-retry-safety"
    transport = RecordingTransport([EHRTransportError("503 unavailable", retryable=True)])
    service = EHRIntegrationService(transport)
    service.save_connection(connection)
    encounter_repository.save(encounter)
    clinical_note_repository.save(note)
    failed = await service.export_approved_note(connection=connection, encounter=encounter, note=note)
    assert failed.status == "failed"

    encounter.consent_revoked_at = datetime.now(timezone.utc)
    encounter_repository.save(encounter)
    with pytest.raises(ValueError, match="revoked"):
        await service.retry_message(failed.id)
    assert len(transport.calls) == 1

    encounter.consent_revoked_at = None
    encounter_repository.save(encounter)
    note.reviewed_by = None
    clinical_note_repository.save(note)
    with pytest.raises(ValueError, match="doctor approval"):
        await service.retry_message(failed.id)
    assert len(transport.calls) == 1


@pytest.mark.asyncio
async def test_http_transport_uses_fhir_conditional_create_and_classifies_errors():
    requests = []

    def handler(request: httpx.Request):
        requests.append(request)
        return httpx.Response(422, json={"resourceType": "OperationOutcome"})

    encounter, note, connection = fixtures()
    resource = {"resourceType": "DocumentReference"}
    transport = HttpFHIRTransport(httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    with pytest.raises(EHRTransportError) as caught:
        await transport.send_resource(connection, resource, "stable-key")
    assert caught.value.retryable is False
    assert requests[0].url.path.endswith("/fhir/DocumentReference")
    assert requests[0].headers["If-None-Exist"].endswith("|stable-key")


def test_sql_outbox_survives_repository_restart_and_claims_duplicates(tmp_path):
    set_current_tenant("ochin-sql")
    engine = create_engine(f"sqlite:///{tmp_path / 'ehr.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    encounter, note, connection = fixtures()
    connection.tenant_id = "ochin-sql"
    connections = SqlEHRConnectionRepository(factory)
    connections.save(connection)
    assert SqlEHRConnectionRepository(factory).get(connection.id) is not None

    now = datetime.now(timezone.utc)
    from src.backend.domain.models.ehr_message import EHRMessage
    message = EHRMessage(
        id=uuid4(), tenant_id="ochin-sql", connection_id=connection.id,
        resource_type="DocumentReference", payload={"resourceType": "DocumentReference"},
        idempotency_key="persistent-key", created_at=now, updated_at=now,
    )
    first = SqlEHRMessageRepository(factory).save_if_absent(message)
    duplicate = message.model_copy(update={"id": uuid4()})
    claimed = SqlEHRMessageRepository(factory).save_if_absent(duplicate)
    assert claimed.id == first.id
    assert SqlEHRMessageRepository(factory).get(first.id).idempotency_key == "persistent-key"


def _failed_message(tenant_id, connection_id, *, retry_count=1, due_at=None):
    from src.backend.domain.models.ehr_message import EHRMessage
    now = datetime.now(timezone.utc)
    return EHRMessage(
        id=uuid4(), tenant_id=tenant_id, connection_id=connection_id,
        resource_type="DocumentReference", payload={"resourceType": "DocumentReference"},
        idempotency_key=str(uuid4()), created_at=now, updated_at=now,
        status="failed", retry_count=retry_count,
        next_retry_at=due_at or now - timedelta(seconds=1),
    )


def test_concurrent_workers_only_claim_a_due_message_once():
    repository = InMemoryEHRMessageRepository()
    connection_id = uuid4()
    set_current_tenant("concurrent-claims")
    message = _failed_message("concurrent-claims", connection_id)
    repository.save(message)

    def claim(worker_id):
        return repository.claim_due(
            worker_id=worker_id, now=datetime.now(timezone.utc), limit=1,
            lease_duration=timedelta(minutes=2), max_retries=6,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(claim, ["worker-a", "worker-b"]))

    assert sum(len(result) for result in results) == 1
    assert repository.get(message.id).status == "processing"


def test_expired_sql_claim_is_recovered_after_process_restart(tmp_path):
    set_current_tenant("restart-claim")
    engine = create_engine(
        f"sqlite:///{tmp_path / 'restart.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    message = _failed_message("restart-claim", uuid4())
    first_repository = SqlEHRMessageRepository(factory)
    first_repository.save(message)
    first = first_repository.claim_due(
        worker_id="stopped-worker", now=datetime.now(timezone.utc), limit=1,
        lease_duration=timedelta(milliseconds=1), max_retries=6,
    )
    assert len(first) == 1

    recovered = SqlEHRMessageRepository(factory).claim_due(
        worker_id="replacement-worker",
        now=datetime.now(timezone.utc) + timedelta(seconds=1),
        limit=1, lease_duration=timedelta(minutes=2), max_retries=6,
    )
    assert len(recovered) == 1
    assert recovered[0].id == message.id
    assert recovered[0].claimed_by == "replacement-worker"


@pytest.mark.asyncio
async def test_automatic_retry_exhaustion_becomes_terminal():
    tenant = f"retry-exhaustion-{uuid4()}"
    set_current_tenant(tenant)
    encounter, note, connection = fixtures()
    encounter.tenant_id = note.tenant_id = connection.tenant_id = tenant
    transport = RecordingTransport([
        EHRTransportError("temporary", retryable=True),
        EHRTransportError("still unavailable", retryable=True),
    ])
    service = EHRIntegrationService(
        transport, max_attempts=2, retry_base_seconds=1, retry_max_seconds=1,
    )
    service.save_connection(connection)
    encounter_repository.save(encounter)
    clinical_note_repository.save(note)
    failed = await service.export_approved_note(connection=connection, encounter=encounter, note=note)
    failed.next_retry_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    from src.backend.infra.db.ehr_inmemory import ehr_message_repository
    ehr_message_repository.save(failed)
    claimed = ehr_message_repository.claim_due(
        worker_id="worker", now=datetime.now(timezone.utc), limit=1,
        lease_duration=timedelta(minutes=2), max_retries=2,
    )

    terminal = await service.retry_claimed_message(claimed[0], "worker")
    assert terminal.status == "terminal"
    assert terminal.retry_count == 2
    assert terminal.next_retry_at is None
    assert len(transport.calls) == 2


@pytest.mark.asyncio
async def test_automatic_retry_eventually_delivers_with_original_idempotency_key():
    tenant = f"eventual-delivery-{uuid4()}"
    set_current_tenant(tenant)
    encounter, note, connection = fixtures()
    encounter.tenant_id = note.tenant_id = connection.tenant_id = tenant
    transport = RecordingTransport([EHRTransportError("temporary", retryable=True)])
    service = EHRIntegrationService(
        transport, max_attempts=3, retry_base_seconds=1, retry_max_seconds=1,
    )
    service.save_connection(connection)
    encounter_repository.save(encounter)
    clinical_note_repository.save(note)
    failed = await service.export_approved_note(connection=connection, encounter=encounter, note=note)
    original_key = failed.idempotency_key
    failed.next_retry_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    from src.backend.infra.db.ehr_inmemory import ehr_message_repository
    ehr_message_repository.save(failed)
    claimed = ehr_message_repository.claim_due(
        worker_id="worker", now=datetime.now(timezone.utc), limit=1,
        lease_duration=timedelta(minutes=2), max_retries=3,
    )

    delivered = await service.retry_claimed_message(claimed[0], "worker")
    assert delivered.status == "delivered"
    assert delivered.remote_resource_id == "epic-doc-1"
    assert [call[1] for call in transport.calls] == [original_key, original_key]


@pytest.mark.asyncio
async def test_interrupted_automatic_attempt_keeps_lease_and_is_reclaimed():
    tenant = f"interrupted-delivery-{uuid4()}"
    set_current_tenant(tenant)
    encounter, note, connection = fixtures()
    encounter.tenant_id = note.tenant_id = connection.tenant_id = tenant
    transport = HangingTransport()
    service = EHRIntegrationService(transport)
    service.save_connection(connection)
    encounter_repository.save(encounter)
    clinical_note_repository.save(note)
    message = _failed_message(tenant, connection.id)
    message.related_encounter_id = encounter.id
    message.related_note_id = note.id
    message.idempotency_key = service._idempotency_key(connection, note)
    from src.backend.infra.db.ehr_inmemory import ehr_message_repository
    ehr_message_repository.save(message)
    now = datetime.now(timezone.utc)
    claimed = ehr_message_repository.claim_due(
        worker_id="stopped-worker", now=now, limit=1,
        lease_duration=timedelta(seconds=1), max_retries=6,
    )

    attempt = asyncio.create_task(service.retry_claimed_message(claimed[0], "stopped-worker"))
    await transport.started.wait()
    attempt.cancel()
    with pytest.raises(asyncio.CancelledError):
        await attempt
    stranded = ehr_message_repository.get(message.id)
    assert stranded.status == "processing"
    assert stranded.claimed_by == "stopped-worker"

    recovered = ehr_message_repository.claim_due(
        worker_id="replacement-worker", now=now + timedelta(seconds=2), limit=1,
        lease_duration=timedelta(minutes=2), max_retries=6,
    )
    assert len(recovered) == 1
    assert recovered[0].claimed_by == "replacement-worker"


@pytest.mark.asyncio
async def test_heartbeat_prevents_reclaim_during_long_running_send():
    tenant = f"heartbeat-{uuid4()}"
    set_current_tenant(tenant)
    encounter, note, connection = fixtures()
    encounter.tenant_id = note.tenant_id = connection.tenant_id = tenant
    transport = HangingTransport()
    service = EHRIntegrationService(transport, lease_seconds=0.15)
    service.save_connection(connection)
    encounter_repository.save(encounter)
    clinical_note_repository.save(note)
    message = _failed_message(tenant, connection.id)
    message.related_encounter_id = encounter.id
    message.related_note_id = note.id
    message.idempotency_key = service._idempotency_key(connection, note)
    from src.backend.infra.db.ehr_inmemory import ehr_message_repository
    ehr_message_repository.save(message)
    claimed = ehr_message_repository.claim_due(
        worker_id="live-worker", now=datetime.now(timezone.utc), limit=1,
        lease_duration=timedelta(seconds=0.15), max_retries=6,
    )
    attempt = asyncio.create_task(service.retry_claimed_message(claimed[0], "live-worker"))
    await transport.started.wait()
    await asyncio.sleep(0.25)

    competing = ehr_message_repository.claim_due(
        worker_id="competing-worker", now=datetime.now(timezone.utc), limit=1,
        lease_duration=timedelta(seconds=1), max_retries=6,
    )
    assert competing == []
    attempt.cancel()
    with pytest.raises(asyncio.CancelledError):
        await attempt


@pytest.mark.asyncio
async def test_manual_retry_cannot_bypass_active_worker_claim():
    tenant = f"manual-contention-{uuid4()}"
    set_current_tenant(tenant)
    encounter, note, connection = fixtures()
    encounter.tenant_id = note.tenant_id = connection.tenant_id = tenant
    transport = RecordingTransport()
    service = EHRIntegrationService(transport)
    service.save_connection(connection)
    encounter_repository.save(encounter)
    clinical_note_repository.save(note)
    message = _failed_message(tenant, connection.id)
    message.related_encounter_id = encounter.id
    message.related_note_id = note.id
    message.idempotency_key = service._idempotency_key(connection, note)
    from src.backend.infra.db.ehr_inmemory import ehr_message_repository
    ehr_message_repository.save(message)
    claimed = ehr_message_repository.claim_due(
        worker_id="automatic-worker", now=datetime.now(timezone.utc), limit=1,
        lease_duration=timedelta(minutes=2), max_retries=6,
    )
    assert len(claimed) == 1

    with pytest.raises(ValueError, match="already in progress"):
        await service.retry_message(message.id)
    assert transport.calls == []