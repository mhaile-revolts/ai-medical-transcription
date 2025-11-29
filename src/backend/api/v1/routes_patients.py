from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends

from src.backend.domain.models.patient_timeline import TimelineEvent
from src.backend.security import get_api_key
from src.backend.tenancy import tenant_dependency
from src.backend.services.patients.summary_service import patient_summary_service


router = APIRouter(
    prefix="/patients",
    tags=["patients"],
    dependencies=[Depends(get_api_key), Depends(tenant_dependency)],
)


@router.get("/{patient_id}/timeline", response_model=List[TimelineEvent])
async def get_patient_timeline(patient_id: str) -> List[TimelineEvent]:
    return patient_summary_service.build_timeline(patient_id)
