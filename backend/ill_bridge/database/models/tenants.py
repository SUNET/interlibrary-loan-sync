from __future__ import annotations

import datetime
import uuid
from typing import Optional

from sqlalchemy import (
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
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ill_bridge.common.enums import AdapterKeyType
from ill_bridge.database.base import Base


class Tenants(Base):
    __tablename__ = "tenants"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="tenants_pkey"),
        UniqueConstraint("folio_tenant_key", name="tenants_folio_tenant_key_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    folio_tenant_key: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(True), nullable=False, server_default=text("now()")
    )

    providers: Mapped[list["Providers"]] = relationship(
        "Providers", back_populates="tenant"
    )
    raw_provider_requests: Mapped[list["RawProviderRequests"]] = relationship(
        "RawProviderRequests", back_populates="tenant"
    )
    ill_requests: Mapped[list["IllRequests"]] = relationship(
        "IllRequests", back_populates="tenant"
    )
    effect_queue: Mapped[list["EffectQueue"]] = relationship(
        "EffectQueue", back_populates="tenant"
    )
    state_audit_logs: Mapped[list["StateAuditLogs"]] = relationship(
        "StateAuditLogs", back_populates="tenant"
    )
    sync_operations: Mapped[list["SyncOperations"]] = relationship(
        "SyncOperations", back_populates="tenant"
    )


