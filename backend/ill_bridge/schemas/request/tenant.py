from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class TenantCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    folio_tenant_key: str = Field(min_length=1)
    name: str = Field(min_length=1)
    infodisk_email: str | None = None


class TenantRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    folio_tenant_key: str
    name: str
    infodisk_email: str | None = None
    created_at: datetime
