from __future__ import annotations

from typing import Optional, Protocol

from src.backend.config import settings


class ASRBackend(Protocol):
    """Protocol for automatic speech recognition backends.

    Implementations should take an audio reference and return a transcript in
    the requested source language.
    """

    def transcribe(self, audio_url: str, language_code: Optional[str] = None) -> str:  # pragma: no cover - interface
        raise NotImplementedError


class TranslationBackend(Protocol):
    """Protocol for text translation backends."""

    def translate(
        self,
        text: str,
        target_language: str,
        source_language: Optional[str] = None,
    ) -> str:  # pragma: no cover - interface
        raise NotImplementedError


class DemoASRBackend:
    """Very simple demo ASR backend.

    In a real deployment this would call Whisper, a cloud medical ASR, or a
    custom model. For now it just returns a deterministic placeholder string
    so tests remain fast and offline.
    """

    def transcribe(self, audio_url: str, language_code: Optional[str] = None) -> str:
        lang = language_code or "unknown-lang"
        return f"Demo transcript for {audio_url} in {lang}"


class DemoTranslationBackend:
    """Very simple demo translation backend.

    In a real deployment this would call an LLM or translation model. For now
    it just wraps the input text with a marker for the target language.
    """

    def translate(
        self,
        text: str,
        target_language: str,
        source_language: Optional[str] = None,
    ) -> str:
        src = source_language or "unknown-lang"
        return f"[{src}→{target_language}] {text}"


class WhisperASRBackend:
    """ASR backend that uses the open-source Whisper model via the `whisper` library.

    This implementation expects `audio_url` to be a local filesystem path.
    To use it, install the whisper package (e.g. `pip install openai-whisper`)
    and set `ASR_BACKEND=whisper` in the environment.
    """

    def __init__(self, model_name: str | None = None) -> None:
        self._model_name = model_name or settings.whisper_model_name
        self._model = None

    def _load_model(self):
        if self._model is None:
            try:
                import whisper  # type: ignore
            except ImportError as exc:  # pragma: no cover - depends on external lib
                raise RuntimeError(
                    "WhisperASRBackend requires the 'whisper' library. "
                    "Install it with 'pip install openai-whisper'"
                ) from exc
            self._model = whisper.load_model(self._model_name)

    def transcribe(self, audio_url: str, language_code: Optional[str] = None) -> str:
        self._load_model()
        # For now we assume audio_url is a local path. In a real deployment
        # this might download from S3 or another object store first.
        result = self._model.transcribe(audio_url, language=language_code)
        return result.get("text", "")


class LlamaASRBackend:
    """Stub ASR backend intended for on-device / LLaMA-style models.

    For now this simply delegates to the demo backend while marking the output
    so it is clear that a local/offline path was intended.
    """

    def __init__(self, wrapped: ASRBackend | None = None) -> None:
        from typing import cast

        # Fall back to the demo backend if nothing else is provided to avoid
        # breaking tests.
        self._wrapped: ASRBackend = wrapped or cast(ASRBackend, DemoASRBackend())

    def transcribe(self, audio_url: str, language_code: Optional[str] = None) -> str:  # pragma: no cover - simple wrapper
        base = self._wrapped.transcribe(audio_url, language_code=language_code)
        return f"[llama-offline] {base}"


class LLMTranslationBackend(TranslationBackend):
    """Translation backend that uses an LLM via the OpenAI Python client.

    This is an optional integration behind the existing TranslationBackend
    protocol. If the `OPENAI_API_KEY` environment variable is not set or the
    `openai` package is missing, it will raise at runtime.
    """

    def __init__(self, model: str | None = None) -> None:
        self._model = model or settings.llm_model

    def translate(
        self,
        text: str,
        target_language: str,
        source_language: Optional[str] = None,
    ) -> str:  # pragma: no cover - depends on external service
        api_key = settings.openai_api_key
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY must be set to use LLMTranslationBackend")

        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError(
                "LLMTranslationBackend requires the 'openai' package. "
                "Install it with 'pip install openai'"
            ) from exc

        client = OpenAI(api_key=api_key)
        # Simple prompt-based translation; in a real medical system this would
        # need careful prompt design and safety controls.
        prompt = (
            "You are a translation engine for clinical text. Translate the "
            f"following text from {source_language or 'the source language'} "
            f"into {target_language}, preserving medical terminology.\n\n{text}"
        )
        response = client.responses.create(
            model=self._model,
            input=[{"role": "user", "content": prompt}],
        )
        # Extract first text segment from the response
        for output in response.output:
            for item in output.content:
                if item.type == "output_text" and item.text:
                    return item.text
        # Fallback: return original text if structure is not as expected
        return text


demo_asr_backend = DemoASRBackend()
demo_translation_backend = DemoTranslationBackend()


def get_asr_backend_from_env() -> ASRBackend:
    """Select an ASR backend based on the ASR_BACKEND environment variable.

    - ASR_BACKEND=whisper → WhisperASRBackend
    - ASR_BACKEND=llama → LlamaASRBackend (stub for local/offline models)
    - Anything else (or unset) → DemoASRBackend
    """

    backend_name = settings.asr_backend.lower()
    if backend_name == "whisper":
        return WhisperASRBackend()
    if backend_name == "llama":
        return LlamaASRBackend()
    return demo_asr_backend


def get_translation_backend_from_env() -> TranslationBackend:
    """Select a translation backend based on TRANSLATION_BACKEND env var.

    - TRANSLATION_BACKEND=llm → LLMTranslationBackend
    - Anything else (or unset) → DemoTranslationBackend
    """

    backend_name = settings.translation_backend.lower()
    if backend_name == "llm":
        return LLMTranslationBackend()
    return demo_translation_backend
