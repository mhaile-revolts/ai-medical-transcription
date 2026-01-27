from pathlib import Path

from httpx import AsyncClient, ASGITransport
from fastapi import status
import pytest

from src.backend.main import app
from src.backend.config import settings

pytestmark = pytest.mark.asyncio


async def test_nlp_debug_code_uses_umls_concepts():
    """The /nlp/debug/code endpoint should surface the best terminology match."""

    concepts_path = Path("tests/backend/data/demo_umls_concepts.jsonl").resolve()
    assert concepts_path.exists(), "Demo UMLS concepts file is missing"

    # Point settings at the demo concepts file so UmlsCodingBackend can load it.
    settings.umls_concepts_path = concepts_path

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/v1/nlp/debug/code",
            json={"text": "type 2 diabetes"},
        )

    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()

    assert "best_match" in data
    best = data["best_match"]
    assert best is not None
    assert best["code"] == "E11"
    assert best["system"] in {"ICD10", "ICD10CM", "ICD-10"}
    assert 0.0 <= best["similarity"] <= 1.0