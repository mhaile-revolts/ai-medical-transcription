"""Durable capture-id claims used by the audio upload route."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4
from sqlalchemy.exc import IntegrityError

from src.backend.infra.db.models_notes_jobs import AudioUploadIdempotencyORM
from src.backend.infra.db.session import SessionFactory


class AudioUploadIdempotencyService:
    def __init__(self) -> None:
        self._session_factory: SessionFactory | None = None

    def configure_persistence(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    def claim(self, *, tenant_id: str, clinician_id: str, encounter_id: UUID, capture_id: str) -> tuple[UUID, str]:
        if self._session_factory is None:
            raise RuntimeError("Durable audio upload idempotency is not configured")
        session = self._session_factory()
        now = datetime.now(timezone.utc)
        proposed_job_id = uuid4()
        try:
            row = AudioUploadIdempotencyORM(
                id=uuid4(), tenant_id=tenant_id, clinician_id=clinician_id,
                encounter_id=encounter_id, capture_id=capture_id, job_id=proposed_job_id,
                state="pending", lease_expires_at=now + timedelta(minutes=2),
                created_at=now, updated_at=now,
            )
            session.add(row)
            session.commit()
            return proposed_job_id, "claimed"
        except IntegrityError:
            session.rollback()
            existing = session.query(AudioUploadIdempotencyORM).filter_by(
                tenant_id=tenant_id, clinician_id=clinician_id,
                encounter_id=encounter_id, capture_id=capture_id,
            ).one()
            if existing.state == "complete":
                return existing.job_id, "complete"
            if existing.state == "failed" or (
                existing.lease_expires_at is not None and existing.lease_expires_at <= now
            ):
                existing.state = "pending"
                existing.lease_expires_at = now + timedelta(minutes=2)
                existing.updated_at = now
                session.commit()
                return existing.job_id, "claimed"
            return existing.job_id, "pending"
        finally:
            session.close()

    def complete(self, job_id: UUID) -> None:
        self._set_state(job_id, "complete")

    def fail(self, job_id: UUID) -> None:
        self._set_state(job_id, "failed")

    def state(self, job_id: UUID) -> str | None:
        if self._session_factory is None:
            raise RuntimeError("Durable audio upload idempotency is not configured")
        session = self._session_factory()
        try:
            row = session.query(AudioUploadIdempotencyORM).filter_by(job_id=job_id).one_or_none()
            return row.state if row is not None else None
        finally:
            session.close()

    def _set_state(self, job_id: UUID, state: str) -> None:
        if self._session_factory is None:
            raise RuntimeError("Durable audio upload idempotency is not configured")
        session = self._session_factory()
        try:
            row = session.query(AudioUploadIdempotencyORM).filter_by(job_id=job_id).one()
            row.state = state
            row.lease_expires_at = None
            row.updated_at = datetime.now(timezone.utc)
            session.commit()
        finally:
            session.close()


audio_upload_idempotency_service = AudioUploadIdempotencyService()