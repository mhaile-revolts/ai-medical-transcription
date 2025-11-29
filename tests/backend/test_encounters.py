from uuid import UUID

from src.backend.services.encounters.service import encounter_service
from src.backend.domain.models.clinical_encounter import EncounterStatus
from src.backend.main import app
from httpx import AsyncClient
from fastapi import status


def test_create_encounter_and_attach_job():
    encounter = encounter_service.create_encounter(
        clinician_id="clin-1",
        patient_id="pat-1",
        title="Test encounter",
    )
    assert isinstance(encounter.id, UUID)
    assert encounter.status == EncounterStatus.CREATED

    # Attach a fake job UUID and ensure status transitions to IN_PROGRESS
    fake_job_id = UUID(int=1)
    updated = encounter_service.attach_job(encounter_id=encounter.id, job_id=fake_job_id)
    assert fake_job_id in updated.transcription_job_ids
    assert updated.status == EncounterStatus.IN_PROGRESS


def test_upsert_note_advances_status():
    encounter = encounter_service.create_encounter(
        clinician_id="clin-2",
        patient_id="pat-2",
        title="Second encounter",
    )

    note = encounter_service.upsert_note_from_soap(
        encounter_id=encounter.id,
        subjective="subj",
        objective="obj",
        assessment="asm",
        plan="plan",
        editor_id="clin-2",
        finalize=False,
    )

    assert note.encounter_id == encounter.id
    # Encounter should now be READY_FOR_REVIEW
    updated_encounter = encounter_service.get_encounter(encounter.id)
    assert updated_encounter is not None
    assert updated_encounter.status == EncounterStatus.READY_FOR_REVIEW

    # Finalizing should move status to FINALIZED
    encounter_service.upsert_note_from_soap(
        encounter_id=encounter.id,
        subjective="subj2",
        objective="obj2",
        assessment="asm2",
        plan="plan2",
        editor_id="clin-2",
        finalize=True,
    )
    finalized = encounter_service.get_encounter(encounter.id)
    assert finalized is not None
    assert finalized.status == EncounterStatus.FINALIZED


async def test_create_and_get_encounter_via_api():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        # auth is disabled by default in tests; get_current_user will synthesize an admin
        create_resp = await ac.post(
            "/api/v1/encounters/",
            json={"patient_id": "pat-api", "title": "API encounter"},
        )
        assert create_resp.status_code == status.HTTP_201_CREATED
        encounter = create_resp.json()
        encounter_id = encounter["id"]

        get_resp = await ac.get(f"/api/v1/encounters/{encounter_id}")
        assert get_resp.status_code == status.HTTP_200_OK
        body = get_resp.json()
        assert body["encounter"]["id"] == encounter_id
