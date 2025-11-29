from __future__ import annotations

from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Protocol

from src.backend.config import settings
from src.backend.domain.nlp.models import ClinicalEntities, ClinicalEntity, SOAPNote, SOAPSection


class NERBackend(Protocol):
    """Protocol for clinical named entity recognition backends."""

    def extract(self, text: str) -> ClinicalEntities:  # pragma: no cover - interface
        """Extract structured clinical entities from free text."""
        raise NotImplementedError


class CodingBackend(Protocol):
    """Protocol for mapping entities to clinical codes (e.g., ICD-10, SNOMED)."""

    def code(self, entities: ClinicalEntities) -> ClinicalEntities:  # pragma: no cover - interface
        """Return entities with code fields populated where possible."""
        raise NotImplementedError


class SOAPGeneratorBackend(Protocol):
    """Protocol for generating structured SOAP notes from text and entities."""

    def generate(self, text: str, entities: ClinicalEntities) -> SOAPNote:  # pragma: no cover - interface
        raise NotImplementedError


class DemoNERBackend:
    """Very small, deterministic NER backend used for tests and prototyping.

    This mirrors the previous DemoNLPService behaviour by looking for a couple
    of hard-coded keywords so higher layers have stable output without any
    external ML dependencies.
    """

    def extract(self, text: str) -> ClinicalEntities:
        entities = ClinicalEntities()
        lower = text.lower()

        if "diabetes" in lower:
            entities.diagnoses.append(ClinicalEntity(label="DIAGNOSIS", text="diabetes"))
        if "metformin" in lower:
            entities.medications.append(ClinicalEntity(label="MEDICATION", text="metformin"))

        return entities


class DemoCodingBackend:
    """Minimal demo coding backend.

    For now this only codes the demo "diabetes" diagnosis to ICD-10 E11 so that
    downstream FHIR export has at least one coded condition.
    """

    def code(self, entities: ClinicalEntities) -> ClinicalEntities:
        for diag in entities.diagnoses:
            if diag.text.lower() == "diabetes" and not diag.code:
                diag.code = "E11"
        return entities


class UmlsCodingBackend:
    """Simple UMLS/ontology-based coding backend using string similarity.

    This backend loads concept names and codes from a JSON or JSONL file and
    assigns the best-matching concept to each entity using a fuzzy string match.
    It does not require any ML libraries and is meant as a lightweight
    placeholder that can later be swapped for a true UmlsBERT encoder.
    """

    def __init__(
        self,
        *,
        concepts_path=None,
        min_similarity: Optional[float] = None,
    ) -> None:
        from pathlib import Path

        self._concepts_path = concepts_path or settings.umls_concepts_path
        if self._concepts_path is not None and not isinstance(self._concepts_path, Path):
            self._concepts_path = Path(self._concepts_path)
        self._min_similarity = min_similarity if min_similarity is not None else settings.umls_min_similarity
        self._concepts: Optional[List[Dict[str, Any]]] = None

    def _load_concepts(self) -> None:
        import json

        if self._concepts is not None:
            return

        path = self._concepts_path
        if path is None:
            raise RuntimeError(
                "UmlsCodingBackend requires UMLS_CONCEPTS_PATH to be set to a JSON or JSONL file containing concepts."
            )
        if not path.exists():
            raise RuntimeError(f"UmlsCodingBackend concepts file '{path}' does not exist.")

        concepts: List[Dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as f:
            # Support either a JSON array or JSONL (one JSON object per line).
            first_char = f.read(1)
            f.seek(0)
            if first_char == "[":
                raw = json.load(f)
                iterable = raw if isinstance(raw, list) else []
            else:
                iterable = (json.loads(line) for line in f if line.strip())

            for obj in iterable:
                if not isinstance(obj, dict):
                    continue
                name = obj.get("name") or obj.get("description")
                if not isinstance(name, str):
                    continue
                concepts.append(
                    {
                        "name": name,
                        "code": obj.get("code") or obj.get("cui"),
                        "system": obj.get("system") or obj.get("codingSystem"),
                    }
                )

        if not concepts:
            raise RuntimeError("No concepts loaded from UMLS_CONCEPTS_PATH; check the file format.")

        self._concepts = concepts

    def _best_match(self, text: str) -> Optional[Dict[str, Any]]:
        assert self._concepts is not None
        best: Optional[Dict[str, Any]] = None
        best_score = 0.0
        source = text.lower()
        for concept in self._concepts:
            name = concept.get("name")
            if not isinstance(name, str):
                continue
            score = SequenceMatcher(a=source, b=name.lower()).ratio()
            if score > best_score:
                best_score = score
                best = concept
        if best is None or best_score < self._min_similarity:
            return None
        return best

    def code(self, entities: ClinicalEntities) -> ClinicalEntities:
        self._load_concepts()
        assert self._concepts is not None

        for bucket in (entities.diagnoses, entities.symptoms, entities.medications):
            for ent in bucket:
                if ent.code or not ent.text:
                    continue
                match = self._best_match(ent.text)
                if not match:
                    continue
                code = match.get("code")
                if isinstance(code, str):
                    ent.code = code
        return entities


class DemoSOAPGeneratorBackend:
    """Demo SOAP generator that echoes the transcript into the subjective section.

    This preserves the behaviour expected by existing tests while allowing
    future replacement with a real medical LLM-backed implementation.
    """

    def generate(self, text: str, entities: ClinicalEntities) -> SOAPNote:
        return SOAPNote(
            subjective=SOAPSection(text=f"Subjective summary: {text}"),
            objective=SOAPSection(text="Objective: demo placeholder"),
            assessment=SOAPSection(text="Assessment: demo placeholder"),
            plan=SOAPSection(text="Plan: demo placeholder"),
        )


class ClinicalBERTNERBackend:
    """NER backend using a HuggingFace token classification model.

    By default this uses a Bio/ClinicalBERT checkpoint suitable for biomedical
    or clinical NER. It requires the `transformers` library and a compatible
    model with token-classification heads.
    """

    def __init__(self, model_name: Optional[str] = None) -> None:  # pragma: no cover - external dependency
        self._model_name = model_name or settings.clinical_ner_model_name
        self._pipeline = None

    def _load_pipeline(self) -> None:
        if self._pipeline is not None:
            return
        try:
            from transformers import AutoModelForTokenClassification, AutoTokenizer, pipeline  # type: ignore
        except ImportError as exc:  # pragma: no cover - depends on external lib
            raise RuntimeError(
                "ClinicalBERTNERBackend requires the 'transformers' package. Install it with 'pip install transformers'."
            ) from exc

        tokenizer = AutoTokenizer.from_pretrained(self._model_name)
        model = AutoModelForTokenClassification.from_pretrained(self._model_name)
        self._pipeline = pipeline(
            "token-classification",
            model=model,
            tokenizer=tokenizer,
            aggregation_strategy="simple",
        )

    def extract(self, text: str) -> ClinicalEntities:  # pragma: no cover - external dependency
        self._load_pipeline()
        assert self._pipeline is not None
        outputs = self._pipeline(text)
        entities = ClinicalEntities()

        for item in outputs:
            # `entity_group` is an aggregated label such as PROBLEM, DRUG, etc.
            label = str(item.get("entity_group", "")).upper()
            span_text = str(item.get("word") or item.get("text") or "")
            if not span_text:
                continue

            target_bucket = None
            if any(tok in label for tok in ("DISEASE", "DISORDER", "PROBLEM", "COND", "DIAG")):
                target_bucket = entities.diagnoses
            elif any(tok in label for tok in ("SYMPTOM", "SIGN")):
                target_bucket = entities.symptoms
            elif any(tok in label for tok in ("DRUG", "MED", "MEDICATION")):
                target_bucket = entities.medications

            if target_bucket is not None:
                target_bucket.append(ClinicalEntity(label=label, text=span_text))

        return entities


class Med7NERBackend:
    """NER backend backed by the Med7 spaCy model.

    This requires the `spacy` library and a compatible Med7 pipeline to be
    installed. By default it uses the model name from MED7_MODEL_NAME.

    Note: this is intended for production-like environments and is not enabled
    by default in tests.
    """

    def __init__(self, model_name: str | None = None) -> None:  # pragma: no cover - external dependency
        self._model_name = model_name or settings.med7_model_name
        self._nlp = None

    def _load_model(self) -> None:
        if self._nlp is not None:
            return
        try:
            import spacy  # type: ignore
        except ImportError as exc:  # pragma: no cover - depends on external lib
            raise RuntimeError(
                "Med7NERBackend requires the 'spacy' package. Install it with 'pip install spacy' "
                "and ensure the Med7 model is available."
            ) from exc
        try:
            self._nlp = spacy.load(self._model_name)
        except Exception as exc:  # pragma: no cover - model loading
            raise RuntimeError(
                f"Failed to load Med7 model '{self._model_name}'. Make sure it is installed."
            ) from exc

    def extract(self, text: str) -> ClinicalEntities:  # pragma: no cover - external dependency
        self._load_model()
        assert self._nlp is not None
        doc = self._nlp(text)
        entities = ClinicalEntities()
        for ent in doc.ents:
            label = ent.label_.upper()
            # Med7 focuses on medication-related spans; map DRUG to medications.
            if label in {"DRUG", "MEDICATION"}:
                entities.medications.append(ClinicalEntity(label="MEDICATION", text=ent.text))
            # Other labels (e.g. DOSAGE, STRENGTH, ROUTE) could be modeled as
            # structured attributes in extended models later.
        return entities


class LLMSOAPGeneratorBackend:
    """SOAP generator that uses an LLM via the OpenAI Python client.

    This backend expects OPENAI_API_KEY to be set and uses the model name from
    LLM_MODEL. It asks the model to return a simple JSON structure with
    subjective, objective, assessment, and plan fields.
    """

    def __init__(self, model: str | None = None) -> None:  # pragma: no cover - external service
        self._model = model or settings.llm_model

    def generate(self, text: str, entities: ClinicalEntities) -> SOAPNote:  # pragma: no cover - external service
        import json

        api_key = settings.openai_api_key
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY must be set to use LLMSOAPGeneratorBackend")

        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError(
                "LLMSOAPGeneratorBackend requires the 'openai' package. Install it with 'pip install openai'"
            ) from exc

        client = OpenAI(api_key=api_key)

        # Build a compact prompt; in a real medical setting this should be
        # expanded with stronger safety constraints and system prompts.
        prompt = {
            "role": "user",
            "content": (
                "You are a clinical documentation assistant. Given the following "
                "doctor-patient transcript, generate a concise SOAP note. "
                "Respond ONLY as compact JSON with keys 'subjective', 'objective', "
                "'assessment', and 'plan'. Do not include markdown or explanations.\n\n"
                f"Transcript:\n{text}\n"
            ),
        }

        response = client.responses.create(
            model=self._model,
            input=[prompt],
        )

        raw_text: str | None = None
        for output in response.output:
            for item in output.content:
                if getattr(item, "type", "") == "output_text" and getattr(item, "text", None):
                    raw_text = item.text
                    break
            if raw_text is not None:
                break

        if not raw_text:
            # Fallback to demo behaviour if the response is not as expected.
            return DemoSOAPGeneratorBackend().generate(text, entities)

        try:
            data = json.loads(raw_text)
        except json.JSONDecodeError:
            return DemoSOAPGeneratorBackend().generate(text, entities)

        def _get(key: str) -> str:
            value = data.get(key)
            return value if isinstance(value, str) else ""

        return SOAPNote(
            subjective=SOAPSection(text=_get("subjective") or f"Subjective summary: {text}"),
            objective=SOAPSection(text=_get("objective") or "Objective: not provided"),
            assessment=SOAPSection(text=_get("assessment") or "Assessment: not provided"),
            plan=SOAPSection(text=_get("plan") or "Plan: not provided"),
        )


def get_ner_backend_from_env() -> NERBackend:
    """Select an NER backend based on NLP_NER_BACKEND.

    Currently supports:
    - "demo" (default) – deterministic keyword-based extraction
    - "med7" – Med7 spaCy model backend (requires external dependencies)
    - "clinicalbert" – Clinical/BioBERT-based NER via HuggingFace transformers
    """

    backend_name = settings.nlp_ner_backend.lower()
    if backend_name == "med7":
        return Med7NERBackend()
    if backend_name == "clinicalbert":
        return ClinicalBERTNERBackend()
    return DemoNERBackend()


def get_coding_backend_from_env() -> CodingBackend:
    """Select a coding backend based on NLP_CODING_BACKEND.

    Supports:
    - "demo" (default) – simple hard-coded coding for demo flows
    - "umlscoder" / "umls" – UmlsCodingBackend using a local concepts file
    """

    backend_name = settings.nlp_coding_backend.lower()
    if backend_name in {"umlscoder", "umls"}:
        return UmlsCodingBackend()
    return DemoCodingBackend()


def get_soap_backend_from_env() -> SOAPGeneratorBackend:
    """Select a SOAP note generator backend based on NLP_SOAP_BACKEND.

    Supports:
    - "demo" (default) – simple echo-based generator
    - "llm" – LLMSOAPGeneratorBackend using an external LLM
    """

    backend_name = settings.nlp_soap_backend.lower()
    if backend_name == "llm":
        return LLMSOAPGeneratorBackend()
    return DemoSOAPGeneratorBackend()
