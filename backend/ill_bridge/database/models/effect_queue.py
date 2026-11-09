from __future__ import annotations

import datetime
import uuid
from typing import Optional

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
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

from ill_bridge.database.base import Base


class EffectQueue(Base):
    __tablename__ = "effect_queue"
    __table_args__ = (
        CheckConstraint(
            "subject_type = ANY (ARRAY['ILL_REQUEST'::text, 'BORROWING_ORDER'::text])",
            name="effect_queue_subject_type_check",
        ),
        ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name="effect_queue_tenant_id_fkey"
        ),
        PrimaryKeyConstraint("id", name="effect_queue_pkey"),
        UniqueConstraint(
            "tenant_id", "effect_key", name="effect_queue_tenant_id_effect_key_key"
        ),
        Index(
            "effect_queue_claimable_idx",
            "tenant_id",
            "available_at",
            postgresql_where="(published_at IS NULL)",
        ),
        Index(
            "effect_queue_pending_idx",
            "tenant_id",
            "available_at",
            postgresql_where="(published_at IS NULL)",
        ),
        Index(
            "effect_queue_subject_idx",
            "tenant_id",
            "subject_type",
            "subject_id",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    effect_key: Mapped[str] = mapped_column(Text, nullable=False)
    available_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(True), nullable=False, server_default=text("now()")
    )
    attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    fence: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("0")
    )
    # Polymorphic subject: subject_type says which table subject_id points into.
    #   'ILL_REQUEST'     -> ill_requests.id
    #   'BORROWING_ORDER' -> borrowing_orders.id
    # A single column cannot carry a foreign key into two tables, so there is
    # no DB-level FK here: the dispatcher loads the subject by type and keeps a
    # row queued (NEEDS_REVIEW) if its subject is missing.
    subject_type: Mapped[str] = mapped_column(Text, nullable=False)
    subject_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    published_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))
    claimed_by: Mapped[Optional[str]] = mapped_column(Text)
    claimed_until: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))
    last_error: Mapped[Optional[str]] = mapped_column(Text)

    tenant: Mapped["Tenants"] = relationship("Tenants", back_populates="effect_queue")
