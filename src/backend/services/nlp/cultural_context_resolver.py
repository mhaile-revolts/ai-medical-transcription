from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional

from src.backend.tenancy import get_current_tenant


@dataclass
class CulturalContext:
    """Lightweight view of cultural context for an NLP request.

    This can later be extended to include explicit cultural_identity,
    indigenous_affiliation, and a tenant-level cultural_ruleset once those are
    modeled in the domain layer. For now it gives normalizers a structured
    place to hang additional logic.
    """

    tenant_id: str
    cultural_ruleset: Optional[str] = None
    patient_metadata: Optional[Mapping[str, Any]] = None


class CulturalContextResolver:
    def resolve(
        self,
        *,
        tenant_id: Optional[str] = None,
        patient_metadata: Optional[Mapping[str, Any]] = None,
        cultural_ruleset: Optional[str] = None,
    ) -> CulturalContext:
        current_tenant = tenant_id or get_current_tenant()
        return CulturalContext(
            tenant_id=current_tenant,
            cultural_ruleset=cultural_ruleset,
            patient_metadata=patient_metadata,
        )


cultural_context_resolver = CulturalContextResolver()
