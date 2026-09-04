from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Load root-level .env so Settings() picks up values without needing shell exports.
# The project root is two levels up from this file: src/backend/main.py -> backend -> src -> root.
load_dotenv(dotenv_path=Path(__file__).resolve().parents[2] / ".env", override=False)

from src.backend.api.v1.routes_system import router as system_router_v1
from src.backend.api.v1.routes_transcription import router as transcription_router_v1
from src.backend.api.v1.routes_transcription_async import router as transcription_async_router_v1
from src.backend.api.v1.routes_audio_ingestion import router as audio_router_v1
from src.backend.api.v1.routes_nlp import router as nlp_router_v1
from src.backend.api.v1.routes_sessions import router as sessions_router_v1
from src.backend.api.v1.routes_encounters import router as encounters_router_v1
from src.backend.api.v1.routes_templates import router as templates_router_v1
from src.backend.api.v1.routes_patients import router as patients_router_v1
from src.backend.api.v1.routes_analytics import router as analytics_router_v1
from src.backend.api.v1.routes_scribe import router as scribe_router_v1
from src.backend.api.v1.routes_culture import router as culture_router_v1
from src.backend.api.v1.routes_ehr import callback_router as ehr_callback_router_v1, router as ehr_router_v1
from src.backend.config import settings
from src.backend.infra.db.bootstrap import init_sql_repositories
from src.backend.services.audit.service import configure_audit_sink

app = FastAPI(title="AI Medical Transcription Detector API")

def _validate_security_configuration() -> None:
    """Reject insecure PHI deployment defaults before accepting requests."""
    if settings.app_env in {"development", "test"}:
        return
    failures = []
    if settings.app_mode == "demo":
        failures.append("APP_MODE=demo is not permitted outside development/test")
    if "*" in [o.strip() for o in settings.cors_allow_origins.split(",")]:
        failures.append("CORS_ALLOW_ORIGINS must name explicit origins")
    if any(
        urlparse(origin.strip()).scheme != "https"
        for origin in settings.cors_allow_origins.split(",")
        if origin.strip()
    ):
        failures.append("CORS_ALLOW_ORIGINS must use HTTPS origins")
    if not (settings.clerk_jwks_url or settings.clerk_jwt_public_key):
        failures.append("configure CLERK_JWKS_URL or CLERK_JWT_PUBLIC_KEY")
    if not settings.clerk_issuer:
        failures.append("configure CLERK_ISSUER")
    if min(settings.phi_audio_retention_days, settings.phi_transcript_retention_days, settings.audit_retention_days) <= 0:
        failures.append("PHI and audit retention periods must be positive")
    if not settings.audit_log_path:
        failures.append("AUDIT_LOG_PATH is required")
    smart_values = (
        settings.ochin_smart_fhir_base_url, settings.ochin_smart_issuer,
        settings.ochin_smart_client_id, settings.ochin_smart_redirect_uri,
        settings.ochin_smart_authorize_url, settings.ochin_smart_token_url,
        settings.ochin_smart_jwks_url, settings.smart_token_encryption_key,
    )
    if not all(smart_values):
        failures.append("complete OCHIN SMART authorization configuration is required")
    if failures:
        raise RuntimeError("Unsafe deployment configuration: " + "; ".join(failures))


@app.on_event("startup")
async def startup_event():
    """Application startup hook.

    When USE_SQL_REPOS is enabled and a DATABASE_URL is configured, this will
    initialize SQL-backed repositories for encounters, notes, and
    transcription jobs. In other environments (tests, local dev without a
    database), this is a no-op and the in-memory repositories remain active.
    """

    _validate_security_configuration()
    configure_audit_sink()
    if settings.app_mode != "demo" or settings.use_sql_repos:
        init_sql_repositories()


@app.on_event("shutdown")
async def shutdown_event():
    """Application shutdown hook.

    Add graceful shutdown logic here if needed (e.g., closing DB connections).
    """
    pass

# CORS defaults are development-only; startup rejects wildcard production CORS.
allow_origins = [origin.strip() for origin in settings.cors_allow_origins.split(",") if origin.strip()] or ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["system"])
async def health_check() -> dict:
    """Basic liveness probe for the API root."""
    return {"status": "ok"}


# Versioned API routers
app.include_router(system_router_v1, prefix="/api/v1")
app.include_router(transcription_router_v1, prefix="/api/v1")
app.include_router(transcription_async_router_v1, prefix="/api/v1")
app.include_router(audio_router_v1, prefix="/api/v1")
app.include_router(nlp_router_v1, prefix="/api/v1")
app.include_router(sessions_router_v1, prefix="/api/v1")
app.include_router(encounters_router_v1, prefix="/api/v1")
app.include_router(templates_router_v1, prefix="/api/v1")
app.include_router(patients_router_v1, prefix="/api/v1")
app.include_router(analytics_router_v1, prefix="/api/v1")
app.include_router(scribe_router_v1, prefix="/api/v1")
app.include_router(culture_router_v1, prefix="/api/v1")
app.include_router(ehr_router_v1, prefix="/api/v1")
app.include_router(ehr_callback_router_v1, prefix="/api/v1")
