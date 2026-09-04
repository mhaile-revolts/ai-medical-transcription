from __future__ import annotations

import httpx
import pytest

from src.backend.config import settings
from src.backend.services.ehr.smart_fhir_service import (
    SmartFHIRService,
    SmartFHIRUnavailable,
)


def test_normalizes_fhir_patient_and_encounter() -> None:
    patient = SmartFHIRService.normalize_patient(
        {
            "resourceType": "Patient",
            "id": "epic-patient-1",
            "name": [{"given": ["Ada"], "family": "Lovelace"}],
            "birthDate": "1980-12-10",
            "gender": "female",
        }
    )
    encounter = SmartFHIRService.normalize_encounter(
        {
            "resourceType": "Encounter",
            "id": "epic-encounter-1",
            "status": "in-progress",
            "type": [{"text": "Office visit"}],
            "period": {"start": "2026-09-04T14:00:00Z"},
        }
    )

    assert patient.display_name == "Ada Lovelace"
    assert patient.birth_date == "1980-12-10"
    assert encounter.status == "in-progress"
    assert encounter.type == "Office visit"


@pytest.mark.asyncio
async def test_demo_mode_uses_clearly_synthetic_records(monkeypatch) -> None:
    monkeypatch.setattr(settings, "app_mode", "demo")
    service = SmartFHIRService()

    patient = await service.get_patient("12345")
    encounters = await service.active_encounters("12345")

    assert patient.source == "demo-fixture"
    assert patient.display_name.startswith("Synthetic demo patient")
    assert encounters[0].id == "demo-active-12345"


@pytest.mark.asyncio
async def test_production_fails_closed_without_smart_configuration(monkeypatch) -> None:
    monkeypatch.setattr(settings, "app_mode", "durable")
    monkeypatch.setattr(settings, "ochin_smart_fhir_base_url", None)
    monkeypatch.setattr(settings, "ochin_smart_issuer", None)
    monkeypatch.setattr(settings, "ochin_smart_client_id", None)

    with pytest.raises(SmartFHIRUnavailable, match="not configured"):
        await SmartFHIRService().get_patient("patient-1")


@pytest.mark.asyncio
async def test_active_encounters_filters_out_finished_visits(monkeypatch) -> None:
    monkeypatch.setattr(settings, "app_mode", "durable")
    monkeypatch.setattr(settings, "ochin_smart_fhir_base_url", "https://fhir.example.test")
    monkeypatch.setattr(settings, "ochin_smart_issuer", "https://issuer.example.test")
    monkeypatch.setattr(settings, "ochin_smart_client_id", "test-client")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "resourceType": "Bundle",
                "entry": [
                    {"resource": {"resourceType": "Encounter", "id": "active", "status": "in-progress"}},
                    {"resource": {"resourceType": "Encounter", "id": "done", "status": "finished"}},
                ],
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        encounters = await SmartFHIRService(client).active_encounters("patient-1")

    assert [encounter.id for encounter in encounters] == ["active"]