from __future__ import annotations

from typing import List

from src.backend.domain.models.patient_timeline import TimelineEvent, TimelineEventType
from src.backend.infra.db.inmemory import encounter_repository, clinical_note_repository


class PatientSummaryService:
    """Build a lightweight patient timeline from encounters and notes."""

    def build_timeline(self, patient_id: str) -> List[TimelineEvent]:
        events: List[TimelineEvent] = []

        # Encounters for this patient are already tenant-scoped by repository.
        for enc in encounter_repository.list_by_filters(patient_id=patient_id):
            events.append(
                TimelineEvent(
                    type=TimelineEventType.ENCOUNTER,
                    timestamp=enc.created_at,
                    encounter_id=enc.id,
                    label=enc.title or "Encounter",
                    details=None,
                )
            )

            note = clinical_note_repository.get_by_encounter(enc.id)
            if note is not None:
                # Very naive extraction of diagnoses/medications from the text; in
                # a real implementation this would pull from structured NLP
                # entities or codes.
                if note.assessment.text:
                    events.append(
                        TimelineEvent(
                            type=TimelineEventType.DIAGNOSIS,
                            timestamp=note.updated_at,
                            encounter_id=enc.id,
                            label="Assessment",
                            details=note.assessment.text,
                        )
                    )
                if note.plan.text:
                    events.append(
                        TimelineEvent(
                            type=TimelineEventType.MEDICATION,
                            timestamp=note.updated_at,
                            encounter_id=enc.id,
                            label="Plan",
                            details=note.plan.text,
                        )
                    )

        events.sort(key=lambda e: e.timestamp)
        return events


patient_summary_service = PatientSummaryService()
