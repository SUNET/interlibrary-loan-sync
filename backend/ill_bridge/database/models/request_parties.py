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


class RequestParties(Base):
    __tablename__ = "request_parties"
    __table_args__ = (
        CheckConstraint(
            "role = ANY (ARRAY['REQUESTING'::text, 'LENDER_CANDIDATE'::text, 'ACTIVE_LENDER'::text])",
            name="request_parties_role_check",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "ill_request_id"],
            ["ill_requests.tenant_id", "ill_requests.id"],
            ondelete="CASCADE",
            name="request_parties_tenant_id_ill_request_id_fkey",
        ),
        PrimaryKeyConstraint("id", name="request_parties_pkey"),
        UniqueConstraint(
            "tenant_id",
            "ill_request_id",
            "ordinal",
            name="request_parties_tenant_id_ill_request_id_ordinal_key",
        ),
        Index("request_parties_request_idx", "tenant_id", "ill_request_id", "ordinal"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    ill_request_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    role: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'LENDER_CANDIDATE'::text")
    )
    scheme: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'SIGEL'::text")
    )
    code: Mapped[str] = mapped_column(Text, nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    response_code: Mapped[Optional[str]] = mapped_column(Text)
    response_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))
    location: Mapped[Optional[str]] = mapped_column(Text)

    ill_requests: Mapped["IllRequests"] = relationship(
        "IllRequests", back_populates="request_parties"
    )


