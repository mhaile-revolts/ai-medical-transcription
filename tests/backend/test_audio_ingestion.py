from starlette.testclient import TestClient
from httpx import AsyncClient
from fastapi import status

from src.backend.main import app


async def test_upload_audio_creates_transcription_job():
    client = AsyncClient(app=app, base_url="http://test")
    try:
        files = {"file": ("demo.wav", b"fake-binary", "audio/wav")}
        response = await client.post(
            "/api/v1/audio/upload",
            files=files,
            params={"language_code": "en-US", "target_language": "es-ES"},
        )
    finally:
        await client.aclose()

    assert response.status_code == status.HTTP_201_CREATED
    payload = response.json()
    job = payload["job"]
    # audio_url is now a filesystem path pointing to the persisted upload
    assert job["audio_url"].endswith("demo.wav")
    assert job["language_code"] == "en-US"
    assert job["target_language"] == "es-ES"
    assert job["result_text"]
    assert job["translated_text"]
    # A clinical encounter should have been created and returned
    assert "encounter_id" in payload
    assert payload["encounter_id"] is not None


def test_live_transcription_websocket():
    client = TestClient(app)

    with client.websocket_connect("/api/v1/audio/ws") as websocket:
        websocket.send_bytes(b"hello")
        message = websocket.receive_json()

    assert "partial_text" in message
    assert message["total_bytes"] == len(b"hello")
