from __future__ import annotations

from enum import Enum
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel

from src.backend.services.nlp.culture_feedback_service import (
    CultureFeedbackItem,
    culture_feedback_service,
)
from src.backend.services.audit.service import audit_service
from src.backend.security import get_api_key
from src.backend.tenancy import tenant_dependency, get_current_tenant


router = APIRouter(
    prefix="/culture",
    tags=["culture"],
    dependencies=[Depends(get_api_key), Depends(tenant_dependency)],
)


class CultureIssueType(str, Enum):
    OFFENSIVE_LANGUAGE = "OFFENSIVE_LANGUAGE"
    INCORRECT_INTERPRETATION = "INCORRECT_INTERPRETATION"
    HARMFUL_SUGGESTION = "HARMFUL_SUGGESTION"
    OTHER = "OTHER"


class CultureFeedbackCreateRequest(BaseModel):
    encounter_id: Optional[UUID] = None
    job_id: Optional[UUID] = None
    note_id: Optional[UUID] = None

    community_group: Optional[str] = None
    indigenous_affiliation: Optional[str] = None

    issue_type: CultureIssueType
    comment: str


class CultureFeedbackResponse(BaseModel):
    id: UUID
    tenant_id: str
    encounter_id: Optional[UUID]
    job_id: Optional[UUID]
    note_id: Optional[UUID]
    community_group: Optional[str]
    indigenous_affiliation: Optional[str]
    issue_type: CultureIssueType
    comment: str


@router.post("/feedback", response_model=CultureFeedbackResponse, status_code=status.HTTP_201_CREATED)
async def submit_culture_feedback(payload: CultureFeedbackCreateRequest) -> CultureFeedbackResponse:
    """Submit culture/cultural-safety feedback for later review.

    This endpoint is intended for clinicians and community partners to flag
    offensive language, incorrect interpretations, or potentially harmful
    suggestions so that rules and models can be improved over time.
    """

    item: CultureFeedbackItem = culture_feedback_service.submit_feedback(
        encounter_id=payload.encounter_id,
        job_id=payload.job_id,
        note_id=payload.note_id,
        community_group=payload.community_group,
        indigenous_affiliation=payload.indigenous_affiliation,
        issue_type=payload.issue_type.value,
        comment=payload.comment,
    )

    audit_service.log_event(
        action="submit_culture_feedback",
        resource_type="culture_feedback",
        resource_id=str(item.id),
        extra={
            "tenant_id": item.tenant_id,
            "issue_type": item.issue_type,
        },
    )

    return CultureFeedbackResponse(
        id=item.id,
        tenant_id=item.tenant_id,
        encounter_id=item.encounter_id,
        job_id=item.job_id,
        note_id=item.note_id,
        community_group=item.community_group,
        indigenous_affiliation=item.indigenous_affiliation,
        issue_type=CultureIssueType(item.issue_type),
        comment=item.comment,
    )
