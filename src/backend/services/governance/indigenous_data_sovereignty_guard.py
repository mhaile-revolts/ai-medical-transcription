from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional

from src.backend.tenancy import get_current_tenant


@dataclass
class CulturalConsentContext:
    """Represents cultural/Indigenous data-sovereignty consent for a request.

    This is intentionally conservative by default:
    - cultural_ai_allowed defaults to True so analysis features work out of the
      box for existing tenants.
    - training_allowed defaults to False unless an explicit patient-level flag
      is provided.

    In future iterations this can be extended to carry richer community- or
    tenant-specific policy, including OCAP/CARE/UNDRIP-aligned rules.
    """

    tenant_id: str
    cultural_ai_allowed: bool = True
    training_allowed: bool = False
    reason: Optional[str] = None


def evaluate_cultural_ai_consent(
    *,
    tenant_id: Optional[str] = None,
    patient_metadata: Optional[Mapping[str, Any]] = None,
) -> CulturalConsentContext:
    """Compute a CulturalConsentContext for the current request.

    Parameters
    ----------
    tenant_id:
        Optional explicit tenant identifier. When omitted, falls back to the
        request-scoped tenant context.
    patient_metadata:
        Optional mapping containing patient-level consent hints, such as
        ``consent_cultural_ai`` and ``consent_data_training``. These keys are
        intentionally generic so that upstream systems can supply them without
        forcing a specific patient domain model here.
    """

    current_tenant = tenant_id or get_current_tenant()

    # Default posture: allow cultural AI features, but do *not* allow reuse for
    # model training unless explicitly consented.
    cultural_ai_allowed = True
    training_allowed = False
    reason: Optional[str] = None

    if patient_metadata is not None:
        if "consent_cultural_ai" in patient_metadata:
            value = patient_metadata["consent_cultural_ai"]
            if isinstance(value, bool):
                cultural_ai_allowed = value
            reason = reason or "patient_level_consent"

        if "consent_data_training" in patient_metadata:
            value = patient_metadata["consent_data_training"]
            if isinstance(value, bool):
                training_allowed = value
            reason = reason or "patient_level_training_consent"

    return CulturalConsentContext(
        tenant_id=current_tenant,
        cultural_ai_allowed=cultural_ai_allowed,
        training_allowed=training_allowed,
        reason=reason,
    )


def guard_cultural_ai_usage(context: CulturalConsentContext) -> None:
    """Placeholder guard hook for cultural AI usage.

    In future iterations this function can raise or log when ``context``
    indicates that cultural/Indigenous-aware AI features should *not* be used
    for a given request or tenant. For now it is a no-op to avoid breaking
    existing flows while we introduce the wiring.
    """

    # No-op for the initial implementation.
    return
