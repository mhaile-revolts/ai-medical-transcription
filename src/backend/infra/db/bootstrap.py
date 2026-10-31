from __future__ import annotations

from typing import Optional

from sqlalchemy import create_engine, inspect, text

from src.backend.config import settings
from src.backend.infra.db.models import Base
from src.backend.infra.db.session import create_sqlalchemy_session_factory
from src.backend.infra.db.sql_encounters import SqlEncounterRepository
from src.backend.infra.db.sql_notes_jobs import SqlClinicalNoteRepository, SqlTranscriptionJobRepository
from src.backend.infra.db import inmemory as inmemory_repos
from src.backend.infra.db import ehr_inmemory as ehr_repos
from src.backend.infra.db.sql_ehr import SqlEHRConnectionRepository, SqlEHRMessageRepository
from src.backend.services.users.service import user_service
from src.backend.services.conversation.service import conversation_service
from src.backend.infra.storage.audio import configure_postgres_audio_storage
from src.backend.services.audio_upload_idempotency import audio_upload_idempotency_service

REQUIRED_SCHEMA_REVISION = "0008_transcription_language_confidence"


def init_sql_repositories(database_url: Optional[str] = None) -> None:  # pragma: no cover - side-effectful wiring
    """Optionally switch in-memory repositories to SQL-backed implementations.

    This helper is intended to be called from an application bootstrap path
    (for example, when starting the API server in a non-test environment).
    If USE_SQL_REPOS is not enabled or DATABASE_URL is not configured, this is
    a no-op and the in-memory repositories remain active.
    """

    if settings.app_mode == "demo" and not settings.use_sql_repos:
        return

    db_url = database_url or settings.database_url
    if not db_url:
        raise RuntimeError("DATABASE_URL is required when APP_MODE is not demo")

    engine = create_engine(db_url, future=True)

    # Readiness must happen before serving requests. Schema creation is not
    # performed here: production deployments must apply Alembic revisions.
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    required_tables = {
        "encounters", "clinical_notes", "transcription_jobs", "users", "audio_blobs",
        "conversation_sessions", "ehr_connections", "ehr_messages", "smart_tokens",
        "smart_authorization_states", "audio_upload_idempotency",
    }
    missing_tables = required_tables - set(inspect(engine).get_table_names())
    if missing_tables:
        raise RuntimeError(
            "Database schema is not ready; run 'alembic upgrade head' "
            f"(missing: {', '.join(sorted(missing_tables))})"
        )
    with engine.connect() as connection:
        revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one_or_none()
    if revision != REQUIRED_SCHEMA_REVISION:
        raise RuntimeError(
            "Database migration revision is not current; run 'alembic upgrade head' "
            f"(expected {REQUIRED_SCHEMA_REVISION}, found {revision or 'none'})"
        )

    session_factory = create_sqlalchemy_session_factory(db_url)

    # Swap repository singletons to SQL-backed implementations so that existing
    # imports (e.g., encounter_repository from infra.db.inmemory) now point at
    # real DB-backed repositories.
    inmemory_repos.encounter_repository.set_target(SqlEncounterRepository(session_factory))
    inmemory_repos.clinical_note_repository.set_target(SqlClinicalNoteRepository(session_factory))
    inmemory_repos.transcription_job_repository.set_target(SqlTranscriptionJobRepository(session_factory))
    ehr_repos.ehr_connection_repository.set_target(SqlEHRConnectionRepository(session_factory))
    ehr_repos.ehr_message_repository.set_target(SqlEHRMessageRepository(session_factory))
    user_service.configure_persistence(session_factory)
    conversation_service.configure_persistence(session_factory)
    configure_postgres_audio_storage(session_factory)
    audio_upload_idempotency_service.configure_persistence(session_factory)
