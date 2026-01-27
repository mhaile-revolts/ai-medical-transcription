from pathlib import Path

from httpx import AsyncClient, ASGITransport
from fastapi import status
import pytest

from src.backend.main import app
from src.backend.services.nlp import service as nlp_service_module
from src.backend.services.nlp.service import PipelineNLPService
from src.backend.services.nlp.backends import UmlsCodingBackend, DemoSOAPGeneratorBackend
from src.backend.domain.nlp.models import ClinicalEntities, ClinicalEntity

pytestmark = pytest.mark.asyncio


async def test_create_transcription_job_and_fetch_it_back():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
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

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        get_response = await ac.get(f"/api/v1/transcriptions/{job_id}")
        assert get_response.status_code == status.HTTP_200_OK

    fetched = get_response.json()
    assert fetched["id"] == job_id
    assert fetched["status"] == "COMPLETED"
    assert fetched["audio_url"] == "s3://bucket/demo.wav"
    assert fetched["target_language"] == "es-ES"
    assert fetched["translated_text"]


class StubNERBackend:
    """Test-only NER backend that returns fixed entities for coding checks."""

    def extract(self, text: str) -> ClinicalEntities:
        entities = ClinicalEntities()
        entities.diagnoses.append(
            ClinicalEntity(label="DIAGNOSIS", text="type 2 diabetes mellitus")
        )
        entities.medications.append(
            ClinicalEntity(label="MEDICATION", text="metformin")
        )
        return entities


async def test_analyze_transcription_uses_umls_coding_backend_for_codes():
    """High-level route test: /transcriptions/{id}/analyze surfaces terminology codes."""

    concepts_path = Path("tests/backend/data/demo_umls_concepts.jsonl").resolve()
    assert concepts_path.exists(), "Demo UMLS concepts file is missing"

    umls_backend = UmlsCodingBackend(concepts_path=concepts_path, min_similarity=0.5)

    original_nlp_service = nlp_service_module.nlp_service
    nlp_service_module.nlp_service = PipelineNLPService(
        ner_backend=StubNERBackend(),
        coding_backend=umls_backend,
        soap_backend=DemoSOAPGeneratorBackend(),
    )

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            create_response = await ac.post(
                "/api/v1/transcriptions/",
                json={
                    "audio_url": "s3://bucket/umls-coding.wav",
                    "language_code": "en-US",
                },
            )
            assert create_response.status_code == status.HTTP_201_CREATED
            job_id = create_response.json()["id"]

            analyze_resp = await ac.post(f"/api/v1/transcriptions/{job_id}/analyze")

        assert analyze_resp.status_code == status.HTTP_200_OK
        payload = analyze_resp.json()

        assert "codes" in payload
        codes = payload["codes"]
        assert isinstance(codes, list)
        assert any(c["code"] == "E11" for c in codes)
    finally:
        # Restore the original singleton to avoid leaking state across tests.
        nlp_service_module.nlp_service = original_nlp_service
