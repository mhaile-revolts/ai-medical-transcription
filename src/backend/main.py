from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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
from src.backend.config import settings
from src.backend.infra.db.bootstrap import init_sql_repositories

app = FastAPI(title="AI Medical Transcription Detector API")


@app.on_event("startup")
async def on_startup() -> None:
    """Application startup hook.

    When USE_SQL_REPOS is enabled and a DATABASE_URL is configured, this will
    initialize SQL-backed repositories for encounters, notes, and
    transcription jobs. In other environments (tests, local dev without a
    database), this is a no-op and the in-memory repositories remain active.
    """

    init_sql_repositories()

# CORS configuration – permissive by default for development. Tighten via
# CORS_ALLOW_ORIGINS in production deployments.
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
