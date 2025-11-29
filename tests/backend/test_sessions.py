from httpx import AsyncClient
from fastapi import status

from src.backend.main import app


async def test_create_session_attach_transcription_and_analyze():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        # Create a session
        create_session_resp = await ac.post(
            "/api/v1/sessions/",
            json={"title": "Test encounter"},
        )
        assert create_session_resp.status_code == status.HTTP_201_CREATED
        session = create_session_resp.json()
        session_id = session["id"]

        # Create a transcription job
        create_job_resp = await ac.post(
            "/api/v1/transcriptions/",
            json={"audio_url": "s3://bucket/session-demo.wav", "language_code": "en-US"},
        )
        assert create_job_resp.status_code == status.HTTP_201_CREATED
        job = create_job_resp.json()
        job_id = job["id"]

        # Attach the transcription job to the session
        attach_resp = await ac.post(
            f"/api/v1/sessions/{session_id}/transcriptions",
            json={"job_id": job_id},
        )
        assert attach_resp.status_code == status.HTTP_200_OK
        updated_session = attach_resp.json()
        assert job_id in updated_session["transcription_job_ids"]

        # Analyze the session
        analyze_resp = await ac.post(f"/api/v1/sessions/{session_id}/analyze")
        assert analyze_resp.status_code == status.HTTP_200_OK

        payload = analyze_resp.json()
        assert "entities" in payload
        assert "soap_note" in payload
        assert "subjective" in payload["soap_note"]
        assert "text" in payload["soap_note"]["subjective"]
