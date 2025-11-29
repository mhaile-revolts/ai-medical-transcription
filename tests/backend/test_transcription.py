from httpx import AsyncClient
from fastapi import status

from src.backend.main import app


async def test_create_transcription_job_and_fetch_it_back():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        create_response = await ac.post(
            "/api/v1/transcriptions/",
            json={
                "audio_url": "s3://bucket/demo.wav",
                "language_code": "en-US",
                "target_language": "es-ES",
            },
        )
    assert create_response.status_code == status.HTTP_201_CREATED

    created = create_response.json()
    assert created["audio_url"] == "s3://bucket/demo.wav"
    assert created["language_code"] == "en-US"
    assert created["target_language"] == "es-ES"
    assert created["status"] == "COMPLETED"
    assert created["result_text"]
    assert created["translated_text"]

    job_id = created["id"]

    async with AsyncClient(app=app, base_url="http://test") as ac:
        get_response = await ac.get(f"/api/v1/transcriptions/{job_id}")
    assert get_response.status_code == status.HTTP_200_OK

    fetched = get_response.json()
    assert fetched["id"] == job_id
    assert fetched["status"] == "COMPLETED"
    assert fetched["audio_url"] == "s3://bucket/demo.wav"
    assert fetched["target_language"] == "es-ES"
    assert fetched["translated_text"]
