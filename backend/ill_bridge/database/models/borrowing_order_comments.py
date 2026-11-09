from __future__ import annotations

import datetime
import uuid

from sqlalchemy import (
    and_,
    DateTime,
    ForeignKeyConstraint,
    Index,
    PrimaryKeyConstraint,
    Text,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, foreign, mapped_column, relationship

from ill_bridge.database.base import Base


class BorrowingOrderComments(Base):
    """Staff notes on a borrowing order (N1 *personalkommentarer*)."""

    __tablename__ = "borrowing_order_comments"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "borrowing_order_id"],
            ["borrowing_orders.tenant_id", "borrowing_orders.id"],
            name="borrowing_order_comments_tenant_id_borrowing_order_id_fkey",
        ),
        ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="borrowing_order_comments_tenant_id_fkey",
        ),
        PrimaryKeyConstraint("id", name="borrowing_order_comments_pkey"),
        Index(
            "borrowing_order_comments_order_idx",
            "tenant_id",
            "borrowing_order_id",
            "created_at",
            "id",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    borrowing_order_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    author: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(True), nullable=False, server_default=text("now()")
    )

    borrowing_orders: Mapped["BorrowingOrders"] = relationship(
        "BorrowingOrders",
        primaryjoin="""and_(
            BorrowingOrders.id == foreign(BorrowingOrderComments.borrowing_order_id),
            BorrowingOrders.tenant_id == BorrowingOrderComments.tenant_id,
        )""",
        foreign_keys="[BorrowingOrderComments.borrowing_order_id]",
        back_populates="borrowing_order_comments",
    )
    tenant: Mapped["Tenants"] = relationship(
        "Tenants", back_populates="borrowing_order_comments"
    )
