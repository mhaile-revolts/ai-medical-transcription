from httpx import AsyncClient
from fastapi import status

from src.backend.main import app


async def test_multitenancy_isolation_for_encounters_and_transcriptions():
    """Data created under one tenant should not be visible to another.

    This test exercises both the encounters and transcriptions flows with
    different X-Tenant-ID headers.
    """

    async with AsyncClient(app=app, base_url="http://test") as ac:
        # Tenant A: create an encounter via API
        create_enc_a = await ac.post(
            "/api/v1/encounters/",
            json={"patient_id": "pat-a", "title": "Encounter A"},
            headers={"X-Tenant-ID": "tenant-a"},
        )
        assert create_enc_a.status_code == status.HTTP_201_CREATED
        enc_a = create_enc_a.json()

        # Tenant A: create a transcription job
        create_job_a = await ac.post(
            "/api/v1/transcriptions/",
            json={"audio_url": "s3://bucket/a.wav", "language_code": "en-US"},
            headers={"X-Tenant-ID": "tenant-a"},
        )
        assert create_job_a.status_code == status.HTTP_201_CREATED

        # Tenant B: create its own encounter and transcription
        create_enc_b = await ac.post(
            "/api/v1/encounters/",
            json={"patient_id": "pat-b", "title": "Encounter B"},
            headers={"X-Tenant-ID": "tenant-b"},
        )
        assert create_enc_b.status_code == status.HTTP_201_CREATED
        enc_b = create_enc_b.json()

        create_job_b = await ac.post(
            "/api/v1/transcriptions/",
            json={"audio_url": "s3://bucket/b.wav", "language_code": "en-US"},
            headers={"X-Tenant-ID": "tenant-b"},
        )
        assert create_job_b.status_code == status.HTTP_201_CREATED

        # Listing encounters under tenant-a should only return tenant-a encounters
        list_a = await ac.get(
            "/api/v1/encounters/",
            headers={"X-Tenant-ID": "tenant-a"},
        )
        assert list_a.status_code == status.HTTP_200_OK
        encs_a = list_a.json()
        assert any(e["id"] == enc_a["id"] for e in encs_a)
        assert all(e["patient_id"] != enc_b["patient_id"] for e in encs_a)

        # Listing encounters under tenant-b should only return tenant-b encounters
        list_b = await ac.get(
            "/api/v1/encounters/",
            headers={"X-Tenant-ID": "tenant-b"},
        )
        assert list_b.status_code == status.HTTP_200_OK
        encs_b = list_b.json()
        assert any(e["id"] == enc_b["id"] for e in encs_b)
        assert all(e["patient_id"] != enc_a["patient_id"] for e in encs_b)

        # Cross-tenant get by ID should 404 (encounter is not visible outside its tenant)
        get_enc_a_as_b = await ac.get(
            f"/api/v1/encounters/{enc_a['id']}",
            headers={"X-Tenant-ID": "tenant-b"},
        )
        assert get_enc_a_as_b.status_code == status.HTTP_404_NOT_FOUND

        get_enc_b_as_a = await ac.get(
            f"/api/v1/encounters/{enc_b['id']}",
            headers={"X-Tenant-ID": "tenant-a"},
        )
        assert get_enc_b_as_a.status_code == status.HTTP_404_NOT_FOUND
