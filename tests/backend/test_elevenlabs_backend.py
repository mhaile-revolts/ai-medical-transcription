import base64
import json
import subprocess
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient

from src.backend.config import settings
from src.backend.domain.models.clinical_encounter import ClinicalEncounter
from src.backend.domain.models.transcription_job import TranscriptJob, TranscriptJobStatus
from src.backend.infra.db.models_notes_jobs import TranscriptJobORM
from src.backend.main import app, _validate_security_configuration
from src.backend.services.encounters.service import encounter_service
from src.backend.services.transcription.backends import (
    ASRTranscription,
    DemoTranslationBackend,
    ElevenLabsASRBackend,
    _elevenlabs_language_code,
)
from src.backend.services.transcription.privacy import require_external_asr_consent
from src.backend.services.transcription.service import InMemoryTranscriptionService


def test_elevenlabs_request_uses_connected_proxy_and_returns_detected_language(tmp_path, monkeypatch):
    audio = tmp_path / "visit.m4a"
    audio.write_bytes(b"sample audio bytes")
    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["request"] = json.loads(kwargs["input"])
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps({
                "text": "Hola, how are you?",
                "language_code": "eng",
                "language_probability": 0.91,
            }),
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = ElevenLabsASRBackend().transcribe_with_metadata(str(audio))

    assert isinstance(result, ASRTranscription)
    assert result.text == "Hola, how are you?"
    assert result.language_code == "eng"
    assert result.language_probability == 0.91
    assert captured["request"]["model_id"] == "scribe_v2_medical"
    assert captured["request"]["language_code"] is None
    assert base64.b64decode(captured["request"]["audio_base64"]) == b"sample audio bytes"


def test_elevenlabs_language_override_uses_iso_language_code():
    assert _elevenlabs_language_code("es-ES") == "es"
    assert _elevenlabs_language_code("zh_CN") == "zh"
    assert _elevenlabs_language_code(None) is None
    assert _elevenlabs_language_code("auto") is None


def test_transcription_job_persists_detected_language_and_confidence(tmp_path):
    audio = tmp_path / "multilingual.m4a"
    audio.write_bytes(b"synthetic test audio")

    class DetectedLanguageBackend:
        def transcribe_with_metadata(self, audio_url, language_code=None):
            return ASRTranscription(
                text="Buenos días. Good morning.",
                language_code="eng",
                language_probability=0.87,
            )

    service = InMemoryTranscriptionService(
        asr_backend=DetectedLanguageBackend(),
        translation_backend=DemoTranslationBackend(),
    )
    job = service.create_job(audio_url=str(audio))

    assert job.result_text == "Buenos días. Good morning."
    assert job.language_code == "eng"
    assert job.language_probability == 0.87


def test_detected_language_confidence_survives_sql_model_round_trip():
    job = TranscriptJob(
        id=uuid4(),
        created_at=datetime.now(timezone.utc),
        status=TranscriptJobStatus.COMPLETED,
        audio_url="uploads/synthetic.wav",
        language_code="spa",
        language_probability=0.93,
        tenant_id="test-tenant",
    )

    restored = TranscriptJobORM.from_domain(job).to_domain()

    assert restored.language_code == "spa"
    assert restored.language_probability == 0.93


def test_elevenlabs_requires_baa_and_zero_retention_configuration(monkeypatch):
    monkeypatch.setattr(settings, "asr_backend", "elevenlabs")
    monkeypatch.setattr(settings, "require_on_prem_only", False)
    monkeypatch.setattr(settings, "elevenlabs_baa_confirmed", False)
    monkeypatch.setattr(settings, "elevenlabs_zero_retention_enabled", False)
    with pytest.raises(RuntimeError, match="ELEVENLABS_BAA_CONFIRMED"):
        _validate_security_configuration()

    monkeypatch.setattr(settings, "elevenlabs_baa_confirmed", True)
    with pytest.raises(RuntimeError, match="ELEVENLABS_ZERO_RETENTION_ENABLED"):
        _validate_security_configuration()

    monkeypatch.setattr(settings, "elevenlabs_zero_retention_enabled", True)
    monkeypatch.setattr(settings, "app_env", "test")
    _validate_security_configuration()


@pytest.mark.asyncio
async def test_audio_capabilities_discloses_external_provider(monkeypatch):
    monkeypatch.setattr(settings, "asr_backend", "elevenlabs")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/audio/capabilities")

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider_label"] == "ElevenLabs Scribe v2 Medical (cloud)"
    assert payload["external_processing"] is True
    assert payload["automatic_language_detection"] is True
    assert "Business Associate Agreement" in payload["consent_disclosure"]


@pytest.mark.asyncio
async def test_elevenlabs_routes_reject_audio_without_consent_bound_encounter(monkeypatch):
    monkeypatch.setattr(settings, "asr_backend", "elevenlabs")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        direct_job = await client.post(
            "/api/v1/transcriptions/",
            json={"audio_url": "https://example.invalid/synthetic.wav"},
        )
        upload = await client.post(
            "/api/v1/audio/upload",
            files={"file": ("synthetic.wav", b"synthetic audio", "audio/wav")},
        )

    assert direct_job.status_code == 409
    assert upload.status_code == 409


def test_elevenlabs_rejects_old_generic_recording_consent(monkeypatch):
    monkeypatch.setattr(settings, "asr_backend", "elevenlabs")
    monkeypatch.setattr(encounter_service, "is_confirmed_recording_allowed", lambda _: True)
    encounter = ClinicalEncounter(
        id=uuid4(),
        created_at=datetime.now(timezone.utc),
        consent_version="mobile-recording-consent-v1",
        tenant_id="test-tenant",
    )

    with pytest.raises(HTTPException, match="provider"):
        require_external_asr_consent(encounter)
