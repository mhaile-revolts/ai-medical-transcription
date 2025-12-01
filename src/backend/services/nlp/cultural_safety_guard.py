from __future__ import annotations

from typing import List, Optional

from src.backend.domain.nlp.decision_support import (
    DecisionSupportSuggestion,
    SuggestionSeverity,
    SuggestionType,
)
from src.backend.domain.nlp.models import SOAPNote


class CulturalSafetyGuard:
    """Conservative post-processor for decision-support suggestions.

    For now, this only adds gentle advisory suggestions in a few clearly
    identified cases, such as when spiritual language appears in the note text
    alongside high-severity alerts. It never removes or downgrades existing
    suggestions.
    """

    def review(
        self,
        suggestions: List[DecisionSupportSuggestion],
        *,
        soap_note: Optional[SOAPNote] = None,
    ) -> List[DecisionSupportSuggestion]:
        if not suggestions or soap_note is None:
            return suggestions

        text = " ".join(
            [
                soap_note.subjective.text,
                soap_note.objective.text,
                soap_note.assessment.text,
                soap_note.plan.text,
            ]
        ).lower()

        has_spiritual_language = any(
            phrase in text
            for phrase in [
                "my ancestors are calling",
                "spirits",
                "spiritual",  # broad but advisory only
            ]
        )
        has_high_severity = any(s.severity == SuggestionSeverity.CRITICAL for s in suggestions)

        if has_spiritual_language and has_high_severity:
            suggestions = suggestions + [
                DecisionSupportSuggestion.new(
                    type=SuggestionType.DIFFERENTIAL,
                    severity=SuggestionSeverity.INFO,
                    summary="Spiritual language present – interpret high-severity alerts in cultural context.",
                    details=(
                        "Transcript includes spiritual or ancestral language. Ensure high-severity "
                        "alerts are interpreted within the patient's cultural and spiritual context "
                        "and, where appropriate, in consultation with culturally knowledgeable "
                        "clinicians or community representatives."
                    ),
                    evidence_refs=["demo-cultural-safety-1"],
                )
            ]

        return suggestions


cultural_safety_guard = CulturalSafetyGuard()
