from __future__ import annotations

from typing import Tuple

from src.backend.domain.nlp.models import ClinicalEntities, SOAPNote
from src.backend.services.nlp.backends import (
    NERBackend,
    CodingBackend,
    SOAPGeneratorBackend,
    get_ner_backend_from_env,
    get_coding_backend_from_env,
    get_soap_backend_from_env,
)


class PipelineNLPService:
    """Clinical NLP pipeline orchestrating NER, coding, and SOAP generation.

    This replaces the previous hard-coded demo implementation with a small
    pipeline built from pluggable backends. By default it uses demo backends
    that preserve the behaviour expected by existing tests, but can later be
    configured to use real Med7/ClinicalBERT/UMLS/LLM components.
    """

    def __init__(
        self,
        *,
        ner_backend: NERBackend | None = None,
        coding_backend: CodingBackend | None = None,
        soap_backend: SOAPGeneratorBackend | None = None,
    ) -> None:
        self._ner: NERBackend = ner_backend or get_ner_backend_from_env()
        self._coding: CodingBackend = coding_backend or get_coding_backend_from_env()
        self._soap: SOAPGeneratorBackend = soap_backend or get_soap_backend_from_env()

    def extract_and_summarize(self, transcript: str) -> Tuple[ClinicalEntities, SOAPNote]:
        """Run the configured NLP pipeline over a transcript string."""

        entities = self._ner.extract(transcript)
        entities = self._coding.code(entities)
        soap_note = self._soap.generate(transcript, entities)
        return entities, soap_note


# Default singleton instance used by API routes.
nlp_service = PipelineNLPService()
