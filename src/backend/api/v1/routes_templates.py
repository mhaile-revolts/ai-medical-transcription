from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel

from src.backend.domain.models.note_template import NoteTemplate, NoteTemplateSection
from src.backend.security import get_api_key
from src.backend.tenancy import tenant_dependency
from src.backend.services.templates.service import template_service


router = APIRouter(
    prefix="/templates",
    tags=["templates"],
    dependencies=[Depends(get_api_key), Depends(tenant_dependency)],
)


class CreateTemplateRequest(BaseModel):
    name: str
    specialty: str
    visit_type: Optional[str] = None
    sections: List[NoteTemplateSection]


@router.get("/", response_model=List[NoteTemplate])
async def list_templates(
    specialty: Optional[str] = None,
    visit_type: Optional[str] = None,
) -> List[NoteTemplate]:
    return template_service.list_templates(specialty=specialty, visit_type=visit_type)


@router.post("/", response_model=NoteTemplate, status_code=status.HTTP_201_CREATED)
async def create_template(payload: CreateTemplateRequest) -> NoteTemplate:
    return template_service.create_template(
        name=payload.name,
        specialty=payload.specialty,
        visit_type=payload.visit_type,
        sections=payload.sections,
    )
