from __future__ import annotations

from collections import Counter
from typing import List

from src.backend.domain.nlp.decision_support import DecisionSupportSuggestion, SuggestionSeverity
from src.backend.services.audit.service import audit_service


class BiasAuditor:
    """Lightweight auditor for decision-support suggestion patterns.

    This phase focuses on observability: we log simple aggregate counts of
    suggestion severities so that downstream analytics can inspect potential
    imbalances across populations. No blocking or mutation is performed here.
    """

    def audit_suggestions(self, suggestions: List[DecisionSupportSuggestion]) -> None:
        if not suggestions:
            return

        counts = Counter(s.severity.value for s in suggestions)
        audit_service.log_event(
            action="cds_bias_audit",
            resource_type="decision_support_suggestions",
            resource_id=None,
            extra={"severity_counts": dict(counts)},
        )


bias_auditor = BiasAuditor()
