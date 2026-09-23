from __future__ import annotations

import datetime
import uuid
from typing import Optional

from sqlalchemy import (
    and_,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKeyConstraint,
    Index,
    Integer,
    PrimaryKeyConstraint,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, foreign, mapped_column, relationship

from ill_bridge.common.enums import AdapterKeyType
from ill_bridge.database.base import Base


class Providers(Base):
    __tablename__ = "providers"
    __table_args__ = (
        CheckConstraint(
            "poll_interval_seconds >= 10", name="providers_poll_interval_seconds_check"
        ),
        ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name="providers_tenant_id_fkey"
        ),
        PrimaryKeyConstraint("id", name="providers_pkey"),
        UniqueConstraint(
            "tenant_id",
            "adapter_key",
            "account_key",
            name="providers_tenant_id_adapter_key_account_key_key",
        ),
        UniqueConstraint("tenant_id", "id", name="providers_tenant_id_id_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    adapter_key: Mapped[AdapterKeyType] = mapped_column(
        Enum(
            AdapterKeyType,
            values_callable=lambda cls: [member.value for member in cls],
            name="adapter_key_type",
        ),
        nullable=False,
        server_default=text("'libris'::adapter_key_type"),
    )
    account_key: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    local_library_scheme: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'SIGEL'::text")
    )
    local_library_code: Mapped[str] = mapped_column(Text, nullable=False)
    base_url: Mapped[str] = mapped_column(Text, nullable=False)
    secret_ref: Mapped[str] = mapped_column(Text, nullable=False)
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    writes_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    mapping_version: Mapped[str] = mapped_column(Text, nullable=False)
    config_version: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("1")
    )
    poll_interval_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("60")
    )
    capabilities: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    config: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(True), nullable=False, server_default=text("now()")
    )

    tenant: Mapped["Tenants"] = relationship("Tenants", back_populates="providers")
    ill_requests: Mapped[list["IllRequests"]] = relationship(
        "IllRequests",
        primaryjoin="""and_(
            Providers.id == foreign(IllRequests.provider_id),
            Providers.tenant_id == IllRequests.tenant_id,
        )""",
        foreign_keys="[IllRequests.provider_id]",
        back_populates="providers",
    )


