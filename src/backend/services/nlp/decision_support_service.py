from __future__ import annotations

from typing import List

from src.backend.domain.nlp.decision_support import (
    DecisionSupportSuggestion,
    SuggestionSeverity,
    SuggestionType,
)
from src.backend.domain.nlp.models import ClinicalEntities, SOAPNote


class DecisionSupportService:
    """Very small rule-based CDS layer.

    This is intentionally simplistic and meant as a placeholder for a future
    LLM+RAG implementation. It should always be treated as advisory only.
    """

    def suggest(self, entities: ClinicalEntities, soap_note: SOAPNote | None = None) -> List[DecisionSupportSuggestion]:
        suggestions: List[DecisionSupportSuggestion] = []

        has_diabetes_dx = any("diabetes" in (e.text or "").lower() for e in entities.diagnoses)
        has_metformin = any("metformin" in (e.text or "").lower() for e in entities.medications)

        # Simple diabetes/medication bundle
        if has_diabetes_dx and not has_metformin:
            suggestions.append(
                DecisionSupportSuggestion.new(
                    type=SuggestionType.MED_ADJUSTMENT,
                    severity=SuggestionSeverity.INFO,
                    summary="Diabetes diagnosis without metformin detected.",
                    details=(
                        "Consider whether first-line therapy such as metformin or other "
                        "appropriate agents is indicated based on guidelines and patient context."
                    ),
                    evidence_refs=["demo-guideline-diabetes-1"],
                )
            )

        if has_metformin and not has_diabetes_dx:
            suggestions.append(
                DecisionSupportSuggestion.new(
                    type=SuggestionType.CONTRAINDICATION,
                    severity=SuggestionSeverity.WARNING,
                    summary="Metformin mentioned without an obvious diabetes diagnosis.",
                    details="Verify indication and ensure documentation of the underlying condition.",
                    evidence_refs=["demo-guideline-diabetes-2"],
                )
            )

        if has_diabetes_dx and has_metformin:
            suggestions.append(
                DecisionSupportSuggestion.new(
                    type=SuggestionType.DIFFERENTIAL,
                    severity=SuggestionSeverity.INFO,
                    summary="Diabetes on treatment – consider labs and monitoring.",
                    details="Ensure recent HbA1c, renal function, and follow-up plan are documented.",
                    evidence_refs=["demo-guideline-diabetes-3"],
                )
            )

        # Very light cardiology/OB-GYN/behavioral-health style hints based on SOAP text
        if soap_note is not None:
            note_text = " ".join(
                [
                    soap_note.subjective.text,
                    soap_note.objective.text,
                    soap_note.assessment.text,
                    soap_note.plan.text,
                ]
            ).lower()

            if "heart failure" in note_text or "hfref" in note_text:
                suggestions.append(
                    DecisionSupportSuggestion.new(
                        type=SuggestionType.RED_FLAG,
                        severity=SuggestionSeverity.INFO,
                        summary="Heart failure mentioned – ensure guideline-directed therapy.",
                        details="Consider ACEi/ARB/ARNI, beta-blocker, MRA, and SGLT2i as appropriate.",
                        evidence_refs=["demo-guideline-hf-1"],
                    )
                )

            if "pregnancy" in note_text or "prenatal" in note_text:
                suggestions.append(
                    DecisionSupportSuggestion.new(
                        type=SuggestionType.RED_FLAG,
                        severity=SuggestionSeverity.INFO,
                        summary="Prenatal visit – check key maternal/fetal parameters.",
                        details="Confirm blood pressure, fetal movement, warning signs, and follow-up interval are documented.",
                        evidence_refs=["demo-guideline-ob-1"],
                    )
                )

            if "suicidal" in note_text or "self-harm" in note_text:
                suggestions.append(
                    DecisionSupportSuggestion.new(
                        type=SuggestionType.RED_FLAG,
                        severity=SuggestionSeverity.CRITICAL,
                        summary="Possible suicidality mentioned – follow safety protocol.",
                        details="Ensure immediate risk assessment, safety planning, and escalation per clinic policy.",
                        evidence_refs=["demo-guideline-psych-1"],
                    )
                )

        return suggestions


decision_support_service = DecisionSupportService()
