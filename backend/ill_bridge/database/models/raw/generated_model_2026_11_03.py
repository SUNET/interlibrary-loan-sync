from typing import Optional
import datetime
import enum
import uuid

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, Enum, ForeignKeyConstraint, Identity, Index, Integer, PrimaryKeyConstraint, String, Text, UniqueConstraint, Uuid, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

class Base(DeclarativeBase):
    pass


class ProcrastinateJobEventType(str, enum.Enum):
    DEFERRED = 'deferred'
    STARTED = 'started'
    DEFERRED_FOR_RETRY = 'deferred_for_retry'
    FAILED = 'failed'
    SUCCEEDED = 'succeeded'
    CANCELLED = 'cancelled'
    ABORT_REQUESTED = 'abort_requested'
    ABORTED = 'aborted'
    SCHEDULED = 'scheduled'
    RETRIED = 'retried'


class ProcrastinateJobStatus(str, enum.Enum):
    TODO = 'todo'
    DOING = 'doing'
    SUCCEEDED = 'succeeded'
    FAILED = 'failed'
    CANCELLED = 'cancelled'
    ABORTING = 'aborting'
    ABORTED = 'aborted'


class ProcrastinateWorkers(Base):
    __tablename__ = 'procrastinate_workers'
    __table_args__ = (
        PrimaryKeyConstraint('id', name='procrastinate_workers_pkey'),
        Index('idx_procrastinate_workers_last_heartbeat', 'last_heartbeat')
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True, start=1, increment=1, minvalue=1, maxvalue=9223372036854775807, cycle=False, cache=1), primary_key=True, autoincrement=True)
    last_heartbeat: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))

    procrastinate_jobs: Mapped[list['ProcrastinateJobs']] = relationship('ProcrastinateJobs', back_populates='worker')


class Pyway(Base):
    __tablename__ = 'pyway'
    __table_args__ = (
        PrimaryKeyConstraint('installed_rank', name='pyway_pkey'),
    )

    installed_rank: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    version: Mapped[str] = mapped_column(String(20), nullable=False)
    extension: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(125), nullable=False)
    checksum: Mapped[str] = mapped_column(String(25), nullable=False)
    apply_timestamp: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('now()'))


class Tenants(Base):
    __tablename__ = 'tenants'
    __table_args__ = (
        PrimaryKeyConstraint('id', name='tenants_pkey'),
        UniqueConstraint('folio_tenant_key', name='tenants_folio_tenant_key_key')
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    folio_tenant_key: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))

    borrowing_orders: Mapped[list['BorrowingOrders']] = relationship('BorrowingOrders', back_populates='tenant')
    providers: Mapped[list['Providers']] = relationship('Providers', back_populates='tenant')
    raw_provider_requests: Mapped[list['RawProviderRequests']] = relationship('RawProviderRequests', back_populates='tenant')
    borrowing_order_comments: Mapped[list['BorrowingOrderComments']] = relationship('BorrowingOrderComments', back_populates='tenant')
    ill_requests: Mapped[list['IllRequests']] = relationship('IllRequests', back_populates='tenant')
    effect_queue: Mapped[list['EffectQueue']] = relationship('EffectQueue', back_populates='tenant')
    state_audit_logs: Mapped[list['StateAuditLogs']] = relationship('StateAuditLogs', back_populates='tenant')
    sync_operations: Mapped[list['SyncOperations']] = relationship('SyncOperations', back_populates='tenant')


class BorrowingOrders(Base):
    __tablename__ = 'borrowing_orders'
    __table_args__ = (
        CheckConstraint("folio_user_status = ANY (ARRAY['FOUND'::text, 'NOT_FOUND'::text, 'CHECK_FAILED'::text])", name='borrowing_orders_folio_user_status_check'),
        CheckConstraint("processing_state = ANY (ARRAY['HANDLED'::text, 'UNHANDLED'::text])", name='borrowing_orders_processing_state_check'),
        CheckConstraint("request_type = ANY (ARRAY['LOAN'::text, 'COPY'::text])", name='borrowing_orders_request_type_check'),
        CheckConstraint("state = ANY (ARRAY['SUBMITTED'::text, 'LINKED'::text, 'CANCELLED'::text])", name='borrowing_orders_state_check'),
        ForeignKeyConstraint(['tenant_id'], ['tenants.id'], name='borrowing_orders_tenant_id_fkey'),
        PrimaryKeyConstraint('id', name='borrowing_orders_pkey'),
        UniqueConstraint('tenant_id', 'id', name='borrowing_orders_tenant_id_id_key'),
        UniqueConstraint('tenant_id', 'order_ref', name='borrowing_orders_tenant_id_order_ref_key'),
        Index('borrowing_orders_attention_idx', 'tenant_id', 'updated_at', postgresql_where="(processing_state = 'UNHANDLED'::text)"),
        Index('borrowing_orders_dashboard_idx', 'tenant_id', 'state', 'updated_at'),
        Index('borrowing_orders_lf_number_uq', 'tenant_id', 'libris_lf_number', postgresql_where='(libris_lf_number IS NOT NULL)', unique=True),
        Index('borrowing_orders_patron_idx', 'tenant_id', 'patron_barcode')
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    order_ref: Mapped[str] = mapped_column(Text, nullable=False)
    state: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'SUBMITTED'::text"))
    request_type: Mapped[str] = mapped_column(Text, nullable=False)
    bibliographic: Mapped[dict] = mapped_column(JSONB, nullable=False)
    patron_barcode: Mapped[str] = mapped_column(Text, nullable=False)
    patron_name: Mapped[str] = mapped_column(Text, nullable=False)
    folio_user_status: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    processing_state: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'UNHANDLED'::text"))
    folio_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    pickup_service_point_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    libris_lf_number: Mapped[Optional[str]] = mapped_column(Text)

    tenant: Mapped['Tenants'] = relationship('Tenants', back_populates='borrowing_orders')
    borrowing_order_comments: Mapped[list['BorrowingOrderComments']] = relationship('BorrowingOrderComments', back_populates='borrowing_orders')
    effect_queue: Mapped[list['EffectQueue']] = relationship('EffectQueue', back_populates='borrowing_orders')


class ProcrastinateJobs(Base):
    __tablename__ = 'procrastinate_jobs'
    __table_args__ = (
        CheckConstraint("NOT (status = 'todo'::procrastinate_job_status AND abort_requested = true)", name='check_not_todo_abort_requested'),
        ForeignKeyConstraint(['worker_id'], ['procrastinate_workers.id'], ondelete='SET NULL', name='procrastinate_jobs_worker_id_fkey'),
        PrimaryKeyConstraint('id', name='procrastinate_jobs_pkey'),
        Index('idx_procrastinate_jobs_worker_not_null', 'worker_id', postgresql_where="((worker_id IS NOT NULL) AND (status = 'doing'::procrastinate_job_status))"),
        Index('procrastinate_jobs_id_lock_idx_v1', 'id', 'lock', postgresql_where="(status = ANY (ARRAY['todo'::procrastinate_job_status, 'doing'::procrastinate_job_status]))"),
        Index('procrastinate_jobs_lock_idx_v1', 'lock', postgresql_where="(status = 'doing'::procrastinate_job_status)", unique=True),
        Index('procrastinate_jobs_priority_idx_v1', 'priority', 'id', postgresql_where="(status = 'todo'::procrastinate_job_status)"),
        Index('procrastinate_jobs_queue_name_idx_v1', 'queue_name'),
        Index('procrastinate_jobs_queueing_lock_idx_v1', 'queueing_lock', postgresql_where="(status = 'todo'::procrastinate_job_status)", unique=True)
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    queue_name: Mapped[str] = mapped_column(String(128), nullable=False)
    task_name: Mapped[str] = mapped_column(String(128), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('0'))
    args: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    status: Mapped[ProcrastinateJobStatus] = mapped_column(Enum(ProcrastinateJobStatus, values_callable=lambda cls: [member.value for member in cls], name='procrastinate_job_status'), nullable=False, server_default=text("'todo'::procrastinate_job_status"))
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('0'))
    abort_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('false'))
    lock: Mapped[Optional[str]] = mapped_column(Text)
    queueing_lock: Mapped[Optional[str]] = mapped_column(Text)
    scheduled_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))
    worker_id: Mapped[Optional[int]] = mapped_column(BigInteger)

    worker: Mapped[Optional['ProcrastinateWorkers']] = relationship('ProcrastinateWorkers', back_populates='procrastinate_jobs')
    procrastinate_events: Mapped[list['ProcrastinateEvents']] = relationship('ProcrastinateEvents', back_populates='job')
    procrastinate_periodic_defers: Mapped[list['ProcrastinatePeriodicDefers']] = relationship('ProcrastinatePeriodicDefers', back_populates='job')


class Providers(Base):
    __tablename__ = 'providers'
    __table_args__ = (
        CheckConstraint('poll_interval_seconds >= 10', name='providers_poll_interval_seconds_check'),
        ForeignKeyConstraint(['tenant_id'], ['tenants.id'], name='providers_tenant_id_fkey'),
        PrimaryKeyConstraint('id', name='providers_pkey'),
        UniqueConstraint('tenant_id', 'adapter_key', 'account_key', name='providers_tenant_id_adapter_key_account_key_key'),
        UniqueConstraint('tenant_id', 'id', name='providers_tenant_id_id_key')
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    adapter_key: Mapped[str] = mapped_column(Text, nullable=False)
    account_key: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    local_library_scheme: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'SIGEL'::text"))
    local_library_code: Mapped[str] = mapped_column(Text, nullable=False)
    base_url: Mapped[str] = mapped_column(Text, nullable=False)
    secret_ref: Mapped[str] = mapped_column(Text, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('false'))
    writes_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('false'))
    mapping_version: Mapped[str] = mapped_column(Text, nullable=False)
    config_version: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text('1'))
    poll_interval_seconds: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('60'))
    capabilities: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))

    tenant: Mapped['Tenants'] = relationship('Tenants', back_populates='providers')
    ill_requests: Mapped[list['IllRequests']] = relationship('IllRequests', back_populates='providers')


class RawProviderRequests(Base):
    __tablename__ = 'raw_provider_requests'
    __table_args__ = (
        ForeignKeyConstraint(['tenant_id'], ['tenants.id'], name='raw_provider_requests_tenant_id_fkey'),
        PrimaryKeyConstraint('id', name='raw_provider_requests_pkey'),
        UniqueConstraint('tenant_id', 'source_key', 'event_key', name='raw_provider_requests_tenant_id_source_key_event_key_key'),
        Index('raw_provider_requests_unprocessed_idx', 'tenant_id', 'received_at', postgresql_where='(processed_at IS NULL)')
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    source_key: Mapped[str] = mapped_column(Text, nullable=False)
    event_key: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    payload_hash: Mapped[str] = mapped_column(Text, nullable=False)
    received_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('1'))
    provider_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    processed_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))
    result: Mapped[Optional[str]] = mapped_column(Text)

    tenant: Mapped['Tenants'] = relationship('Tenants', back_populates='raw_provider_requests')


class BorrowingOrderComments(Base):
    __tablename__ = 'borrowing_order_comments'
    __table_args__ = (
        ForeignKeyConstraint(['tenant_id', 'borrowing_order_id'], ['borrowing_orders.tenant_id', 'borrowing_orders.id'], name='borrowing_order_comments_tenant_id_borrowing_order_id_fkey'),
        ForeignKeyConstraint(['tenant_id'], ['tenants.id'], name='borrowing_order_comments_tenant_id_fkey'),
        PrimaryKeyConstraint('id', name='borrowing_order_comments_pkey'),
        Index('borrowing_order_comments_order_idx', 'tenant_id', 'borrowing_order_id', 'created_at', 'id')
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    borrowing_order_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    author: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))

    borrowing_orders: Mapped['BorrowingOrders'] = relationship('BorrowingOrders', back_populates='borrowing_order_comments')
    tenant: Mapped['Tenants'] = relationship('Tenants', back_populates='borrowing_order_comments')


class IllRequests(Base):
    __tablename__ = 'ill_requests'
    __table_args__ = (
        CheckConstraint("direction = ANY (ARRAY['BORROWING'::text, 'LENDING'::text])", name='ill_requests_direction_check'),
        CheckConstraint("processing_state = ANY (ARRAY['PENDING'::text, 'IN_SYNC'::text, 'RETRYING'::text, 'NEEDS_REVIEW'::text, 'CONFLICT'::text, 'PAUSED'::text])", name='ill_requests_processing_state_check'),
        CheckConstraint("request_type = ANY (ARRAY['LOAN'::text, 'COPY'::text])", name='ill_requests_request_type_check'),
        CheckConstraint("workflow_state = ANY (ARRAY['REQUESTED'::text, 'ACKNOWLEDGED'::text, 'RESERVED'::text, 'DELIVERED'::text, 'RENEWAL_REQUESTED'::text, 'RENEWAL_ACKNOWLEDGED'::text, 'ACCEPTED'::text, 'ON_HOLD'::text, 'IN_TRANSIT'::text, 'ARRIVED'::text, 'RECEIVED'::text, 'READY_FOR_PICKUP'::text, 'ON_LOAN'::text, 'RETURNED_FROM_PATRON'::text, 'RETURN_PENDING'::text, 'RETURN_IN_TRANSIT'::text, 'RETURNED'::text, 'FULFILLED'::text, 'COMPLETED'::text, 'CANCEL_PENDING'::text, 'CANCELLED'::text, 'REJECTED'::text, 'EXPIRED'::text])", name='ill_requests_workflow_state_check'),
        ForeignKeyConstraint(['tenant_id', 'provider_id'], ['providers.tenant_id', 'providers.id'], name='ill_requests_tenant_id_provider_id_fkey'),
        ForeignKeyConstraint(['tenant_id'], ['tenants.id'], name='ill_requests_tenant_id_fkey'),
        PrimaryKeyConstraint('id', name='ill_requests_pkey'),
        UniqueConstraint('tenant_id', 'id', name='ill_requests_tenant_id_id_key'),
        UniqueConstraint('tenant_id', 'provider_id', 'direction', 'external_request_id', name='ill_requests_tenant_id_provider_id_direction_external_reque_key'),
        Index('ill_requests_attention_idx', 'tenant_id', 'processing_state', 'updated_at', postgresql_where="(processing_state = ANY (ARRAY['NEEDS_REVIEW'::text, 'CONFLICT'::text, 'RETRYING'::text]))"),
        Index('ill_requests_dashboard_idx', 'tenant_id', 'direction', 'workflow_state', 'updated_at')
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    provider_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    external_request_id: Mapped[str] = mapped_column(Text, nullable=False)
    direction: Mapped[str] = mapped_column(Text, nullable=False)
    request_type: Mapped[str] = mapped_column(Text, nullable=False)
    processing_state: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'PENDING'::text"))
    requesting_library: Mapped[dict] = mapped_column(JSONB, nullable=False)
    bibliographic: Mapped[dict] = mapped_column(JSONB, nullable=False)
    extensions: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    mapping_version: Mapped[str] = mapped_column(Text, nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('1'))
    version: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text('1'))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    provider_record_id: Mapped[Optional[str]] = mapped_column(Text)
    workflow_state: Mapped[Optional[str]] = mapped_column(Text)
    active_lending_library: Mapped[Optional[dict]] = mapped_column(JSONB)
    provider_status_raw: Mapped[Optional[str]] = mapped_column(Text)
    provider_status_code: Mapped[Optional[str]] = mapped_column(Text)
    provider_revision: Mapped[Optional[str]] = mapped_column(Text)
    observed_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))
    source_updated_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))
    closed_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))

    providers: Mapped['Providers'] = relationship('Providers', back_populates='ill_requests')
    tenant: Mapped['Tenants'] = relationship('Tenants', back_populates='ill_requests')
    effect_queue: Mapped[list['EffectQueue']] = relationship('EffectQueue', back_populates='ill_requests')
    request_parties: Mapped[list['RequestParties']] = relationship('RequestParties', back_populates='ill_requests')
    state_audit_logs: Mapped[list['StateAuditLogs']] = relationship('StateAuditLogs', back_populates='ill_requests')
    sync_operations: Mapped[list['SyncOperations']] = relationship('SyncOperations', back_populates='ill_requests')


class ProcrastinateEvents(Base):
    __tablename__ = 'procrastinate_events'
    __table_args__ = (
        ForeignKeyConstraint(['job_id'], ['procrastinate_jobs.id'], ondelete='CASCADE', name='procrastinate_events_job_id_fkey'),
        PrimaryKeyConstraint('id', name='procrastinate_events_pkey'),
        Index('procrastinate_events_job_id_fkey_v1', 'job_id')
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    type: Mapped[Optional[ProcrastinateJobEventType]] = mapped_column(Enum(ProcrastinateJobEventType, values_callable=lambda cls: [member.value for member in cls], name='procrastinate_job_event_type'))
    at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True), server_default=text('now()'))

    job: Mapped['ProcrastinateJobs'] = relationship('ProcrastinateJobs', back_populates='procrastinate_events')


class ProcrastinatePeriodicDefers(Base):
    __tablename__ = 'procrastinate_periodic_defers'
    __table_args__ = (
        ForeignKeyConstraint(['job_id'], ['procrastinate_jobs.id'], name='procrastinate_periodic_defers_job_id_fkey'),
        PrimaryKeyConstraint('id', name='procrastinate_periodic_defers_pkey'),
        UniqueConstraint('task_name', 'periodic_id', 'defer_timestamp', name='procrastinate_periodic_defers_unique'),
        Index('procrastinate_periodic_defers_job_id_fkey_v1', 'job_id')
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    task_name: Mapped[str] = mapped_column(String(128), nullable=False)
    periodic_id: Mapped[str] = mapped_column(String(128), nullable=False, server_default=text("''::character varying"))
    defer_timestamp: Mapped[Optional[int]] = mapped_column(BigInteger)
    job_id: Mapped[Optional[int]] = mapped_column(BigInteger)

    job: Mapped[Optional['ProcrastinateJobs']] = relationship('ProcrastinateJobs', back_populates='procrastinate_periodic_defers')


class EffectQueue(Base):
    __tablename__ = 'effect_queue'
    __table_args__ = (
        CheckConstraint('num_nonnulls(ill_request_id, borrowing_order_id) = 1', name='effect_queue_one_subject_check'),
        ForeignKeyConstraint(['tenant_id', 'borrowing_order_id'], ['borrowing_orders.tenant_id', 'borrowing_orders.id'], name='effect_queue_tenant_id_borrowing_order_id_fkey'),
        ForeignKeyConstraint(['tenant_id', 'ill_request_id'], ['ill_requests.tenant_id', 'ill_requests.id'], name='effect_queue_tenant_id_ill_request_id_fkey'),
        ForeignKeyConstraint(['tenant_id'], ['tenants.id'], name='effect_queue_tenant_id_fkey'),
        PrimaryKeyConstraint('id', name='effect_queue_pkey'),
        UniqueConstraint('tenant_id', 'effect_key', name='effect_queue_tenant_id_effect_key_key'),
        Index('effect_queue_claimable_idx', 'tenant_id', 'available_at', postgresql_where='(published_at IS NULL)'),
        Index('effect_queue_pending_idx', 'tenant_id', 'available_at', postgresql_where='(published_at IS NULL)')
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    effect_key: Mapped[str] = mapped_column(Text, nullable=False)
    available_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('0'))
    fence: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text('0'))
    ill_request_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    published_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))
    claimed_by: Mapped[Optional[str]] = mapped_column(Text)
    claimed_until: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))
    last_error: Mapped[Optional[str]] = mapped_column(Text)
    borrowing_order_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)

    borrowing_orders: Mapped[Optional['BorrowingOrders']] = relationship('BorrowingOrders', back_populates='effect_queue')
    ill_requests: Mapped[Optional['IllRequests']] = relationship('IllRequests', back_populates='effect_queue')
    tenant: Mapped['Tenants'] = relationship('Tenants', back_populates='effect_queue')


class RequestParties(Base):
    __tablename__ = 'request_parties'
    __table_args__ = (
        CheckConstraint("role = ANY (ARRAY['REQUESTING'::text, 'LENDER_CANDIDATE'::text, 'ACTIVE_LENDER'::text])", name='request_parties_role_check'),
        ForeignKeyConstraint(['tenant_id', 'ill_request_id'], ['ill_requests.tenant_id', 'ill_requests.id'], ondelete='CASCADE', name='request_parties_tenant_id_ill_request_id_fkey'),
        PrimaryKeyConstraint('id', name='request_parties_pkey'),
        UniqueConstraint('tenant_id', 'ill_request_id', 'ordinal', name='request_parties_tenant_id_ill_request_id_ordinal_key'),
        Index('request_parties_request_idx', 'tenant_id', 'ill_request_id', 'ordinal')
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    ill_request_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'LENDER_CANDIDATE'::text"))
    scheme: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'SIGEL'::text"))
    code: Mapped[str] = mapped_column(Text, nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('false'))
    response_code: Mapped[Optional[str]] = mapped_column(Text)
    response_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))
    location: Mapped[Optional[str]] = mapped_column(Text)

    ill_requests: Mapped['IllRequests'] = relationship('IllRequests', back_populates='request_parties')


class StateAuditLogs(Base):
    __tablename__ = 'state_audit_logs'
    __table_args__ = (
        CheckConstraint("actor_type = ANY (ARRAY['STAFF'::text, 'PROVIDER'::text, 'FOLIO'::text, 'SYSTEM'::text])", name='state_audit_logs_actor_type_check'),
        ForeignKeyConstraint(['tenant_id', 'ill_request_id'], ['ill_requests.tenant_id', 'ill_requests.id'], name='state_audit_logs_tenant_id_ill_request_id_fkey'),
        ForeignKeyConstraint(['tenant_id'], ['tenants.id'], name='state_audit_logs_tenant_id_fkey'),
        PrimaryKeyConstraint('id', name='state_audit_logs_pkey'),
        Index('state_audit_logs_timeline_idx', 'tenant_id', 'ill_request_id', 'recorded_at', 'id')
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    actor_type: Mapped[str] = mapped_column(Text, nullable=False)
    correlation_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    recorded_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    details_redacted: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
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

    ill_requests: Mapped[Optional['IllRequests']] = relationship('IllRequests', back_populates='state_audit_logs')
    tenant: Mapped['Tenants'] = relationship('Tenants', back_populates='state_audit_logs')


class SyncOperations(Base):
    __tablename__ = 'sync_operations'
    __table_args__ = (
        CheckConstraint('attempts >= 0', name='sync_operations_attempts_check'),
        CheckConstraint("status = ANY (ARRAY['PENDING'::text, 'IN_FLIGHT'::text, 'CONFIRMED'::text, 'REFUSED'::text, 'UNKNOWN'::text, 'ABANDONED'::text])", name='sync_operations_status_check'),
        ForeignKeyConstraint(['tenant_id', 'ill_request_id'], ['ill_requests.tenant_id', 'ill_requests.id'], name='sync_operations_tenant_id_ill_request_id_fkey'),
        ForeignKeyConstraint(['tenant_id'], ['tenants.id'], name='sync_operations_tenant_id_fkey'),
        PrimaryKeyConstraint('id', name='sync_operations_pkey'),
        UniqueConstraint('tenant_id', 'ill_request_id', 'target', 'effect_key', name='sync_operations_tenant_id_ill_request_id_target_effect_key_key'),
        Index('sync_operations_due_idx', 'tenant_id', 'next_attempt_at', postgresql_where="(status = ANY (ARRAY['PENDING'::text, 'UNKNOWN'::text]))")
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    ill_request_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    target: Mapped[str] = mapped_column(Text, nullable=False)
    effect_key: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'PENDING'::text"))
    operation_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('0'))
    fence: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text('0'))
    result_redacted: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    external_id: Mapped[Optional[str]] = mapped_column(Text)
    expected_version: Mapped[Optional[int]] = mapped_column(BigInteger)
    lease_owner: Mapped[Optional[str]] = mapped_column(Text)
    lease_expires_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))
    first_attempted_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))
    last_attempted_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))
    next_attempt_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))

    ill_requests: Mapped['IllRequests'] = relationship('IllRequests', back_populates='sync_operations')
    tenant: Mapped['Tenants'] = relationship('Tenants', back_populates='sync_operations')
