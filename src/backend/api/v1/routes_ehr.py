from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, HttpUrl

from src.backend.domain.models.ehr_connection import EHRConnection
from src.backend.domain.models.ehr_message import EHRMessage
from src.backend.services.ehr.integration_service import ehr_integration_service
from src.backend.security import get_api_key, get_current_user, ensure_is_admin
from src.backend.tenancy import tenant_dependency, get_current_tenant
from src.backend.domain.models.clinical_encounter import ClinicalEncounter, EncounterStatus
from src.backend.services.encounters.service import encounter_service
from src.backend.services.ehr.smart_fhir_service import (
    SmartFHIRUnavailable,
    smart_fhir_service,
)
from src.backend.services.audit.service import audit_service


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


class SmartPatientResponse(BaseModel):
    id: str
    display_name: str
    birth_date: Optional[str] = None
    sex: Optional[str] = None
    source: str


class SmartEncounterResponse(BaseModel):
    id: str
    status: str
    type: Optional[str] = None
    period_start: Optional[str] = None


class SmartConfirmRequest(BaseModel):
    patient_id: str
    external_encounter_id: str
    consent_obtained: bool
    consent_method: str
    consent_version: str


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


@router.get("/smart/patients/{patient_id}", response_model=SmartPatientResponse)
async def smart_patient_lookup(patient_id: str, current_user=Depends(get_current_user)) -> SmartPatientResponse:
    try:
        patient = await smart_fhir_service.get_patient(patient_id)
    except SmartFHIRUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    audit_service.log_event(action="smart_patient_lookup", resource_type="patient", resource_id=patient.id)
    return SmartPatientResponse(
        id=patient.id, display_name=patient.display_name, birth_date=patient.birth_date,
        sex=patient.sex, source=patient.source,
    )


@router.get("/smart/patients/{patient_id}/encounters", response_model=List[SmartEncounterResponse])
async def smart_active_encounters(patient_id: str, current_user=Depends(get_current_user)) -> List[SmartEncounterResponse]:
    try:
        # Read the patient first so an encounter query cannot confirm an
        # identifier that the configured server does not recognize.
        await smart_fhir_service.get_patient(patient_id)
        encounters = await smart_fhir_service.active_encounters(patient_id)
    except SmartFHIRUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    audit_service.log_event(action="smart_encounter_lookup", resource_type="patient", resource_id=patient_id,
                            extra={"count": len(encounters)})
    return [SmartEncounterResponse(id=e.id, status=e.status, type=e.type, period_start=e.period_start) for e in encounters]


@router.post("/smart/confirm", response_model=ClinicalEncounter, status_code=status.HTTP_201_CREATED)
async def confirm_smart_encounter(
    payload: SmartConfirmRequest, current_user=Depends(get_current_user)
) -> ClinicalEncounter:
    if not payload.consent_obtained:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Recorded patient consent is required")
    if not payload.consent_method.strip() or not payload.consent_version.strip():
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Consent method and version are required")
    try:
        patient = await smart_fhir_service.get_patient(payload.patient_id)
        active = await smart_fhir_service.active_encounters(payload.patient_id)
    except SmartFHIRUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    external = next((item for item in active if item.id == payload.external_encounter_id), None)
    if external is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="FHIR encounter is not active for this patient")

    encounter = encounter_service.create_encounter(
        clinician_id=str(current_user.id), patient_id=patient.id, title="SMART/FHIR confirmed encounter"
    )
    # These evidence fields are intentionally written once at confirmation and
    # are not accepted by generic encounter update endpoints.
    encounter.external_patient_id = patient.id
    encounter.external_encounter_id = external.id
    encounter.external_encounter_status = external.status
    encounter.consent_obtained_at = datetime.now(timezone.utc)
    encounter.consent_method = payload.consent_method.strip()
    encounter.consent_version = payload.consent_version.strip()
    encounter.status = EncounterStatus.CREATED
    if encounter_service._durable():
        from src.backend.infra.db.inmemory import encounter_repository
        encounter_repository.save(encounter)
    audit_service.log_event(
        action="smart_encounter_confirmed", resource_type="clinical_encounter", resource_id=str(encounter.id),
        extra={"patient_id": patient.id, "external_encounter_id": external.id},
    )
    return encounter
