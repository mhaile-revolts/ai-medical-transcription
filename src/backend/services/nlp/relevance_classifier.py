from __future__ import annotations

from typing import List

from src.backend.domain.nlp.models import RelevanceLabel, TranscriptSegment, SpeakerRole


class RelevanceClassifier:
    """Very lightweight relevance classifier for transcript segments.

    V1 splits on simple sentence boundaries and marks all segments as
    CLINICAL_CORE. This is mainly a schema and hook point for future ML/LLM
    relevance models.
    """

    def classify_segments(self, transcript: str) -> List[TranscriptSegment]:
        if not transcript:
            return []
        raw_segments = [s.strip() for s in _split_sentences(transcript) if s.strip()]
        return [
            TranscriptSegment(
                text=segment,
                start_ms=None,
                end_ms=None,
                relevance=RelevanceLabel.CLINICAL_CORE,
                speaker=None,  # Future diarization can fill this with SpeakerRole
                confidence=None,
            )
            for segment in raw_segments
        ]


def _split_sentences(text: str) -> list[str]:
    # Extremely naive sentence splitter; good enough for demo purposes.
    import re

    parts = re.split(r"(?<=[.!?])\s+", text)
    return parts


relevance_classifier = RelevanceClassifier()
