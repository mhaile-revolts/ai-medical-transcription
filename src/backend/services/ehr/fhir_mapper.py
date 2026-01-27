from __future__ import annotations

from typing import Any, Dict, List
from uuid import UUID

from src.backend.domain.models.clinical_encounter import ClinicalEncounter
from src.backend.domain.nlp.models import ClinicalEntities, SOAPNote


def build_coding(
    code: str | None,
    system_hint: str | None = None,
    display: str | None = None,
) -> List[Dict[str, Any]]:
    """Build a minimal FHIR Coding list from a code + optional system hint.

    This is factored out so both demo and production exporters share mapping
    logic.
    """

    if not code:
        return []

    system_uri: str | None = None
    if system_hint:
        norm = system_hint.strip().upper()
        if "ICD" in norm:
            system_uri = "http://hl7.org/fhir/sid/icd-10-cm"
        elif "SNOMED" in norm:
            system_uri = "http://snomed.info/sct"
        elif "RXNORM" in norm:
            system_uri = "http://www.nlm.nih.gov/research/umls/rxnorm"

    # Heuristic fallback: codes starting with a letter and containing digits are
    # treated as ICD-10-CM for demo purposes (e.g. "E11").
    if system_uri is None and code[0].isalpha() and any(ch.isdigit() for ch in code):
        system_uri = "http://hl7.org/fhir/sid/icd-10-cm"

    coding: Dict[str, Any] = {"code": code}
    if system_uri:
        coding["system"] = system_uri
    if display:
        coding["display"] = display
    return [coding]


def build_conditions(entities: ClinicalEntities) -> List[Dict[str, Any]]:
    return [
        {
            "resourceType": "Condition",
            "code": {
                "text": e.text,
                "coding": build_coding(e.code, e.code_system, e.code_display),
            },
        }
        for e in entities.diagnoses
    ]


def build_medications(entities: ClinicalEntities) -> List[Dict[str, Any]]:
    return [
        {
            "resourceType": "MedicationStatement",
            "medicationCodeableConcept": {
                "text": e.text,
                "coding": build_coding(e.code, e.code_system, e.code_display),
            },
        }
        for e in entities.medications
    ]


def build_composition(soap_note: SOAPNote, encounter: ClinicalEncounter | None = None) -> Dict[str, Any]:
    # Encounter linkage can be added later via subject/context references.
    return {
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


def build_document_bundle(
    *,
    bundle_id: UUID,
    entities: ClinicalEntities,
    soap_note: SOAPNote,
    encounter: ClinicalEncounter | None = None,
) -> Dict[str, Any]:
    """Build a FHIR document-style Bundle from SOAP note and entities."""

    composition = build_composition(soap_note, encounter=encounter)
    conditions = build_conditions(entities)
    medications = build_medications(entities)

    entries = [{"resource": composition}] + [{"resource": r} for r in conditions + medications]
    bundle: Dict[str, Any] = {
        "resourceType": "Bundle",
        "type": "document",
        "id": str(bundle_id),
        "entry": entries,
    }
    return bundle
