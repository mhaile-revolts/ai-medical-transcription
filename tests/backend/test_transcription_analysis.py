from httpx import AsyncClient
from fastapi import status

from src.backend.main import app


async def test_analyze_completed_transcription_job():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        # First create a synchronous transcription job
        create_resp = await ac.post(
            "/api/v1/transcriptions/",
            json={
                "audio_url": "s3://bucket/analysis-demo.wav",
                "language_code": "en-US",
            },
        )
        assert create_resp.status_code == status.HTTP_201_CREATED
        job = create_resp.json()
        job_id = job["id"]

        # Now analyze that job
        analyze_resp = await ac.post(f"/api/v1/transcriptions/{job_id}/analyze")
        assert analyze_resp.status_code == status.HTTP_200_OK

        payload = analyze_resp.json()
        assert "entities" in payload
        assert "soap_note" in payload
        assert "subjective" in payload["soap_note"]
        assert "text" in payload["soap_note"]["subjective"]
