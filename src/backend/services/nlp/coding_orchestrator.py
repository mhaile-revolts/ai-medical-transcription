from __future__ import annotations

from typing import List, Tuple

from src.backend.domain.nlp.coding_models import (
    BillingRiskLevel,
    BillingRiskSummary,
    CodeAssignment,
    CodeSystem,
)
from src.backend.domain.nlp.models import ClinicalEntities, SOAPNote


class CodingOrchestrator:
    """Derive code assignments and a naive billing risk summary.

    This layer sits on top of the existing CodingBackend (which may already
    populate `ClinicalEntity.code`) and turns those codes into richer
    structures, while also synthesizing very simple billing risk heuristics.
    """

    def assign_codes(
        self,
        entities: ClinicalEntities,
        soap_note: SOAPNote | None = None,
    ) -> Tuple[List[CodeAssignment], BillingRiskSummary | None]:
        assignments: List[CodeAssignment] = []

        def _add_from_bucket(bucket, category: str) -> None:
            for ent in bucket:
                if not ent.text:
                    continue
                # Try to guess coding system from the code pattern; fall back to OTHER.
                system = CodeSystem.OTHER
                if ent.code:
                    if ent.code[0].isalpha() and any(c.isdigit() for c in ent.code):
                        system = CodeSystem.ICD10
                assignments.append(
                    CodeAssignment(
                        code_system=system,
                        code=ent.code or "UNCODED",
                        display=None,
                        source_entity_label=ent.label,
                        source_text=ent.text,
                        confidence=None,
                        category=category,
                    )
                )

        _add_from_bucket(entities.diagnoses, "diagnosis")
        _add_from_bucket(entities.medications, "medication")
        _add_from_bucket(entities.symptoms, "symptom")

        # Extremely minimal CPT-style procedure hints based on SOAP text.
        if soap_note is not None:
            text = " ".join(
                [
                    soap_note.subjective.text,
                    soap_note.objective.text,
                    soap_note.assessment.text,
                    soap_note.plan.text,
                ]
            ).lower()
            if "follow-up" in text or "follow up" in text:
                assignments.append(
                    CodeAssignment(
                        code_system=CodeSystem.CPT,
                        code="99213_DEMO",
                        display="Established patient office visit (demo)",
                        source_entity_label="PROCEDURE",
                        source_text="follow-up visit",
                        confidence=None,
                        category="procedure",
                    )
                )

        billing_risk = self._compute_billing_risk(assignments)
        return assignments, billing_risk

    def _compute_billing_risk(self, assignments: List[CodeAssignment]) -> BillingRiskSummary | None:
        if not assignments:
            return BillingRiskSummary(
                level=BillingRiskLevel.HIGH,
                reasons=["No codes assigned; potential under-coding or missing documentation."],
                suggested_actions=["Review encounter for billable diagnoses and procedures."],
            )

        has_dx = any(a.category == "diagnosis" for a in assignments)
        has_proc = any(a.category == "procedure" for a in assignments)

        if has_dx and has_proc:
            return BillingRiskSummary(
                level=BillingRiskLevel.LOW,
                reasons=["Both diagnoses and procedures are present."],
                suggested_actions=["Consider reviewing E/M level for optimization where allowed."],
            )

        if has_dx or has_proc:
            return BillingRiskSummary(
                level=BillingRiskLevel.MEDIUM,
                reasons=["Only diagnoses or only procedures present."],
                suggested_actions=["Check whether additional supporting codes are appropriate."],
            )

        return BillingRiskSummary(
            level=BillingRiskLevel.HIGH,
            reasons=["Only symptom/other codes present."],
            suggested_actions=["Ensure definitive diagnoses and procedures are captured when clinically appropriate."],
        )


coding_orchestrator = CodingOrchestrator()
