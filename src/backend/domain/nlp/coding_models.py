from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel


class CodeSystem(str, Enum):
    """Supported coding systems for clinical concepts.

    This is intentionally small for now but can be extended (e.g., RxNorm).
    """

    ICD10 = "ICD10"
    CPT = "CPT"
    SNOMED = "SNOMED"
    OTHER = "OTHER"


class CodeAssignment(BaseModel):
    """Represents a single clinical code suggestion for a piece of text."""

    code_system: CodeSystem
    code: str
    display: Optional[str] = None
    # Optional back-references to the source entity/text
    source_entity_label: Optional[str] = None
    source_text: str
    confidence: Optional[float] = None
    # Coarse category such as "diagnosis", "procedure", "medication".
    category: Optional[str] = None


class BillingRiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class BillingRiskSummary(BaseModel):
    """Naive billing risk assessment derived from assigned codes.

    This is advisory only and intended as a starting point for a richer rules
    engine. It should never be treated as a definitive compliance opinion.
    """

    level: BillingRiskLevel
    reasons: List[str] = []
    suggested_actions: List[str] = []
