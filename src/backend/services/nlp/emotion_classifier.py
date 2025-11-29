from __future__ import annotations

from typing import List

from src.backend.domain.nlp.models import EmotionLabel, TranscriptSegment


class EmotionClassifier:
    """Very simple emotion classifier placeholder.

    For now this labels all segments as NEUTRAL. It exists to provide a clean
    hook for future ML/LLM-based emotion and tone detection.
    """

    def classify_segments(self, segments: List[TranscriptSegment]) -> List[TranscriptSegment]:
        for seg in segments:
            if seg.emotion is None:
                seg.emotion = EmotionLabel.NEUTRAL
        return segments


emotion_classifier = EmotionClassifier()
