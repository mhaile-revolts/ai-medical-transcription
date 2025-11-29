from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class Settings:
    """Centralized application settings.

    This keeps environment-variable handling in one place so other modules can
    depend on strongly-typed attributes instead of calling os.getenv
    directly.
    """

    # ASR backend selection: "demo" (default) or "whisper".
    asr_backend: str = os.getenv("ASR_BACKEND", "demo")

    # Translation backend selection: "demo" (default) or "llm".
    translation_backend: str = os.getenv("TRANSLATION_BACKEND", "demo")

    # NLP backend selection for the clinical NLP pipeline.
    # These are currently "demo" only but are designed to support values like
    # "med7", "clinicalbert", "umlscoder", "llm", etc. in future
    # implementations.
    nlp_ner_backend: str = os.getenv("NLP_NER_BACKEND", "demo")
    nlp_coding_backend: str = os.getenv("NLP_CODING_BACKEND", "demo")
    nlp_soap_backend: str = os.getenv("NLP_SOAP_BACKEND", "demo")

    # Directory where uploaded audio files are stored.
    audio_upload_dir: Path = Path(os.getenv("AUDIO_UPLOAD_DIR", "uploads"))

    # Optional database configuration for SQL-backed repositories.
    database_url: Optional[str] = os.getenv("DATABASE_URL")
    use_sql_repos: bool = os.getenv("USE_SQL_REPOS", "false").lower() == "true"

    # Optional settings for external providers.
    openai_api_key: Optional[str] = os.getenv("OPENAI_API_KEY")
    whisper_model_name: str = os.getenv("WHISPER_MODEL_NAME", "base")
    llm_model: str = os.getenv("LLM_MODEL", "gpt-4.1-mini")

    # Optional model identifiers for NLP backends.
    # Med7 spaCy pipeline name used when NLP_NER_BACKEND=med7.
    med7_model_name: str = os.getenv("MED7_MODEL_NAME", "en_core_med7_lg")
    # Clinical/BioBERT NER model name used when NLP_NER_BACKEND=clinicalbert.
    clinical_ner_model_name: str = os.getenv("CLINICAL_NER_MODEL_NAME", "emilyalsentzer/Bio_ClinicalBERT")

    # Optional UMLS/ontology coding configuration.
    # Path to a JSON or JSONL file containing concept records with at least a
    # "name" field and optionally "code" and "system".
    umls_concepts_path: Optional[Path] = (
        Path(os.getenv("UMLS_CONCEPTS_PATH")) if os.getenv("UMLS_CONCEPTS_PATH") else None
    )
    # Minimum similarity ratio (0-1) for fuzzy string matching when assigning
    # codes via UmlsCodingBackend.
    umls_min_similarity: float = float(os.getenv("UMLS_MIN_SIMILARITY", "0.85"))

    # Basic API authentication configuration.
    # When ENABLE_API_AUTH=true, protected endpoints require a valid API key.
    enable_api_auth: bool = os.getenv("ENABLE_API_AUTH", "false").lower() == "true"
    # Comma-separated list of allowed API keys when auth is enabled.
    api_keys: Optional[str] = os.getenv("API_KEYS")

    # Request size limits (in bytes).
    max_upload_bytes: int = int(os.getenv("MAX_UPLOAD_BYTES", str(10 * 1024 * 1024)))
    max_ws_bytes: int = int(os.getenv("MAX_WS_BYTES", str(10 * 1024 * 1024)))

    # CORS configuration: comma-separated origins (e.g. "https://app.example.com,https://admin.example.com").
    # Default is "*" (allow all) which is acceptable for local development but
    # should be tightened in production.
    cors_allow_origins: str = os.getenv("CORS_ALLOW_ORIGINS", "*")


settings = Settings()
