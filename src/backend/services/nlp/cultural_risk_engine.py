from __future__ import annotations

from typing import Any, List, Mapping, Optional

from src.backend.domain.nlp.decision_support import (
    DecisionSupportSuggestion,
    SuggestionSeverity,
    SuggestionType,
)
from src.backend.domain.nlp.models import ClinicalEntities, SOAPNote


class CulturalRiskEngine:
    """Assess culture- and region-aware clinical risk in a conservative way.

    For this phase, the engine only triggers when explicit, structured hints are
    present in `patient_metadata`. Without such hints, it returns no additional
    suggestions so existing behavior is preserved.
    """

    def assess(
        self,
        entities: ClinicalEntities,
        soap_note: Optional[SOAPNote] = None,
        *,
        patient_metadata: Optional[Mapping[str, Any]] = None,
    ) -> List[DecisionSupportSuggestion]:
        if not patient_metadata:
            return []

        suggestions: List[DecisionSupportSuggestion] = []

        region = str(patient_metadata.get("region", "")).lower()
        environment = str(patient_metadata.get("environment", "")).lower()

        note_text = ""
        if soap_note is not None:
            note_text = " ".join(
                [
                    soap_note.subjective.text,
                    soap_note.objective.text,
                    soap_note.assessment.text,
                    soap_note.plan.text,
                ]
            ).lower()

        # Example: heat-related illness risk in hot, outdoor environments.
        if any(k in environment for k in ("outdoor", "pastoralist")) and (
            "heat" in note_text or "dizzy" in note_text or "exhausted" in note_text
        ):
            suggestions.append(
                DecisionSupportSuggestion.new(
                    type=SuggestionType.RED_FLAG,
                    severity=SuggestionSeverity.INFO,
                    summary="Possible heat-related illness in high-exposure environment.",
                    details=(
                        "Patient is described as working or living in an outdoor/pastoralist "
                        "environment with symptoms that may suggest heat stress. Consider "
                        "assessing for dehydration and heat-related illness in context of local "
                        "climate and resources."
                    ),
                    evidence_refs=["demo-cultural-heat-1"],
                )
            )

        # Example: region-aware infectious disease consideration (very generic).
        if "malaria_endemic" in region and "fever" in note_text:
            suggestions.append(
                DecisionSupportSuggestion.new(
                    type=SuggestionType.DIFFERENTIAL,
                    severity=SuggestionSeverity.INFO,
                    summary="Fever in malaria-endemic region – consider infectious causes.",
                    details=(
                        "Patient is in a region marked as malaria-endemic in metadata. Ensure "
                        "local guidelines for fever workup are followed; malaria is only one "
                        "of several possible causes."
                    ),
                    evidence_refs=["demo-cultural-malaria-1"],
                )
            )

        return suggestions


cultural_risk_engine = CulturalRiskEngine()
