from __future__ import annotations

from fastapi import APIRouter, Depends

from src.backend.domain.models.analytics import ClinicOverviewMetrics, ClinicianSummaryMetrics
from src.backend.security import get_api_key, get_current_user
from src.backend.tenancy import tenant_dependency
from src.backend.services.analytics.service import analytics_service
from src.backend.domain.models.user import User


router = APIRouter(
    prefix="/analytics",
    tags=["analytics"],
    dependencies=[Depends(get_api_key), Depends(tenant_dependency)],
)


@router.get("/clinic-overview", response_model=ClinicOverviewMetrics)
async def clinic_overview(current_user: User = Depends(get_current_user)) -> ClinicOverviewMetrics:
    # Metrics are tenant-scoped by repositories; no extra filtering needed here.
    return analytics_service.compute_clinic_overview()


@router.get("/clinician-summary", response_model=ClinicianSummaryMetrics)
async def clinician_summary(
    clinician_id: str | None = None,
    current_user: User = Depends(get_current_user),
) -> ClinicianSummaryMetrics:
    target_id = clinician_id or str(current_user.id)
    return analytics_service.compute_clinician_summary(target_id)
