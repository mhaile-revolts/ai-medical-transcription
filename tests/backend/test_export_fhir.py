from httpx import AsyncClient, ASGITransport
from fastapi import status
import pytest

from src.backend.main import app

pytestmark = pytest.mark.asyncio


async def test_export_transcription_as_fhir_bundle():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # Create a transcription job first
        create_resp = await ac.post(
            "/api/v1/transcriptions/",
            json={"audio_url": "s3://bucket/export-demo.wav", "language_code": "en-US"},
        )
        assert create_resp.status_code == status.HTTP_201_CREATED
        job = create_resp.json()
        job_id = job["id"]

        # Export as FHIR bundle
        export_resp = await ac.post(f"/api/v1/transcriptions/{job_id}/export/fhir")
        assert export_resp.status_code == status.HTTP_200_OK

        payload = export_resp.json()
        assert "bundle" in payload
    bundle = payload["bundle"]
    assert bundle["resourceType"] == "Bundle"
    assert bundle["type"] == "document"
    assert bundle["id"] == job_id
    assert isinstance(bundle.get("entry"), list)
    assert len(bundle["entry"]) >= 1


def test_fhir_export_uses_code_system_for_coding():
    """DemoFHIRExporter should map code_system hints into FHIR Coding.system."""

    from uuid import uuid4

    from src.backend.domain.nlp.models import ClinicalEntities, ClinicalEntity, SOAPNote, SOAPSection
    from src.backend.services.ehr.service import DemoFHIRExporter

    entities = ClinicalEntities()
    entities.diagnoses.append(
        ClinicalEntity(
            label="DIAGNOSIS",
            text="type 2 diabetes mellitus",
            code="E11",
            code_system="ICD10",
            code_display="Type 2 diabetes mellitus",
        )
    )
    entities.medications.append(
        ClinicalEntity(
            label="MEDICATION",
            text="metformin",
            code="860975",
            code_system="RxNorm",
            code_display="Metformin",
        )
    )

    soap = SOAPNote(
        subjective=SOAPSection(text="Subjective"),
        objective=SOAPSection(text="Objective"),
        assessment=SOAPSection(text="Assessment"),
        plan=SOAPSection(text="Plan"),
    )

    exporter = DemoFHIRExporter()
    bundle = exporter.build_fhir_bundle(job_id=uuid4(), entities=entities, soap_note=soap)

    entries = bundle.get("entry", [])
    cond = next(r["resource"] for r in entries if r["resource"]["resourceType"] == "Condition")
    cond_coding = cond["code"]["coding"][0]
    assert cond_coding["code"] == "E11"
    assert "system" in cond_coding
    assert "icd-10" in cond_coding["system"].lower()
    assert cond_coding.get("display") == "Type 2 diabetes mellitus"

    med = next(
        r["resource"]
        for r in entries
        if r["resource"]["resourceType"] == "MedicationStatement"
    )
    med_coding = med["medicationCodeableConcept"]["coding"][0]
    assert med_coding["code"] == "860975"
    assert "system" in med_coding
    assert "rxnorm" in med_coding["system"].lower()
    assert med_coding.get("display") == "Metformin"
