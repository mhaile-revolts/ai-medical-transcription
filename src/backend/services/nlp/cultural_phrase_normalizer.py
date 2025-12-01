from __future__ import annotations

from typing import Optional

from src.backend.services.governance.indigenous_data_sovereignty_guard import (
    CulturalConsentContext,
)


class CulturalPhraseNormalizer:
    """Normalize culturally-specific expressions into clinical phrasing.

    This sits between raw ASR output and the clinical NLP pipeline. The goal is
    **not** to erase cultural language but to make implicit clinical meaning
    more explicit for downstream models, while preserving the original text at
    the application layer.

    The initial implementation is deliberately small and conservative; it
    focuses on a few common idioms and can be expanded/overridden per tenant in
    future iterations.
    """

    def normalize(
        self,
        text: str,
        *,
        context: Optional[CulturalConsentContext] = None,
    ) -> str:
        if not text:
            return text

        # If cultural AI features have been explicitly disabled, return the
        # input unchanged.
        if context is not None and not context.cultural_ai_allowed:
            return text

        normalized = text

        # Very small, illustrative rule set. In a real deployment these rules
        # would be curated per community/tenant and loaded from configuration
        # rather than hard-coded.
        normalized = _replace_case_insensitive(
            normalized,
            "my blood is hot",
            "my body feels hot, like I have a fever",
        )
        normalized = _replace_case_insensitive(
            normalized,
            "my spirit is tired",
            "I feel very tired and low in mood",
        )
        normalized = _replace_case_insensitive(
            normalized,
            "the child is not active",
            "the child is less active and less playful than usual",
        )
        normalized = _replace_case_insensitive(
            normalized,
            "the sun is burning my blood",
            "I feel extremely hot, like the sun is overheating my body",
        )

        return normalized


def _replace_case_insensitive(text: str, needle: str, replacement: str) -> str:
    """Case-insensitive substring replacement preserving other content."""

    import re

    pattern = re.compile(re.escape(needle), re.IGNORECASE)
    return pattern.sub(replacement, text)


cultural_phrase_normalizer = CulturalPhraseNormalizer()
