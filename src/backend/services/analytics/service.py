from __future__ import annotations

from datetime import timedelta
from typing import Optional

from src.backend.domain.models.analytics import ClinicOverviewMetrics, ClinicianSummaryMetrics
from src.backend.domain.models.clinical_encounter import ClinicalEncounter, EncounterStatus
from src.backend.infra.db.inmemory import encounter_repository, clinical_note_repository


class AnalyticsService:
    def compute_clinic_overview(self) -> ClinicOverviewMetrics:
        encounters = list(encounter_repository.list_by_filters())
        total_encounters = len(encounters)

        notes = []
        finalized_durations: list[timedelta] = []
        finalized_count = 0

        for enc in encounters:
            note = clinical_note_repository.get_by_encounter(enc.id)
            if note is None:
                continue
            notes.append(note)
            if note.is_finalized and enc.created_at <= note.updated_at:
                finalized_count += 1
                finalized_durations.append(note.updated_at - enc.created_at)

        total_notes = len(notes)
        avg_minutes: Optional[float] = None
        finalized_rate: Optional[float] = None

        if finalized_durations:
            avg_minutes = sum((d.total_seconds() for d in finalized_durations)) / 60.0 / len(finalized_durations)
        if total_notes:
            finalized_rate = finalized_count / total_notes

        return ClinicOverviewMetrics(
            total_encounters=total_encounters,
            total_notes=total_notes,
            finalized_notes=finalized_count,
            avg_time_to_finalize_minutes=avg_minutes,
            finalized_rate=finalized_rate,
        )

    def compute_clinician_summary(self, clinician_id: str) -> ClinicianSummaryMetrics:
        encounters = list(encounter_repository.list_by_filters(clinician_id=clinician_id))
        notes_finalized = 0
        notes_pending = 0
        durations: list[timedelta] = []

        for enc in encounters:
            note = clinical_note_repository.get_by_encounter(enc.id)
            if note is None:
                continue
            if note.is_finalized:
                notes_finalized += 1
                if enc.created_at <= note.updated_at:
                    durations.append(note.updated_at - enc.created_at)
            elif enc.status == EncounterStatus.READY_FOR_REVIEW:
                notes_pending += 1

        avg_delay: Optional[float] = None
        if durations:
            avg_delay = sum((d.total_seconds() for d in durations)) / 60.0 / len(durations)

        return ClinicianSummaryMetrics(
            clinician_id=clinician_id,
            encounters_count=len(encounters),
            notes_finalized=notes_finalized,
            notes_pending_review=notes_pending,
            avg_finalization_delay_minutes=avg_delay,
        )


analytics_service = AnalyticsService()
