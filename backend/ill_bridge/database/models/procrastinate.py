from typing import Optional
import datetime
import enum
import uuid

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKeyConstraint,
    Identity,
    Index,
    Integer,
    PrimaryKeyConstraint,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from ill_bridge.database.base import Base




class ProcrastinateJobEventType(str, enum.Enum):
    DEFERRED = "deferred"
    STARTED = "started"
    DEFERRED_FOR_RETRY = "deferred_for_retry"
    FAILED = "failed"
    SUCCEEDED = "succeeded"
    CANCELLED = "cancelled"
    ABORT_REQUESTED = "abort_requested"
    ABORTED = "aborted"
    SCHEDULED = "scheduled"
    RETRIED = "retried"


class ProcrastinateJobStatus(str, enum.Enum):
    TODO = "todo"
    DOING = "doing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    ABORTING = "aborting"
    ABORTED = "aborted"


class ProcrastinateWorkers(Base):
    __tablename__ = "procrastinate_workers"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="procrastinate_workers_pkey"),
        Index("idx_procrastinate_workers_last_heartbeat", "last_heartbeat"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(
            always=True,
            start=1,
            increment=1,
            minvalue=1,
            maxvalue=9223372036854775807,
            cycle=False,
            cache=1,
        ),
        primary_key=True,
        autoincrement=True,
    )
    last_heartbeat: Mapped[datetime.datetime] = mapped_column(
        DateTime(True), nullable=False, server_default=text("now()")
    )

    procrastinate_jobs: Mapped[list["ProcrastinateJobs"]] = relationship(
        "ProcrastinateJobs", back_populates="worker"
    )


class ProcrastinateJobs(Base):
    __tablename__ = "procrastinate_jobs"
    __table_args__ = (
        CheckConstraint(
            "NOT (status = 'todo'::procrastinate_job_status AND abort_requested = true)",
            name="check_not_todo_abort_requested",
        ),
        ForeignKeyConstraint(
            ["worker_id"],
            ["procrastinate_workers.id"],
            ondelete="SET NULL",
            name="procrastinate_jobs_worker_id_fkey",
        ),
        PrimaryKeyConstraint("id", name="procrastinate_jobs_pkey"),
        Index(
            "idx_procrastinate_jobs_worker_not_null",
            "worker_id",
            postgresql_where="((worker_id IS NOT NULL) AND (status = 'doing'::procrastinate_job_status))",
        ),
        Index(
            "procrastinate_jobs_id_lock_idx_v1",
            "id",
            "lock",
            postgresql_where="(status = ANY (ARRAY['todo'::procrastinate_job_status, 'doing'::procrastinate_job_status]))",
        ),
        Index(
            "procrastinate_jobs_lock_idx_v1",
            "lock",
            postgresql_where="(status = 'doing'::procrastinate_job_status)",
            unique=True,
        ),
        Index(
            "procrastinate_jobs_priority_idx_v1",
            "priority",
            "id",
            postgresql_where="(status = 'todo'::procrastinate_job_status)",
        ),
        Index("procrastinate_jobs_queue_name_idx_v1", "queue_name"),
        Index(
            "procrastinate_jobs_queueing_lock_idx_v1",
            "queueing_lock",
            postgresql_where="(status = 'todo'::procrastinate_job_status)",
            unique=True,
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    queue_name: Mapped[str] = mapped_column(String(128), nullable=False)
    task_name: Mapped[str] = mapped_column(String(128), nullable=False)
    priority: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    args: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    status: Mapped[ProcrastinateJobStatus] = mapped_column(
        Enum(
            ProcrastinateJobStatus,
            values_callable=lambda cls: [member.value for member in cls],
            name="procrastinate_job_status",
        ),
        nullable=False,
        server_default=text("'todo'::procrastinate_job_status"),
    )
    attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    abort_requested: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    lock: Mapped[Optional[str]] = mapped_column(Text)
    queueing_lock: Mapped[Optional[str]] = mapped_column(Text)
    scheduled_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))
    worker_id: Mapped[Optional[int]] = mapped_column(BigInteger)

    worker: Mapped[Optional["ProcrastinateWorkers"]] = relationship(
        "ProcrastinateWorkers", back_populates="procrastinate_jobs"
    )
    procrastinate_events: Mapped[list["ProcrastinateEvents"]] = relationship(
        "ProcrastinateEvents", back_populates="job"
    )
    procrastinate_periodic_defers: Mapped[list["ProcrastinatePeriodicDefers"]] = (
        relationship("ProcrastinatePeriodicDefers", back_populates="job")
    )


class ProcrastinateEvents(Base):
    __tablename__ = "procrastinate_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["job_id"],
            ["procrastinate_jobs.id"],
            ondelete="CASCADE",
            name="procrastinate_events_job_id_fkey",
        ),
        PrimaryKeyConstraint("id", name="procrastinate_events_pkey"),
        Index("procrastinate_events_job_id_fkey_v1", "job_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    type: Mapped[Optional[ProcrastinateJobEventType]] = mapped_column(
        Enum(
            ProcrastinateJobEventType,
            values_callable=lambda cls: [member.value for member in cls],
            name="procrastinate_job_event_type",
        )
    )
    at: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime(True), server_default=text("now()")
    )

    job: Mapped["ProcrastinateJobs"] = relationship(
        "ProcrastinateJobs", back_populates="procrastinate_events"
    )


class ProcrastinatePeriodicDefers(Base):
    __tablename__ = "procrastinate_periodic_defers"
    __table_args__ = (
        ForeignKeyConstraint(
            ["job_id"],
            ["procrastinate_jobs.id"],
            name="procrastinate_periodic_defers_job_id_fkey",
        ),
        PrimaryKeyConstraint("id", name="procrastinate_periodic_defers_pkey"),
        UniqueConstraint(
            "task_name",
            "periodic_id",
            "defer_timestamp",
            name="procrastinate_periodic_defers_unique",
        ),
        Index("procrastinate_periodic_defers_job_id_fkey_v1", "job_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    task_name: Mapped[str] = mapped_column(String(128), nullable=False)
    periodic_id: Mapped[str] = mapped_column(
        String(128), nullable=False, server_default=text("''::character varying")
    )
    defer_timestamp: Mapped[Optional[int]] = mapped_column(BigInteger)
    job_id: Mapped[Optional[int]] = mapped_column(BigInteger)

    job: Mapped[Optional["ProcrastinateJobs"]] = relationship(
        "ProcrastinateJobs", back_populates="procrastinate_periodic_defers"
    )
