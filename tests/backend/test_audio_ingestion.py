from starlette.testclient import TestClient
from httpx import AsyncClient, ASGITransport
from fastapi import status
import pytest

from src.backend.main import app

pytestmark = pytest.mark.asyncio


async def test_upload_audio_creates_transcription_job():
    client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
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
    with TestClient(app) as client:
        with client.websocket_connect("/api/v1/audio/ws") as websocket:
            websocket.send_bytes(b"hello")
            message = websocket.receive_json()
            # Ask server to finalize and close cleanly to avoid runtime errors on shutdown.
            websocket.send_text("stop")

            assert "partial_text" in message
            assert message["total_bytes"] == len(b"hello")
