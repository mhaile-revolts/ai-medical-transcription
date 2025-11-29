from httpx import AsyncClient
from fastapi import status

from src.backend.main import app


async def test_nlp_analyze_returns_entities_and_soap_note():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.post(
            "/api/v1/nlp/analyze",
            json={"transcript": "The patient has diabetes and takes metformin."},
        )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()

    assert "entities" in data
    assert "soap_note" in data

    diagnoses = data["entities"]["diagnoses"]
    meds = data["entities"]["medications"]
    assert any("diabetes" in d["text"] for d in diagnoses)
    assert any("metformin" in m["text"] for m in meds)

    soap = data["soap_note"]
    assert "Subjective summary" in soap["subjective"]["text"]
