from __future__ import annotations

import datetime
import uuid
from typing import Optional

from sqlalchemy import (
    and_,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    PrimaryKeyConstraint,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, foreign, mapped_column, relationship

from ill_bridge.database.base import Base


class BorrowingOrders(Base):
    """Local borrowing order (A5), created before any Libris request exists."""

    __tablename__ = "borrowing_orders"
    __table_args__ = (
        CheckConstraint(
            "folio_user_status = ANY (ARRAY['FOUND'::text, 'NOT_FOUND'::text, 'CHECK_FAILED'::text])",
            name="borrowing_orders_folio_user_status_check",
        ),
        CheckConstraint(
            "processing_state = ANY (ARRAY['HANDLED'::text, 'UNHANDLED'::text])",
            name="borrowing_orders_processing_state_check",
        ),
        CheckConstraint(
            "request_type = ANY (ARRAY['LOAN'::text, 'COPY'::text])",
            name="borrowing_orders_request_type_check",
        ),
        CheckConstraint(
            "state = ANY (ARRAY['SUBMITTED'::text, 'LINKED'::text, 'CANCELLED'::text])",
            name="borrowing_orders_state_check",
        ),
        ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name="borrowing_orders_tenant_id_fkey"
        ),
        PrimaryKeyConstraint("id", name="borrowing_orders_pkey"),
        UniqueConstraint("tenant_id", "id", name="borrowing_orders_tenant_id_id_key"),
        Index(
            "borrowing_orders_attention_idx",
            "tenant_id",
            "updated_at",
            postgresql_where="(processing_state = 'UNHANDLED'::text)",
        ),
        Index("borrowing_orders_dashboard_idx", "tenant_id", "state", "updated_at"),
        Index(
            "borrowing_orders_lf_number_uq",
            "tenant_id",
            "libris_lf_number",
            postgresql_where="(libris_lf_number IS NOT NULL)",
            unique=True,
        ),
        Index("borrowing_orders_patron_idx", "tenant_id", "patron_barcode"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    state: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'SUBMITTED'::text")
    )
    request_type: Mapped[str] = mapped_column(Text, nullable=False)
    bibliographic: Mapped[dict] = mapped_column(JSONB, nullable=False)
    patron_barcode: Mapped[str] = mapped_column(Text, nullable=False)
    patron_name: Mapped[str] = mapped_column(Text, nullable=False)
    folio_user_status: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(True), nullable=False, server_default=text("now()")
    )
    # Set by the effect dispatcher, not by intake: an order starts UNHANDLED
    # because its infodisk mail has not been sent yet.
    processing_state: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'UNHANDLED'::text")
    )
    folio_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    # The Libris reference a human recorded. Written either at creation, when
    # the Libris request already exists, or by a later update after A6.
    # Setting it does not move the order to LINKED: it records a claim, while
    # the link itself is ill_requests.borrowing_order_id.
    libris_lf_number: Mapped[Optional[str]] = mapped_column(Text)

    tenant: Mapped["Tenants"] = relationship(
        "Tenants", back_populates="borrowing_orders"
    )
    # Children join on (id, tenant_id) but only the order id is the foreign
    # side: tenant_id is also this table's own FK to tenants, and marking it
    # foreign here would make the two relationships fight over the column.
    borrowing_order_comments: Mapped[list["BorrowingOrderComments"]] = relationship(
        "BorrowingOrderComments",
        primaryjoin="""and_(
            BorrowingOrders.id == foreign(BorrowingOrderComments.borrowing_order_id),
            BorrowingOrders.tenant_id == BorrowingOrderComments.tenant_id,
        )""",
        foreign_keys="[BorrowingOrderComments.borrowing_order_id]",
        back_populates="borrowing_orders",
    )
    # No effect_queue relationship: effect_queue now references its subject
    # polymorphically (subject_type + subject_id) with no foreign key, so there
    # is no join for the ORM to follow. The dispatcher loads subjects by id.
