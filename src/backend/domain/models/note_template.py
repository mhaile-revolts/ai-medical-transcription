from __future__ import annotations

from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel


class NoteTemplateSection(BaseModel):
    id: str
    title: str
    hint: Optional[str] = None


class NoteTemplate(BaseModel):
    id: UUID
    tenant_id: str
    name: str
    specialty: str
    visit_type: Optional[str] = None
    sections: List[NoteTemplateSection]
    is_default: bool = False
