from __future__ import annotations

from enum import Enum
from typing import Any, Mapping, Optional


class AccentLabel(str, Enum):
    """Coarse accent/dialect labels for English and related languages.

    This is intentionally small and illustrative. It provides a stable enum that
    can later be wired to a proper classifier model.
    """

    UNKNOWN = "UNKNOWN"
    EAST_AFRICAN_ENGLISH = "EAST_AFRICAN_ENGLISH"
    WEST_AFRICAN_ENGLISH = "WEST_AFRICAN_ENGLISH"
    AFRICAN_AMERICAN_ENGLISH = "AFRICAN_AMERICAN_ENGLISH"
    CARIBBEAN_ENGLISH = "CARIBBEAN_ENGLISH"
    ARAB_ENGLISH = "ARAB_ENGLISH"
    INDIAN_ENGLISH = "INDIAN_ENGLISH"
    INDIGENOUS_LANGUAGE = "INDIGENOUS_LANGUAGE"


class AccentClassifier:
    """Very lightweight, heuristic accent classifier.

    For this phase, we rely only on language codes and optional region hints.
    This is *not* intended as a final ML model, but as a pluggable hook that
    can later be replaced by a learned classifier without changing callers.
    """

    def classify(
        self,
        *,
        language_code: Optional[str] = None,
        hints: Optional[Mapping[str, Any]] = None,
    ) -> AccentLabel:
        code = (language_code or "").lower()
        region = (hints or {}).get("region") if hints else None
        region_str = str(region or "").lower()

        # Very small, conservative mapping from language/region hints to labels.
        if code.startswith("en-ke") or code.startswith("en-ug") or code.startswith("en-tz"):
            return AccentLabel.EAST_AFRICAN_ENGLISH
        if code.startswith("en-ng") or code.startswith("en-gh"):
            return AccentLabel.WEST_AFRICAN_ENGLISH
        if "aae" in region_str or "african_american" in region_str:
            return AccentLabel.AFRICAN_AMERICAN_ENGLISH
        if code.startswith("en-jm") or "caribbean" in region_str:
            return AccentLabel.CARIBBEAN_ENGLISH
        if "arab" in region_str:
            return AccentLabel.ARAB_ENGLISH
        if code.startswith("en-in") or "india" in region_str:
            return AccentLabel.INDIAN_ENGLISH

        if code in {"nv", "nv-us", "cr", "mi"} or "indigenous" in region_str:
            return AccentLabel.INDIGENOUS_LANGUAGE

        return AccentLabel.UNKNOWN


accent_classifier = AccentClassifier()
