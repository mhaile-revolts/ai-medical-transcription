from __future__ import annotations

import os
import base64
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


def _clerk_issuer_from_publishable_key() -> Optional[str]:
    """Derive the Clerk frontend API issuer without logging the key."""
    key = os.getenv("CLERK_PUBLISHABLE_KEY", "")
    try:
        encoded = key.split("_", 2)[2]
        decoded = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)).decode()
        host = decoded.rstrip("$")
        return f"https://{host}" if host else None
    except (IndexError, ValueError, UnicodeDecodeError):
        return None


@dataclass
class Settings:
    """Centralized application settings.

    This keeps environment-variable handling in one place so other modules can
    depend on strongly-typed attributes instead of calling os.getenv
    directly.
    """

    # ASR backend selection: "demo" (default) or "whisper".
    asr_backend: str = os.getenv("ASR_BACKEND", "demo")
    elevenlabs_scribe_model: str = os.getenv("ELEVENLABS_SCRIBE_MODEL", "scribe_v2_medical")
    elevenlabs_baa_confirmed: bool = os.getenv("ELEVENLABS_BAA_CONFIRMED", "false").lower() == "true"
    elevenlabs_zero_retention_enabled: bool = (
        os.getenv("ELEVENLABS_ZERO_RETENTION_ENABLED", "false").lower() == "true"
    )

    # Optional MultiChain (private blockchain) integration used for tamper-evident
    # audit logging. When MULTICHAIN_ENABLED=true and the RPC connection details
    # are valid, structured audit events will be mirrored into a configured
    # MultiChain stream. PHI is never written on-chain; only minimal metadata
    # such as resource IDs and action types should be published.
    multichain_enabled: bool = os.getenv("MULTICHAIN_ENABLED", "false").lower() == "true"
    multichain_rpc_scheme: str = os.getenv("MULTICHAIN_RPC_SCHEME", "http")
    multichain_rpc_host: str = os.getenv("MULTICHAIN_RPC_HOST", "127.0.0.1")
    multichain_rpc_port: int = int(os.getenv("MULTICHAIN_RPC_PORT", "6824"))
    multichain_rpc_user: Optional[str] = os.getenv("MULTICHAIN_RPC_USER")
    multichain_rpc_password: Optional[str] = os.getenv("MULTICHAIN_RPC_PASSWORD")
    multichain_chain_name: Optional[str] = os.getenv("MULTICHAIN_CHAIN_NAME")
    multichain_audit_stream: str = os.getenv("MULTICHAIN_AUDIT_STREAM", "audit")
    multichain_rpc_timeout_seconds: float = float(os.getenv("MULTICHAIN_RPC_TIMEOUT_SECONDS", "2.0"))

    # Translation backend selection: "demo" (default) or "llm".
    translation_backend: str = os.getenv("TRANSLATION_BACKEND", "demo")

    # NLP backend selection for the clinical NLP pipeline.
    # These are currently "demo" only but are designed to support values like
    # "med7", "clinicalbert", "umlscoder", "llm", etc. in future
    # implementations.
    nlp_ner_backend: str = os.getenv("NLP_NER_BACKEND", "demo")
    nlp_coding_backend: str = os.getenv("NLP_CODING_BACKEND", "demo")
    nlp_soap_backend: str = os.getenv("NLP_SOAP_BACKEND", "demo")

    # ``demo`` is the only mode permitted to use ephemeral local state.
    # Durable mode is deliberately the default: a missing database must stop
    # startup rather than silently accepting PHI into process memory.
    app_mode: str = os.getenv("APP_MODE", "durable").lower()
    # development/test are the *only* environments where the explicit test
    # identity override is available.  Deployments handling PHI must use
    # staging or production.
    app_env: str = os.getenv("APP_ENV", "development").lower()

    # Directory where uploaded audio files are stored (demo mode only).
    audio_upload_dir: Path = Path(os.getenv("AUDIO_UPLOAD_DIR", "uploads"))

    # Optional database configuration for SQL-backed repositories.
    database_url: Optional[str] = os.getenv("DATABASE_URL")
    use_sql_repos: bool = os.getenv("USE_SQL_REPOS", "false").lower() == "true"

    ehr_dispatch_enabled: bool = os.getenv("EHR_DISPATCH_ENABLED", "true").lower() == "true"
    ehr_dispatch_poll_seconds: float = float(os.getenv("EHR_DISPATCH_POLL_SECONDS", "5"))
    ehr_dispatch_batch_size: int = int(os.getenv("EHR_DISPATCH_BATCH_SIZE", "10"))
    ehr_dispatch_lease_seconds: int = int(os.getenv("EHR_DISPATCH_LEASE_SECONDS", "120"))
    ehr_retry_max_attempts: int = int(os.getenv("EHR_RETRY_MAX_ATTEMPTS", "6"))
    ehr_retry_base_seconds: int = int(os.getenv("EHR_RETRY_BASE_SECONDS", "60"))
    ehr_retry_max_seconds: int = int(os.getenv("EHR_RETRY_MAX_SECONDS", "3600"))

    # Optional settings for external providers.
    openai_api_key: Optional[str] = os.getenv("OPENAI_API_KEY")
    whisper_model_name: str = os.getenv("WHISPER_MODEL_NAME", "base")
    llm_model: str = os.getenv("LLM_MODEL", "gpt-4.1-mini")

    # Deployment/sovereignty controls.
    # When REQUIRE_ON_PREM_ONLY=true, operators intend the system to avoid
    # relying on external SaaS/cloud dependencies. Enforcement is implemented
    # in the relevant backends (e.g., LLMTranslationBackend, future cloud ASR).
    require_on_prem_only: bool = os.getenv("REQUIRE_ON_PREM_ONLY", "false").lower() == "true"
    # When ALLOW_CLOUD_LLM=false, LLMTranslationBackend is disabled even if an
    # OPENAI_API_KEY is present.
    allow_cloud_llm: bool = os.getenv("ALLOW_CLOUD_LLM", "true").lower() == "true"

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

    # Request size limits (in bytes).
    max_upload_bytes: int = int(os.getenv("MAX_UPLOAD_BYTES", str(10 * 1024 * 1024)))
    max_ws_bytes: int = int(os.getenv("MAX_WS_BYTES", str(10 * 1024 * 1024)))

    # CORS configuration: comma-separated origins (e.g. "https://app.example.com,https://admin.example.com").
    # Default is "*" (allow all) which is acceptable for local development but
    # should be tightened in production.
    cors_allow_origins: str = os.getenv("CORS_ALLOW_ORIGINS", "*")

    # Clerk OpenID Connect verification.  Configure either CLERK_JWKS_URL
    # (normal Clerk production setup) or CLERK_JWT_PUBLIC_KEY (PEM, useful for
    # isolated deployments).  Claims are deliberately read only after JWT
    # signature/issuer/audience validation.
    clerk_issuer: Optional[str] = os.getenv("CLERK_ISSUER") or _clerk_issuer_from_publishable_key()
    clerk_audience: Optional[str] = os.getenv("CLERK_AUDIENCE")
    clerk_jwks_url: Optional[str] = os.getenv("CLERK_JWKS_URL") or (
        f"{clerk_issuer}/.well-known/jwks.json" if clerk_issuer else None
    )
    clerk_jwt_public_key: Optional[str] = os.getenv("CLERK_JWT_PUBLIC_KEY")

    # OCHIN SMART on FHIR metadata.  These values identify a deployment only;
    # access tokens are deliberately never configured or logged by this app.
    ochin_smart_fhir_base_url: Optional[str] = os.getenv("OCHIN_SMART_FHIR_BASE_URL")
    ochin_smart_issuer: Optional[str] = os.getenv("OCHIN_SMART_ISSUER")
    ochin_smart_client_id: Optional[str] = os.getenv("OCHIN_SMART_CLIENT_ID")
    ochin_smart_redirect_uri: Optional[str] = os.getenv("OCHIN_SMART_REDIRECT_URI")
    ochin_smart_authorize_url: Optional[str] = os.getenv("OCHIN_SMART_AUTHORIZE_URL")
    ochin_smart_token_url: Optional[str] = os.getenv("OCHIN_SMART_TOKEN_URL")
    ochin_smart_jwks_url: Optional[str] = os.getenv("OCHIN_SMART_JWKS_URL")
    ochin_smart_revoke_url: Optional[str] = os.getenv("OCHIN_SMART_REVOKE_URL")
    ochin_smart_scopes: str = os.getenv(
        "OCHIN_SMART_SCOPES",
        "openid fhirUser offline_access patient/Patient.read patient/Encounter.read",
    )
    ochin_smart_required_scopes: str = os.getenv(
        "OCHIN_SMART_REQUIRED_SCOPES", "openid fhirUser patient/Patient.read patient/Encounter.read"
    )
    smart_token_encryption_key: Optional[str] = os.getenv("SMART_TOKEN_ENCRYPTION_KEY") or os.getenv("SESSION_SECRET")
    ochin_smart_mobile_return_uri: str = os.getenv(
        "OCHIN_SMART_MOBILE_RETURN_URI", "aimedicaltranscription://smart-complete"
    )

    # Retention is an operational control; a worker must use these values to
    # purge expired PHI.  Zero is never accepted outside development/test.
    phi_audio_retention_days: int = int(os.getenv("PHI_AUDIO_RETENTION_DAYS", "30"))
    phi_transcript_retention_days: int = int(os.getenv("PHI_TRANSCRIPT_RETENTION_DAYS", "2555"))
    audit_retention_days: int = int(os.getenv("AUDIT_RETENTION_DAYS", "2555"))
    # Production audit events are written to a permission-restricted rotating
    # file that infrastructure must ship to its append-only audit archive.
    audit_log_path: Optional[Path] = (
        Path(os.getenv("AUDIT_LOG_PATH")) if os.getenv("AUDIT_LOG_PATH") else None
    )


settings = Settings()
