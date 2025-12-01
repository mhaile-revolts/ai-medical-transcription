from __future__ import annotations

from typing import Any, List, Mapping, Optional

from src.backend.domain.nlp.decision_support import (
    DecisionSupportSuggestion,
    SuggestionSeverity,
    SuggestionType,
)
from src.backend.domain.nlp.models import ClinicalEntities, SOAPNote


class IndigenousRiskEngine:
    """Assess Indigenous-specific contextual risks in a careful, non-stereotypical way.

    For this initial implementation we only act when explicit metadata is
    provided (e.g., `indigenous_affiliation` or flags such as
    `has_historical_trauma_documented`). The goal is to surface gentle reminders
    about trauma-informed and culturally safe care, not to hard-code diagnoses.
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

        indigenous_affiliation = str(patient_metadata.get("indigenous_affiliation", "")).strip()
        has_trauma_flag = bool(patient_metadata.get("has_historical_trauma_documented", False))

        if indigenous_affiliation and has_trauma_flag:
            suggestions.append(
                DecisionSupportSuggestion.new(
                    type=SuggestionType.DIFFERENTIAL,
                    severity=SuggestionSeverity.INFO,
                    summary="Trauma-informed, culturally safe care is recommended.",
                    details=(
                        "Patient is documented as having an Indigenous affiliation and a "
                        "history of trauma. Ensure assessment and care planning follow "
                        "trauma-informed and culturally safe practices, in partnership with "
                        "local community guidance where available."
                    ),
                    evidence_refs=["demo-indigenous-trauma-1"],
                )
            )

        return suggestions


indigenous_risk_engine = IndigenousRiskEngine()
