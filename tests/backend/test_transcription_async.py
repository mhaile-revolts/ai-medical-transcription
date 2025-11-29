from uuid import UUID

from httpx import AsyncClient
from fastapi import status

from src.backend.domain.models.transcription_job import TranscriptJobStatus
from src.backend.main import app


async def test_create_transcription_job_async_and_poll_until_completed():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        create_response = await ac.post(
            "/api/v1/transcriptions/async",
            json={
                "audio_url": "s3://bucket/async-demo.wav",
                "language_code": "en-US",
                "target_language": "es-ES",
            },
        )
        assert create_response.status_code == status.HTTP_202_ACCEPTED

        job = create_response.json()
        # Validate basic shape
        assert UUID(job["id"])  # valid UUID
        assert job["status"] == TranscriptJobStatus.PENDING.value

        job_id = job["id"]

        # Since we use FastAPI BackgroundTasks, by the time the request
        # completes the background task may or may not have finished.
        # We poll a few times to account for this.
        final_status = job["status"]
        for _ in range(3):
            get_response = await ac.get(f"/api/v1/transcriptions/{job_id}")
            assert get_response.status_code == status.HTTP_200_OK
            polled = get_response.json()
            final_status = polled["status"]
            if final_status == TranscriptJobStatus.COMPLETED.value:
                assert polled["result_text"]
                if polled.get("target_language"):
                    assert polled["translated_text"]
                break

        assert final_status == TranscriptJobStatus.COMPLETED.value
