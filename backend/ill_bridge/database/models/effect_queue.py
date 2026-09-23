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


class EffectQueue(Base):
    __tablename__ = "effect_queue"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "ill_request_id"],
            ["ill_requests.tenant_id", "ill_requests.id"],
            name="effect_queue_tenant_id_ill_request_id_fkey",
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
    ill_request_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    published_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))
    claimed_by: Mapped[Optional[str]] = mapped_column(Text)
    claimed_until: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))
    last_error: Mapped[Optional[str]] = mapped_column(Text)

    ill_requests: Mapped[Optional["IllRequests"]] = relationship(
        "IllRequests",
        primaryjoin="""and_(
            IllRequests.id == foreign(EffectQueue.ill_request_id),
            IllRequests.tenant_id == EffectQueue.tenant_id,
        )""",
        foreign_keys="[EffectQueue.ill_request_id]",
        back_populates="effect_queue",
    )
    tenant: Mapped["Tenants"] = relationship("Tenants", back_populates="effect_queue")


