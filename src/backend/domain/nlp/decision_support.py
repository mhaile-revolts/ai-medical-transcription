from __future__ import annotations

from enum import Enum
from typing import List, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel


class SuggestionType(str, Enum):
    DIFFERENTIAL = "DIFFERENTIAL"
    RED_FLAG = "RED_FLAG"
    MED_ADJUSTMENT = "MED_ADJUSTMENT"
    CONTRAINDICATION = "CONTRAINDICATION"


class SuggestionSeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class DecisionSupportSuggestion(BaseModel):
    id: UUID
    type: SuggestionType
    severity: SuggestionSeverity
    summary: str
    details: Optional[str] = None
    evidence_refs: List[str] = []
    # Source descriptor and regulatory context for future CDS variants.
    source: str = "demo_rule"  # e.g. "demo_rule", "llm_cds_v1"
    regulated: bool = False

    @classmethod
    def new(
        cls,
        *,
        type: SuggestionType,
        severity: SuggestionSeverity,
        summary: str,
        details: Optional[str] = None,
        evidence_refs: Optional[List[str]] = None,
    ) -> "DecisionSupportSuggestion":
        return cls(
            id=uuid4(),
            type=type,
            severity=severity,
            summary=summary,
            details=details,
            evidence_refs=evidence_refs or [],
        )
