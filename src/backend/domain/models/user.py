from __future__ import annotations

from enum import Enum
from uuid import UUID

from pydantic import BaseModel, EmailStr


class UserRole(str, Enum):
    CLINICIAN = "clinician"
    ADMIN = "admin"
    SCRIBE = "scribe"


class User(BaseModel):
    id: UUID
    email: EmailStr
    role: UserRole
    # Tenant that this user belongs to. For the MVP we model this as a simple
    # string identifier (e.g., clinic slug or UUID string).
    tenant_id: str
