from httpx import AsyncClient
from fastapi import status

from src.backend.main import app


async def test_export_transcription_as_fhir_bundle():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        # Create a transcription job first
        create_resp = await ac.post(
            "/api/v1/transcriptions/",
            json={"audio_url": "s3://bucket/export-demo.wav", "language_code": "en-US"},
        )
        assert create_resp.status_code == status.HTTP_201_CREATED
        job = create_resp.json()
        job_id = job["id"]

        # Export as FHIR bundle
        export_resp = await ac.post(f"/api/v1/transcriptions/{job_id}/export/fhir")
        assert export_resp.status_code == status.HTTP_200_OK

        payload = export_resp.json()
        assert "bundle" in payload
        bundle = payload["bundle"]
        assert bundle["resourceType"] == "Bundle"
        assert bundle["type"] == "document"
        assert bundle["id"] == job_id
        assert isinstance(bundle.get("entry"), list)
        assert len(bundle["entry"]) >= 1
