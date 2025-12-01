from __future__ import annotations

from typing import Any, Mapping, Optional, Protocol

from src.backend.core.accent_classifier import AccentClassifier, AccentLabel, accent_classifier


class ASRLike(Protocol):
    """Protocol for ASR-like backends used by MultiAccentASRBackend.

    This intentionally mirrors the signature of src.backend.services.transcription
    ASR backends without importing them directly, to avoid circular imports.
    """

    def transcribe(self, audio_url: str, language_code: Optional[str] = None) -> str:  # pragma: no cover - protocol
        ...


class MultiAccentASRBackend:
    """Wrapper ASR backend that classifies accent/dialect before transcription.

    In this initial implementation, the detected accent is not yet used to
    change which underlying model is called; it is exposed via `last_accent`
    for logging and diagnostics only. Future iterations can use the accent
    label to route to accent-specific models or decoding configs.
    """

    def __init__(
        self,
        *,
        base_backend: ASRLike,
        classifier: AccentClassifier | None = None,
    ) -> None:
        self._base = base_backend
        self._classifier = classifier or accent_classifier
        self.last_accent: AccentLabel | None = None

    def transcribe(
        self,
        audio_url: str,
        language_code: Optional[str] = None,
        *,
        hints: Optional[Mapping[str, Any]] = None,
    ) -> str:
        # Derive an accent label from language + optional hints and store it for
        # observability. For now this does not alter which backend is called.
        self.last_accent = self._classifier.classify(
            language_code=language_code,
            hints=hints,
        )

        return self._base.transcribe(audio_url, language_code=language_code)
