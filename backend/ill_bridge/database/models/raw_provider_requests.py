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


class RawProviderRequests(Base):
    __tablename__ = "raw_provider_requests"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name="raw_provider_requests_tenant_id_fkey"
        ),
        PrimaryKeyConstraint("id", name="raw_provider_requests_pkey"),
        UniqueConstraint(
            "tenant_id",
            "source_key",
            "event_key",
            name="raw_provider_requests_tenant_id_source_key_event_key_key",
        ),
        Index(
            "raw_provider_requests_unprocessed_idx",
            "tenant_id",
            "received_at",
            postgresql_where="(processed_at IS NULL)",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    source_key: Mapped[str] = mapped_column(Text, nullable=False)
    event_key: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    payload_hash: Mapped[str] = mapped_column(Text, nullable=False)
    received_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(True), nullable=False, server_default=text("now()")
    )
    schema_version: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("1")
    )
    provider_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    processed_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))
    result: Mapped[Optional[str]] = mapped_column(Text)

    tenant: Mapped["Tenants"] = relationship(
        "Tenants", back_populates="raw_provider_requests"
    )


