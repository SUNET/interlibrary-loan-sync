from dataclasses import Field
from datetime import datetime
from uuid import UUID
from ill_bridge.common.enums import AdapterKeyType
from pydantic import BaseModel, ConfigDict, Field


class ProviderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID

    adapter_key: AdapterKeyType
    account_key: str
    display_name: str

    local_library_scheme: str
    local_library_code: str

    base_url: str

    enabled: bool
    writes_enabled: bool

    mapping_version: str
    config_version: int

    poll_interval_seconds: int

    capabilities: dict

    created_at: datetime
    updated_at: datetime


class ProviderCreate(BaseModel):
    adapter_key: AdapterKeyType

    account_key: str
    display_name: str

    local_library_scheme: str = "SIGEL"
    local_library_code: str

    base_url: str
    secret_ref: str

    mapping_version: str

    poll_interval_seconds: int = Field(
        default=60,
        ge=10,
    )

    capabilities: dict = Field(default_factory=dict)

    config: dict = Field(default_factory=dict)


class ProviderUpdate(BaseModel):
    """_summary_
    data = update.model_dump(
        exclude_unset=True
    )

    for field, value in data.items():
        setattr(provider, field, value)
    Args:
        BaseModel (_type_): _description_
    """

    display_name: str | None = None

    local_library_code: str | None = None

    base_url: str | None = None

    enabled: bool | None = None
    writes_enabled: bool | None = None

    poll_interval_seconds: int | None = Field(
        default=None,
        ge=10,
    )

    capabilities: dict | None = None
    config: dict | None = None
