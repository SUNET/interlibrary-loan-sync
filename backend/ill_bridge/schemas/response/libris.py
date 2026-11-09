from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class RawProviderRequestRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    provider_id: UUID | None = None
    source_key: str
    event_key: str
    payload: dict[str, Any]
    payload_hash: str
    schema_version: int
    received_at: datetime
    processed_at: datetime | None = None
    result: str | None = None


class IllRequestRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    provider_id: UUID
    external_request_id: str
    direction: str
    request_type: str
    processing_state: str
    requesting_library: dict[str, Any]
    bibliographic: dict[str, Any]
    extensions: dict[str, Any]
    mapping_version: str
    schema_version: int
    version: int
    created_at: datetime
    updated_at: datetime
    provider_record_id: str | None = None
    workflow_state: str | None = None
    active_lending_library: dict[str, Any] | None = None
    provider_status_raw: str | None = None
    provider_status_code: str | None = None
    provider_revision: str | None = None
    observed_at: datetime | None = None
    source_updated_at: datetime | None = None
    closed_at: datetime | None = None


class EffectQueueRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    subject_type: str
    subject_id: UUID
    kind: str
    payload: dict[str, Any]
    effect_key: str
    available_at: datetime
    attempts: int
    fence: int
    published_at: datetime | None = None
    claimed_by: str | None = None
    claimed_until: datetime | None = None
    last_error: str | None = None


class RequestPartyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    ill_request_id: UUID
    role: str
    scheme: str
    code: str
    ordinal: int
    is_active: bool
    response_code: str | None = None
    response_at: datetime | None = None
    location: str | None = None


class StateAuditLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    ill_request_id: UUID | None = None
    event_type: str
    actor_type: str
    correlation_id: UUID
    recorded_at: datetime
    details_redacted: dict[str, Any]
    from_state: str | None = None
    to_state: str | None = None
    actor_id: str | None = None
    reason: str | None = None
    source_event_key: str | None = None
    causation_id: UUID | None = None
    mapping_version: str | None = None
    request_version: int | None = None
    occurred_at: datetime | None = None
