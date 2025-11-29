from __future__ import annotations

from typing import Optional

from sqlalchemy import create_engine

from src.backend.config import settings
from src.backend.infra.db.models import Base
from src.backend.infra.db.session import create_sqlalchemy_session_factory
from src.backend.infra.db.sql_encounters import SqlEncounterRepository
from src.backend.infra.db.sql_notes_jobs import SqlClinicalNoteRepository, SqlTranscriptionJobRepository
from src.backend.infra.db import inmemory as inmemory_repos


def init_sql_repositories(database_url: Optional[str] = None) -> None:  # pragma: no cover - side-effectful wiring
    """Optionally switch in-memory repositories to SQL-backed implementations.

    This helper is intended to be called from an application bootstrap path
    (for example, when starting the API server in a non-test environment).
    If USE_SQL_REPOS is not enabled or DATABASE_URL is not configured, this is
    a no-op and the in-memory repositories remain active.
    """

    if not settings.use_sql_repos:
        return

    db_url = database_url or settings.database_url
    if not db_url:
        # Misconfigured: requested SQL repos but no database URL. Leave
        # in-memory repos in place.
        return

    engine = create_engine(db_url, future=True)

    # Create tables if they do not exist. In a real deployment this should be
    # handled by migrations, but this is convenient for early MVP setups.
    Base.metadata.create_all(engine)

    session_factory = create_sqlalchemy_session_factory(db_url)

    # Swap repository singletons to SQL-backed implementations so that existing
    # imports (e.g., encounter_repository from infra.db.inmemory) now point at
    # real DB-backed repositories.
    inmemory_repos.encounter_repository = SqlEncounterRepository(session_factory)  # type: ignore[assignment]
    inmemory_repos.clinical_note_repository = SqlClinicalNoteRepository(session_factory)  # type: ignore[assignment]
    inmemory_repos.transcription_job_repository = SqlTranscriptionJobRepository(session_factory)  # type: ignore[assignment]
