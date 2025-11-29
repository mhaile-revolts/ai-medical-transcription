from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class ClinicOverviewMetrics(BaseModel):
    total_encounters: int
    total_notes: int
    finalized_notes: int
    avg_time_to_finalize_minutes: Optional[float] = None
    finalized_rate: Optional[float] = None


class ClinicianSummaryMetrics(BaseModel):
    clinician_id: str
    encounters_count: int
    notes_finalized: int
    notes_pending_review: int
    avg_finalization_delay_minutes: Optional[float] = None
