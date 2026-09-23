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


class SyncOperations(Base):
    __tablename__ = "sync_operations"
    __table_args__ = (
        CheckConstraint("attempts >= 0", name="sync_operations_attempts_check"),
        CheckConstraint(
            "status = ANY (ARRAY['PENDING'::text, 'IN_FLIGHT'::text, 'CONFIRMED'::text, 'REFUSED'::text, 'UNKNOWN'::text, 'ABANDONED'::text])",
            name="sync_operations_status_check",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "ill_request_id"],
            ["ill_requests.tenant_id", "ill_requests.id"],
            name="sync_operations_tenant_id_ill_request_id_fkey",
        ),
        ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name="sync_operations_tenant_id_fkey"
        ),
        PrimaryKeyConstraint("id", name="sync_operations_pkey"),
        UniqueConstraint(
            "tenant_id",
            "ill_request_id",
            "target",
            "effect_key",
            name="sync_operations_tenant_id_ill_request_id_target_effect_key_key",
        ),
        Index(
            "sync_operations_due_idx",
            "tenant_id",
            "next_attempt_at",
            postgresql_where="(status = ANY (ARRAY['PENDING'::text, 'UNKNOWN'::text]))",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    ill_request_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    target: Mapped[str] = mapped_column(Text, nullable=False)
    effect_key: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'PENDING'::text")
    )
    operation_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    fence: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("0")
    )
    result_redacted: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    external_id: Mapped[Optional[str]] = mapped_column(Text)
    expected_version: Mapped[Optional[int]] = mapped_column(BigInteger)
    lease_owner: Mapped[Optional[str]] = mapped_column(Text)
    lease_expires_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime(True)
    )
    first_attempted_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime(True)
    )
    last_attempted_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime(True)
    )
    next_attempt_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))

    ill_requests: Mapped["IllRequests"] = relationship(
        "IllRequests",
        primaryjoin="""and_(
            IllRequests.id == foreign(SyncOperations.ill_request_id),
            IllRequests.tenant_id == SyncOperations.tenant_id,
        )""",
        foreign_keys="[SyncOperations.ill_request_id]",
        back_populates="sync_operations",
    )
    tenant: Mapped["Tenants"] = relationship(
        "Tenants", back_populates="sync_operations"
    )
