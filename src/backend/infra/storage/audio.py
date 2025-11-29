from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

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


audio_storage_backend: AudioStorageBackend = LocalAudioStorageBackend()
