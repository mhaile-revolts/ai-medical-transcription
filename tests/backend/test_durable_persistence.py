from datetime import datetime, timezone
import os
import subprocess
import sys
import textwrap
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy import inspect, text
from alembic import command
from alembic.config import Config

from src.backend.domain.models.clinical_encounter import ClinicalEncounter
from src.backend.domain.models.clinical_note import ClinicalNote, ClinicalNoteSection
from src.backend.domain.models.transcription_job import TranscriptJob, TranscriptJobStatus
from src.backend.infra.db.models import Base
import src.backend.infra.db.models_notes_jobs  # noqa: F401
from src.backend.infra.db.session import create_sqlalchemy_session_factory
from src.backend.infra.db.sql_encounters import SqlEncounterRepository
from src.backend.infra.db.sql_notes_jobs import SqlClinicalNoteRepository, SqlTranscriptionJobRepository
from src.backend.infra.storage.audio import PostgresAudioStorageBackend, processing_path
from src.backend.infra.storage import audio as audio_module
from src.backend.services.users.service import InMemoryUserService
from src.backend.domain.models.user import UserRole
from src.backend.services.conversation.service import InMemoryConversationService


def test_records_and_private_audio_survive_repository_reconstruction(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'clinic.db'}"
    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
    factory = create_sqlalchemy_session_factory(database_url)

    encounter_id = uuid4()
    job_id = uuid4()
    note_id = uuid4()
    now = datetime.now(timezone.utc)
    encounters = SqlEncounterRepository(factory)
    notes = SqlClinicalNoteRepository(factory)
    jobs = SqlTranscriptionJobRepository(factory)
    storage = PostgresAudioStorageBackend(factory)

    audio_ref = storage.save_file(b"private-audio", suffix="visit.wav")
    jobs.save(TranscriptJob(
        id=job_id, created_at=now, status=TranscriptJobStatus.COMPLETED,
        audio_url=audio_ref, result_text="persistent transcript", tenant_id="default",
    ))
    encounters.save(ClinicalEncounter(
        id=encounter_id, created_at=now, transcription_job_ids=[job_id],
        assigned_scribe_id="scribe-1", tenant_id="default",
    ))
    notes.save(ClinicalNote(
        id=note_id, encounter_id=encounter_id, created_at=now, updated_at=now,
        subjective=ClinicalNoteSection(text="persistent note"),
        objective=ClinicalNoteSection(text=""), assessment=ClinicalNoteSection(text=""),
        plan=ClinicalNoteSection(text=""), tenant_id="default",
    ))

    # Reconstruct every adapter to simulate a backend process restart.
    restarted_factory = create_sqlalchemy_session_factory(database_url)
    assert SqlEncounterRepository(restarted_factory).get(encounter_id).assigned_scribe_id == "scribe-1"
    assert SqlClinicalNoteRepository(restarted_factory).get(note_id).subjective.text == "persistent note"
    assert SqlTranscriptionJobRepository(restarted_factory).get(job_id).result_text == "persistent transcript"

    old_backend = audio_module.audio_storage_backend
    audio_module.audio_storage_backend = PostgresAudioStorageBackend(restarted_factory)
    try:
        with processing_path(audio_ref) as path:
            with open(path, "rb") as materialized:
                assert materialized.read() == b"private-audio"
    finally:
        audio_module.audio_storage_backend = old_backend


def test_users_survive_service_reconstruction(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'users.db'}"
    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
    factory = create_sqlalchemy_session_factory(database_url)

    users = InMemoryUserService()
    users.configure_persistence(factory)
    created = users.upsert_user_for_subject(
        subject="stable-subject", email="clinician@example.com", role=UserRole.CLINICIAN,
    )

    restarted_users = InMemoryUserService()
    restarted_users.configure_persistence(create_sqlalchemy_session_factory(database_url))
    loaded = restarted_users.get_user_by_subject("stable-subject")
    assert loaded is not None
    assert loaded.id == created.id
    assert loaded.role == UserRole.CLINICIAN


def test_conversation_session_and_job_link_survive_service_reconstruction(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'sessions.db'}"
    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
    factory = create_sqlalchemy_session_factory(database_url)

    sessions = InMemoryConversationService()
    sessions.configure_persistence(factory)
    created = sessions.create_session(title="Persistent visit")
    job_id = uuid4()
    sessions.attach_job(created.id, job_id)

    restarted = InMemoryConversationService()
    restarted.configure_persistence(create_sqlalchemy_session_factory(database_url))
    loaded = restarted.get_session(created.id)
    assert loaded is not None
    assert loaded.title == "Persistent visit"
    assert loaded.transcription_job_ids == [job_id]


def test_migrated_durable_app_processes_audio_and_survives_restart(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'durable-app.db'}"
    script = textwrap.dedent(
        """
        from alembic import command
        from alembic.config import Config

        command.upgrade(Config("alembic.ini"), "head")

        from starlette.testclient import TestClient
        from src.backend.main import app
        from src.backend.services.transcription.service import transcription_service

        class FileReadingASR:
            def transcribe(self, audio_url, language_code=None):
                with open(audio_url, "rb") as audio:
                    return audio.read().decode("utf-8")

        transcription_service._asr_backend = FileReadingASR()
        with TestClient(app) as client:
            session_response = client.post(
                "/api/v1/sessions/",
                json={"title": "Durable session"},
                headers={"X-Tenant-ID": "durable-clinic"},
            )
            assert session_response.status_code == 201
            session_id = session_response.json()["id"]
            with client.websocket_connect(
                f"/api/v1/audio/ws?session_id={session_id}",
                headers={"X-Tenant-ID": "durable-clinic"},
            ) as websocket:
                websocket.send_bytes(b"durable audio")
                partial = websocket.receive_json()
                assert partial["partial_text"] == "durable audio"
                websocket.send_text("stop")
                final = websocket.receive_json()
                assert final["job"]["result_text"] == "durable audio"
                job_id = final["job"]["id"]

        from uuid import UUID
        from src.backend.infra.db.session import create_sqlalchemy_session_factory
        from src.backend.infra.db.sql_notes_jobs import SqlTranscriptionJobRepository
        from src.backend.services.conversation.service import InMemoryConversationService
        from src.backend.tenancy import set_current_tenant, reset_current_tenant

        token = set_current_tenant("durable-clinic")
        try:
            factory = create_sqlalchemy_session_factory(__import__("os").environ["DATABASE_URL"])
            restarted_sessions = InMemoryConversationService()
            restarted_sessions.configure_persistence(factory)
            session = restarted_sessions.get_session(UUID(session_id))
            assert session is not None
            assert UUID(job_id) in session.transcription_job_ids
            assert SqlTranscriptionJobRepository(factory).get(UUID(job_id)).result_text == "durable audio"
        finally:
            reset_current_tenant(token)
        """
    )
    env = os.environ.copy()
    env.update(
        APP_MODE="durable",
        DATABASE_URL=database_url,
        PYTHONPATH=".",
    )
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=os.getcwd(),
        env=env,
        text=True,
        capture_output=True,
        timeout=60,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_migration_upgrades_legacy_encounters_without_losing_records(tmp_path, monkeypatch):
    database_url = f"sqlite:///{tmp_path / 'legacy.db'}"
    engine = create_engine(database_url)
    legacy_id = str(uuid4())
    with engine.begin() as connection:
        connection.execute(text(
            "CREATE TABLE encounters ("
            "id CHAR(32) PRIMARY KEY, created_at DATETIME NOT NULL, "
            "clinician_id VARCHAR, patient_id VARCHAR, status VARCHAR NOT NULL, "
            "title VARCHAR, transcription_job_ids VARCHAR, tenant_id VARCHAR NOT NULL)"
        ))
        connection.execute(
            text(
                "INSERT INTO encounters "
                "(id, created_at, status, title, tenant_id) "
                "VALUES (:id, :created_at, 'CREATED', 'Legacy visit', 'default')"
            ),
            {"id": legacy_id.replace("-", ""), "created_at": datetime.now(timezone.utc)},
        )

    monkeypatch.setenv("DATABASE_URL", database_url)
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "head")

    columns = {column["name"] for column in inspect(engine).get_columns("encounters")}
    assert "assigned_scribe_id" in columns
    with engine.connect() as connection:
        assert connection.execute(
            text("SELECT title FROM encounters WHERE id = :id"),
            {"id": legacy_id.replace("-", "")},
        ).scalar_one() == "Legacy visit"