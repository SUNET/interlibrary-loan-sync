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


class StateAuditLogs(Base):
    __tablename__ = "state_audit_logs"
    __table_args__ = (
        CheckConstraint(
            "actor_type = ANY (ARRAY['STAFF'::text, 'PROVIDER'::text, 'FOLIO'::text, 'SYSTEM'::text])",
            name="state_audit_logs_actor_type_check",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "ill_request_id"],
            ["ill_requests.tenant_id", "ill_requests.id"],
            name="state_audit_logs_tenant_id_ill_request_id_fkey",
        ),
        ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name="state_audit_logs_tenant_id_fkey"
        ),
        PrimaryKeyConstraint("id", name="state_audit_logs_pkey"),
        Index(
            "state_audit_logs_timeline_idx",
            "tenant_id",
            "ill_request_id",
            "recorded_at",
            "id",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    actor_type: Mapped[str] = mapped_column(Text, nullable=False)
    correlation_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    recorded_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(True), nullable=False, server_default=text("now()")
    )
    details_redacted: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    ill_request_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    from_state: Mapped[Optional[str]] = mapped_column(Text)
    to_state: Mapped[Optional[str]] = mapped_column(Text)
    actor_id: Mapped[Optional[str]] = mapped_column(Text)
    reason: Mapped[Optional[str]] = mapped_column(Text)
    source_event_key: Mapped[Optional[str]] = mapped_column(Text)
    causation_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    mapping_version: Mapped[Optional[str]] = mapped_column(Text)
    request_version: Mapped[Optional[int]] = mapped_column(BigInteger)
    occurred_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))

    ill_requests: Mapped[Optional["IllRequests"]] = relationship(
        "IllRequests",
        primaryjoin="""and_(
            IllRequests.id == foreign(StateAuditLogs.ill_request_id),
            IllRequests.tenant_id == StateAuditLogs.tenant_id,
        )""",
        foreign_keys="[StateAuditLogs.ill_request_id]",
        back_populates="state_audit_logs",
    )
    tenant: Mapped["Tenants"] = relationship(
        "Tenants", back_populates="state_audit_logs"
    )


