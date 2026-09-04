from __future__ import annotations

from abc import ABC, abstractmethod
from contextlib import contextmanager
from pathlib import Path
import os
import tempfile
from uuid import UUID, uuid4
from typing import Any

from src.backend.config import settings


class AudioStorageBackend(ABC):
    @abstractmethod
    def save_file(self, content: bytes, *, suffix: str) -> str:
        """Persist audio bytes and return a URL/path reference."""

    @abstractmethod
    def append_file(self, dest: str, chunk: bytes) -> None:
        """Append bytes to an existing audio file reference.

        Used by the WebSocket live ingestion endpoint.
        """

    @abstractmethod
    def delete_file(self, dest: str) -> None:
        """Best-effort deletion of a previously saved file."""


class LocalAudioStorageBackend(AudioStorageBackend):
    def __init__(self) -> None:
        self._base: Path = settings.audio_upload_dir
        self._base.mkdir(parents=True, exist_ok=True)

    def save_file(self, content: bytes, *, suffix: str) -> str:
        self._base.mkdir(parents=True, exist_ok=True)
        dest_path = self._base / suffix
        dest_path.write_bytes(content)
        return str(dest_path)

    def append_file(self, dest: str, chunk: bytes) -> None:
        path = Path(dest)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("ab") as f:
            f.write(chunk)

    def delete_file(self, dest: str) -> None:
        path = Path(dest)
        if path.exists():
            try:
                path.unlink()
            except OSError:
                pass


class PostgresAudioStorageBackend(AudioStorageBackend):
    """Database-backed private audio storage (no public filesystem reference)."""
    def __init__(self, session_factory: Any) -> None:
        self._session_factory = session_factory

    def save_file(self, content: bytes, *, suffix: str) -> str:
        from src.backend.infra.db.models import AudioBlobORM
        from src.backend.tenancy import get_current_tenant
        blob_id = uuid4()
        session = self._session_factory()
        try:
            session.add(AudioBlobORM(id=blob_id, tenant_id=get_current_tenant(),
                                     filename=suffix, content=content))
            session.commit()
            return f"db-audio://{blob_id}"
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def append_file(self, dest: str, chunk: bytes) -> None:
        from src.backend.infra.db.models import AudioBlobORM
        from src.backend.tenancy import get_current_tenant
        if not dest.startswith("db-audio://"):
            raise ValueError("invalid private audio reference")
        session = self._session_factory()
        try:
            row = session.get(AudioBlobORM, UUID(dest.removeprefix("db-audio://")))
            if row is None or row.tenant_id != get_current_tenant():
                raise FileNotFoundError(dest)
            row.content += chunk
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def delete_file(self, dest: str) -> None:
        from src.backend.infra.db.models import AudioBlobORM
        from src.backend.tenancy import get_current_tenant
        if not dest.startswith("db-audio://"):
            return
        session = self._session_factory()
        try:
            row = session.get(AudioBlobORM, UUID(dest.removeprefix("db-audio://")))
            if row and row.tenant_id == get_current_tenant():
                session.delete(row)
                session.commit()
        finally:
            session.close()


audio_storage_backend: AudioStorageBackend = LocalAudioStorageBackend()


def configure_postgres_audio_storage(session_factory: Any) -> None:
    """Mutate the stable singleton so route-level imports see durable storage."""
    global audio_storage_backend
    audio_storage_backend = PostgresAudioStorageBackend(session_factory)


@contextmanager
def processing_path(reference: str):
    """Yield a filesystem path that local ASR engines can read.

    Durable audio remains private in PostgreSQL; it is materialized only for the
    duration of one ASR call and the temporary file is always removed.
    """
    backend = audio_storage_backend
    if not reference.startswith("db-audio://"):
        yield reference
        return
    if not isinstance(backend, PostgresAudioStorageBackend):
        raise RuntimeError("durable audio storage is not configured")

    from src.backend.infra.db.models import AudioBlobORM
    from src.backend.tenancy import get_current_tenant

    session = backend._session_factory()
    temp_path = None
    try:
        row = session.get(AudioBlobORM, UUID(reference.removeprefix("db-audio://")))
        if row is None or row.tenant_id != get_current_tenant():
            raise FileNotFoundError(reference)
        suffix = Path(row.filename).suffix
        with tempfile.NamedTemporaryFile(prefix="clinic-audio-", suffix=suffix, delete=False) as temp:
            temp.write(row.content)
            temp_path = temp.name
        yield temp_path
    finally:
        session.close()
        if temp_path:
            try:
                os.unlink(temp_path)
            except FileNotFoundError:
                pass
