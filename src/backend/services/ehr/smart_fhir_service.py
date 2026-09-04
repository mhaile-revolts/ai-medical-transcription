"""Minimal SMART on FHIR read client used by the clinician confirmation flow."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional
from urllib.parse import quote

import httpx

from src.backend.config import settings


class SmartFHIRUnavailable(RuntimeError):
    """Raised when SMART metadata is absent or its FHIR server cannot be used."""


@dataclass(frozen=True)
class SmartPatient:
    id: str
    display_name: str
    birth_date: Optional[str]
    sex: Optional[str]
    source: str = "smart-fhir"


@dataclass(frozen=True)
class SmartEncounter:
    id: str
    status: str
    type: Optional[str]
    period_start: Optional[str]


ACTIVE_ENCOUNTER_STATUSES = frozenset({"arrived", "triaged", "in-progress", "onleave"})


class SmartFHIRService:
    """FHIR R4 read client with an injectable ``httpx.AsyncClient`` for tests."""

    def __init__(self, client: Optional[httpx.AsyncClient] = None) -> None:
        self._client = client

    def _base_url(self) -> str:
        # Issuer/client metadata are required as a guard against accidentally
        # treating an arbitrary FHIR endpoint as the OCHIN SMART integration.
        if not (settings.ochin_smart_fhir_base_url and settings.ochin_smart_issuer and settings.ochin_smart_client_id):
            raise SmartFHIRUnavailable("OCHIN SMART on FHIR is not configured")
        return settings.ochin_smart_fhir_base_url.rstrip("/")

    async def _get_json(self, path: str) -> dict[str, Any]:
        url = f"{self._base_url()}/{path.lstrip('/')}"
        try:
            if self._client is not None:
                response = await self._client.get(url, headers={"Accept": "application/fhir+json"})
            else:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.get(url, headers={"Accept": "application/fhir+json"})
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise SmartFHIRUnavailable("OCHIN SMART FHIR request failed") from exc
        if not isinstance(payload, dict):
            raise SmartFHIRUnavailable("OCHIN SMART FHIR response was invalid")
        return payload

    @staticmethod
    def normalize_patient(resource: dict[str, Any]) -> SmartPatient:
        identifier = resource.get("id")
        if resource.get("resourceType") != "Patient" or not isinstance(identifier, str) or not identifier:
            raise ValueError("FHIR response is not a Patient")
        names = resource.get("name") or []
        name = names[0] if names and isinstance(names[0], dict) else {}
        display_name = name.get("text") or " ".join(
            [*(name.get("given") or []), name.get("family") or ""]
        ).strip() or identifier
        return SmartPatient(identifier, str(display_name), resource.get("birthDate"), resource.get("gender"))

    @staticmethod
    def normalize_encounter(resource: dict[str, Any]) -> SmartEncounter:
        identifier, status = resource.get("id"), resource.get("status")
        if resource.get("resourceType") != "Encounter" or not isinstance(identifier, str) or not isinstance(status, str):
            raise ValueError("FHIR response is not an Encounter")
        coding = ((resource.get("type") or [{}])[0].get("coding") or [{}])[0]
        kind = coding.get("display") or ((resource.get("type") or [{}])[0].get("text"))
        period = resource.get("period") or {}
        return SmartEncounter(identifier, status.lower(), str(kind) if kind else None, period.get("start"))

    async def get_patient(self, patient_id: str) -> SmartPatient:
        if settings.app_mode == "demo":
            return SmartPatient(patient_id, f"Synthetic demo patient {patient_id}", "1970-01-01", "unknown", "demo-fixture")
        return self.normalize_patient(await self._get_json(f"Patient/{quote(patient_id, safe='')}"))

    async def active_encounters(self, patient_id: str) -> list[SmartEncounter]:
        if settings.app_mode == "demo":
            return [SmartEncounter(f"demo-active-{patient_id}", "in-progress", "Synthetic demo visit", "2024-01-01T00:00:00Z")]
        bundle = await self._get_json(f"Encounter?patient={quote(patient_id, safe='')}")
        entries = bundle.get("entry") or []
        return [
            encounter for entry in entries if isinstance(entry, dict) and isinstance(entry.get("resource"), dict)
            for encounter in [self.normalize_encounter(entry["resource"])]
            if encounter.status in ACTIVE_ENCOUNTER_STATUSES
        ]


smart_fhir_service = SmartFHIRService()