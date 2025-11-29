from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterable, Optional
from uuid import UUID

from src.backend.domain.models.clinical_encounter import ClinicalEncounter, EncounterStatus
from src.backend.domain.models.clinical_note import ClinicalNote
from src.backend.domain.models.transcription_job import TranscriptJob


class EncounterRepository(ABC):
    @abstractmethod
    def get(self, encounter_id: UUID) -> Optional[ClinicalEncounter]:
        raise NotImplementedError

    @abstractmethod
    def list_by_filters(
        self,
        *,
        clinician_id: Optional[str] = None,
        patient_id: Optional[str] = None,
        status: Optional[EncounterStatus] = None,
    ) -> Iterable[ClinicalEncounter]:
        raise NotImplementedError

    @abstractmethod
    def save(self, encounter: ClinicalEncounter) -> None:
        raise NotImplementedError


class ClinicalNoteRepository(ABC):
    @abstractmethod
    def get(self, note_id: UUID) -> Optional[ClinicalNote]:
        raise NotImplementedError

    @abstractmethod
    def get_by_encounter(self, encounter_id: UUID) -> Optional[ClinicalNote]:
        raise NotImplementedError

    @abstractmethod
    def save(self, note: ClinicalNote) -> None:
        raise NotImplementedError


class TranscriptionJobRepository(ABC):
    @abstractmethod
    def get(self, job_id: UUID) -> Optional[TranscriptJob]:
        raise NotImplementedError
