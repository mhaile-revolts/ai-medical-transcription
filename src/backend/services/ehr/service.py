from __future__ import annotations

from typing import Any, Dict
from uuid import UUID

from src.backend.domain.nlp.models import ClinicalEntities, SOAPNote
from src.backend.services.ehr import fhir_mapper


class DemoFHIRExporter:
    """Very lightweight FHIR/HL7 export stub.

    In a real deployment this would construct full FHIR resources or HL7
    messages. For now it builds a small FHIR-like bundle capturing the SOAP
    note and key entities so downstream integration can be tested.
    """

    def _build_coding(
        self,
        code: str | None,
        system_hint: str | None = None,
        display: str | None = None,
    ) -> list[Dict[str, Any]]:
        """Delegate to shared FHIR coding builder for backwards compatibility."""

        return fhir_mapper.build_coding(code, system_hint, display)

    def build_fhir_bundle(
        self,
        *,
        job_id: UUID,
        entities: ClinicalEntities,
        soap_note: SOAPNote,
    ) -> Dict[str, Any]:
        """Build a FHIR document bundle via shared mapper utilities."""

        return fhir_mapper.build_document_bundle(
            bundle_id=job_id,
            entities=entities,
            soap_note=soap_note,
            encounter=None,
        )


demo_fhir_exporter = DemoFHIRExporter()
