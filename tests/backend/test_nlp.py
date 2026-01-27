from httpx import AsyncClient, ASGITransport
from fastapi import status
import pytest

from src.backend.main import app

pytestmark = pytest.mark.asyncio


async def test_nlp_analyze_returns_entities_soap_and_terminology():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post(
            "/api/v1/nlp/analyze",
            json={"transcript": "The patient has diabetes and takes metformin."},
        )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()

    # Core NLP outputs still present
    assert "entities" in data
    assert "soap_note" in data

    diagnoses = data["entities"]["diagnoses"]
    meds = data["entities"]["medications"]
    assert any("diabetes" in d["text"] for d in diagnoses)
    assert any("metformin" in m["text"] for m in meds)

    soap = data["soap_note"]
    assert "Subjective summary" in soap["subjective"]["text"]

    # Terminology / coding outputs
    assert "codes" in data
    assert isinstance(data["codes"], list)
    # We expect at least one code assignment (e.g., for diabetes)
    assert len(data["codes"]) >= 1
    first_code = data["codes"][0]
    assert "code" in first_code
    assert "code_system" in first_code
    assert "source_text" in first_code

    # Billing risk summary is advisory but should be present
    assert "billing_risk" in data
    billing_risk = data["billing_risk"]
    assert billing_risk is None or isinstance(billing_risk, dict)
    if billing_risk is not None:
        assert billing_risk["level"] in {"LOW", "MEDIUM", "HIGH"}
