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


class IllRequests(Base):
    __tablename__ = "ill_requests"
    __table_args__ = (
        CheckConstraint(
            "direction = ANY (ARRAY['BORROWING'::text, 'LENDING'::text])",
            name="ill_requests_direction_check",
        ),
        CheckConstraint(
            "processing_state = ANY (ARRAY['PENDING'::text, 'IN_SYNC'::text, 'RETRYING'::text, 'NEEDS_REVIEW'::text, 'CONFLICT'::text, 'PAUSED'::text])",
            name="ill_requests_processing_state_check",
        ),
        CheckConstraint(
            "request_type = ANY (ARRAY['LOAN'::text, 'COPY'::text])",
            name="ill_requests_request_type_check",
        ),
        CheckConstraint(
            "workflow_state = ANY (ARRAY['REQUESTED'::text, 'ACCEPTED'::text, 'ON_HOLD'::text, 'IN_TRANSIT'::text, 'RECEIVED'::text, 'READY_FOR_PICKUP'::text, 'ON_LOAN'::text, 'RETURN_PENDING'::text, 'RETURN_IN_TRANSIT'::text, 'RETURNED'::text, 'FULFILLED'::text, 'COMPLETED'::text, 'CANCEL_PENDING'::text, 'CANCELLED'::text, 'REJECTED'::text, 'EXPIRED'::text])",
            name="ill_requests_workflow_state_check",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "provider_id"],
            ["providers.tenant_id", "providers.id"],
            name="ill_requests_tenant_id_provider_id_fkey",
        ),
        ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name="ill_requests_tenant_id_fkey"
        ),
        PrimaryKeyConstraint("id", name="ill_requests_pkey"),
        UniqueConstraint("tenant_id", "id", name="ill_requests_tenant_id_id_key"),
        UniqueConstraint(
            "tenant_id",
            "provider_id",
            "direction",
            "external_request_id",
            name="ill_requests_tenant_id_provider_id_direction_external_reque_key",
        ),
        Index(
            "ill_requests_attention_idx",
            "tenant_id",
            "processing_state",
            "updated_at",
            postgresql_where="(processing_state = ANY (ARRAY['NEEDS_REVIEW'::text, 'CONFLICT'::text, 'RETRYING'::text]))",
        ),
        Index(
            "ill_requests_dashboard_idx",
            "tenant_id",
            "direction",
            "workflow_state",
            "updated_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    provider_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    external_request_id: Mapped[str] = mapped_column(Text, nullable=False)
    direction: Mapped[str] = mapped_column(Text, nullable=False)
    request_type: Mapped[str] = mapped_column(Text, nullable=False)
    processing_state: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'PENDING'::text")
    )
    requesting_library: Mapped[dict] = mapped_column(JSONB, nullable=False)
    bibliographic: Mapped[dict] = mapped_column(JSONB, nullable=False)
    extensions: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    mapping_version: Mapped[str] = mapped_column(Text, nullable=False)
    schema_version: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("1")
    )
    version: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("1")
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(True), nullable=False, server_default=text("now()")
    )
    provider_record_id: Mapped[Optional[str]] = mapped_column(Text)
    workflow_state: Mapped[Optional[str]] = mapped_column(Text)
    active_lending_library: Mapped[Optional[dict]] = mapped_column(JSONB)
    provider_status_raw: Mapped[Optional[str]] = mapped_column(Text)
    provider_status_code: Mapped[Optional[str]] = mapped_column(Text)
    provider_revision: Mapped[Optional[str]] = mapped_column(Text)
    observed_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))
    source_updated_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime(True)
    )
    closed_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))

    providers: Mapped["Providers"] = relationship(
        "Providers",
        primaryjoin="""and_(
            Providers.id == foreign(IllRequests.provider_id),
            Providers.tenant_id == IllRequests.tenant_id,
        )""",
        foreign_keys="[IllRequests.provider_id]",
        back_populates="ill_requests",
    )
    tenant: Mapped["Tenants"] = relationship("Tenants", back_populates="ill_requests")
    effect_queue: Mapped[list["EffectQueue"]] = relationship(
        "EffectQueue",
        primaryjoin="""and_(
            IllRequests.id == foreign(EffectQueue.ill_request_id),
            IllRequests.tenant_id == EffectQueue.tenant_id,
        )""",
        foreign_keys="[EffectQueue.ill_request_id]",
        back_populates="ill_requests",
    )
    request_parties: Mapped[list["RequestParties"]] = relationship(
        "RequestParties", back_populates="ill_requests"
    )
    state_audit_logs: Mapped[list["StateAuditLogs"]] = relationship(
        "StateAuditLogs",
        primaryjoin="""and_(
            IllRequests.id == foreign(StateAuditLogs.ill_request_id),
            IllRequests.tenant_id == StateAuditLogs.tenant_id,
        )""",
        foreign_keys="[StateAuditLogs.ill_request_id]",
        back_populates="ill_requests",
    )
    sync_operations: Mapped[list["SyncOperations"]] = relationship(
        "SyncOperations",
        primaryjoin="""and_(
            IllRequests.id == foreign(SyncOperations.ill_request_id),
            IllRequests.tenant_id == SyncOperations.tenant_id,
        )""",
        foreign_keys="[SyncOperations.ill_request_id]",
        back_populates="ill_requests",
    )


