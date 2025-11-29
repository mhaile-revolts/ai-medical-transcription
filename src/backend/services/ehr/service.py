from __future__ import annotations

from typing import Any, Dict
from uuid import UUID

from src.backend.domain.nlp.models import ClinicalEntities, SOAPNote


class DemoFHIRExporter:
    """Very lightweight FHIR/HL7 export stub.

    In a real deployment this would construct full FHIR resources or HL7
    messages. For now it builds a small FHIR-like bundle capturing the SOAP
    note and key entities so downstream integration can be tested.
    """

    def build_fhir_bundle(
        self,
        *,
        job_id: UUID,
        entities: ClinicalEntities,
        soap_note: SOAPNote,
    ) -> Dict[str, Any]:
        conditions = [
            {
                "resourceType": "Condition",
                "code": {
                    "text": e.text,
                    "coding": ([{"code": e.code}] if e.code else []),
                },
            }
            for e in entities.diagnoses
        ]
        medications = [
            {
                "resourceType": "MedicationStatement",
                "medicationCodeableConcept": {"text": e.text},
            }
            for e in entities.medications
        ]

        composition = {
            "resourceType": "Composition",
            "status": "final",
            "title": "Clinical SOAP Note",
            "section": [
                {"title": "Subjective", "text": {"status": "generated", "div": soap_note.subjective.text}},
                {"title": "Objective", "text": {"status": "generated", "div": soap_note.objective.text}},
                {"title": "Assessment", "text": {"status": "generated", "div": soap_note.assessment.text}},
                {"title": "Plan", "text": {"status": "generated", "div": soap_note.plan.text}},
            ],
        }

        entries = [{"resource": composition}] + [{"resource": r} for r in conditions + medications]

        bundle: Dict[str, Any] = {
            "resourceType": "Bundle",
            "type": "document",
            "id": str(job_id),
            "entry": entries,
        }
        return bundle


demo_fhir_exporter = DemoFHIRExporter()
