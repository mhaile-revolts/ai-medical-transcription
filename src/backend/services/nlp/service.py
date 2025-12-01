from __future__ import annotations

from typing import Any, Mapping, Tuple

from src.backend.domain.nlp.models import ClinicalEntities, SOAPNote
from src.backend.services.governance.indigenous_data_sovereignty_guard import (
    CulturalConsentContext,
    evaluate_cultural_ai_consent,
)
from src.backend.services.nlp.backends import (
    NERBackend,
    CodingBackend,
    SOAPGeneratorBackend,
    get_ner_backend_from_env,
    get_coding_backend_from_env,
    get_soap_backend_from_env,
)
from src.backend.services.nlp.cultural_phrase_normalizer import (
    cultural_phrase_normalizer,
)
from src.backend.services.nlp.indigenous_phrase_normalizer import (
    indigenous_phrase_normalizer,
)
from src.backend.tenancy import get_current_tenant


class PipelineNLPService:
    """Clinical NLP pipeline orchestrating NER, coding, and SOAP generation.

    This replaces the previous hard-coded demo implementation with a small
    pipeline built from pluggable backends. By default it uses demo backends
    that preserve the behaviour expected by existing tests, but can later be
    configured to use real Med7/ClinicalBERT/UMLS/LLM components.

    The pipeline now includes optional cultural/Indigenous-aware phrase
    normalization, gated by a lightweight consent context. When no explicit
    consent metadata is supplied, behaviour falls back to the previous
    implementation.
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

    def extract_and_summarize(
        self,
        transcript: str,
        *,
        tenant_id: str | None = None,
        patient_metadata: Mapping[str, Any] | None = None,
        respect_cultural_consent: bool = True,
    ) -> Tuple[ClinicalEntities, SOAPNote]:
        """Run the configured NLP pipeline over a transcript string.

        Parameters
        ----------
        transcript:
            Raw transcript text, typically from ASR.
        tenant_id:
            Optional explicit tenant identifier. If omitted, the request-scoped
            tenant context is used.
        patient_metadata:
            Optional mapping with patient-level consent and cultural hints
            (e.g., ``consent_cultural_ai``, ``consent_data_training``). When
            omitted, the pipeline behaves as before and applies a default,
            permissive consent context.
        respect_cultural_consent:
            When False, cultural consent is ignored and the transcript is
            passed through without phrase normalization. This flag exists mainly
            to support internal/testing callers.
        """

        effective_tenant = tenant_id or get_current_tenant()
        consent_ctx: CulturalConsentContext | None = None

        if respect_cultural_consent:
            consent_ctx = evaluate_cultural_ai_consent(
                tenant_id=effective_tenant,
                patient_metadata=patient_metadata,
            )

        text_for_nlp = transcript
        if consent_ctx is None or consent_ctx.cultural_ai_allowed:
            text_for_nlp = cultural_phrase_normalizer.normalize(
                text_for_nlp,
                context=consent_ctx,
            )
            text_for_nlp = indigenous_phrase_normalizer.normalize(
                text_for_nlp,
                context=consent_ctx,
            )

        entities = self._ner.extract(text_for_nlp)
        entities = self._coding.code(entities)
        soap_note = self._soap.generate(text_for_nlp, entities)
        return entities, soap_note


# Default singleton instance used by API routes.
nlp_service = PipelineNLPService()
