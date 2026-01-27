from __future__ import annotations

from datetime import datetime
from typing import List, Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, HttpUrl

from src.backend.domain.models.ehr_connection import EHRConnection
from src.backend.domain.models.ehr_message import EHRMessage
from src.backend.services.ehr.integration_service import ehr_integration_service
from src.backend.security import get_api_key, get_current_user, ensure_is_admin
from src.backend.tenancy import tenant_dependency, get_current_tenant


router = APIRouter(
    prefix="/ehr",
    tags=["ehr"],
    dependencies=[Depends(get_api_key), Depends(tenant_dependency)],
)


class EHRConnectionCreateRequest(BaseModel):
    name: str
    base_url: Optional[HttpUrl] = None
    auth_type: str = "none"
    auth_config: dict = {}
    supported_capabilities: List[str] = []
    is_active: bool = True


class EHRConnectionResponse(EHRConnectionCreateRequest):
    id: UUID
    tenant_id: str
    created_at: datetime
    updated_at: datetime


class EHRMessageSummary(BaseModel):
    id: UUID
    status: str
    direction: str
    resource_type: str
    related_encounter_id: Optional[UUID] = None
    related_note_id: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime


@router.get("/connections", response_model=List[EHRConnectionResponse])
async def list_connections(current_user=Depends(get_current_user)) -> List[EHRConnectionResponse]:
    ensure_is_admin(current_user)
    tenant_id = get_current_tenant()
    conns = ehr_integration_service.list_active_connections()
    return [
        EHRConnectionResponse(
            id=c.id,
            tenant_id=c.tenant_id,
            name=c.name,
            base_url=c.base_url,
            auth_type=c.auth_type,
            auth_config=c.auth_config,
            supported_capabilities=c.supported_capabilities,
            is_active=c.is_active,
            created_at=c.created_at,
            updated_at=c.updated_at,
        )
        for c in conns
        if c.tenant_id == tenant_id
    ]


@router.post("/connections", response_model=EHRConnectionResponse, status_code=status.HTTP_201_CREATED)
async def create_connection(
    payload: EHRConnectionCreateRequest,
    current_user=Depends(get_current_user),
) -> EHRConnectionResponse:
    ensure_is_admin(current_user)
    tenant_id = get_current_tenant()
    now = datetime.utcnow()
    conn = EHRConnection(
        id=uuid4(),
        tenant_id=tenant_id,
        name=payload.name,
        base_url=payload.base_url,
        auth_type=payload.auth_type,  # type: ignore[arg-type]
        auth_config=payload.auth_config,
        supported_capabilities=payload.supported_capabilities,
        is_active=payload.is_active,
        created_at=now,
        updated_at=now,
    )
    ehr_integration_service.save_connection(conn)
    return EHRConnectionResponse(**conn.model_dump())


@router.get("/messages", response_model=List[EHRMessageSummary])
async def list_messages(
    status_filter: Optional[str] = None,
    current_user=Depends(get_current_user),
) -> List[EHRMessageSummary]:
    ensure_is_admin(current_user)
    statuses = (status_filter,) if status_filter else ("pending", "failed", "sent")
    messages: List[EHRMessage] = ehr_integration_service.list_messages_by_status(*statuses)
    return [
        EHRMessageSummary(
            id=m.id,
            status=m.status,
            direction=m.direction,
            resource_type=m.resource_type,
            related_encounter_id=m.related_encounter_id,
            related_note_id=m.related_note_id,
            created_at=m.created_at,
            updated_at=m.updated_at,
        )
        for m in messages
    ]
