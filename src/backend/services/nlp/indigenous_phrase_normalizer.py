from __future__ import annotations

from typing import Optional

from src.backend.services.governance.indigenous_data_sovereignty_guard import (
    CulturalConsentContext,
)


class IndigenousPhraseNormalizer:
    """Normalize some Indigenous spiritual/experiential expressions.

    The intent is *not* to pathologize spiritual language, but to provide
    parallel clinical phrasing that can help downstream models reason more
    safely. The original phrases should always be preserved at the UI or note
    layer for clinicians to interpret in context.
    """

    def normalize(
        self,
        text: str,
        *,
        context: Optional[CulturalConsentContext] = None,
    ) -> str:
        if not text:
            return text

        if context is not None and not context.cultural_ai_allowed:
            return text

        normalized = text

        # Example: spiritual distress phrased through ancestral language.
        normalized = _replace_case_insensitive(
            normalized,
            "my ancestors are calling",
            "I feel a strong spiritual pull and emotional distress from my ancestors",
        )

        return normalized


def _replace_case_insensitive(text: str, needle: str, replacement: str) -> str:
    import re

    pattern = re.compile(re.escape(needle), re.IGNORECASE)
    return pattern.sub(replacement, text)


indigenous_phrase_normalizer = IndigenousPhraseNormalizer()
