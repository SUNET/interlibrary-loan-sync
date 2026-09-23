-- ============================================================================
-- ILL Bridge — PostgreSQL Schema
-- ============================================================================
--
-- Multi-tenant FOLIO ILL integration.
--
-- Main concepts:
--
--   tenants
--       Institution / tenant boundary.
--
--   providers
--       External provider configuration, e.g. Libris.
--
--   ill_requests
--       Current-state projection of an ILL request.
--
--   request_parties
--       Current lender/requester chain for an ILL request.
--
--   state_audit_logs
--       Append-only history of observations, commands and state transitions.
--
--   raw_provider_requests
--       Raw provider records retained for deduplication and replay.
--
--   effect_queue
--       Transactional queue of pending external side effects.
--
--   sync_operations
--       Durable step ledger for external operations and unknown outcomes.
--
-- ============================================================================

-- App role: used by the application connection (no BYPASSRLS, does not own tables)
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ill_app') THEN
    CREATE ROLE ill_app NOLOGIN;
    -- CREATE ROLE ill_app LOGIN PASSWORD 'change-me-in-prod';
  END IF;
END
$$;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ill_scheduler') THEN
    CREATE ROLE ill_scheduler NOLOGIN;
    -- CREATE ROLE ill_scheduler LOGIN PASSWORD 'change-me-in-prod';
  END IF;
END
$$;



-- Optional: grants needed for the app to use the schema
GRANT CONNECT ON DATABASE ill TO ill_app;
GRANT USAGE ON SCHEMA public TO ill_app;

-- ============================================================================
-- 2.1 Tenants
-- ============================================================================

-- One row per institution (BTH, UUB, MDU...).
-- The root of every FK chain.

CREATE TABLE tenants (
    id                UUID PRIMARY KEY,

    folio_tenant_key  TEXT NOT NULL UNIQUE,       -- FOLIO's own tenant id
    name              TEXT NOT NULL,

    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);


-- ============================================================================
-- 2.2 Providers
-- ============================================================================

CREATE TABLE providers (
    id                    UUID PRIMARY KEY,

    tenant_id             UUID NOT NULL REFERENCES tenants(id),

    adapter_key           TEXT NOT NULL,
    -- 'libris' | 'fake' | 'rapidill' → selects a fixed adapter class.
    -- Must NOT be an arbitrary Python import path from staff configuration.

    account_key           TEXT NOT NULL,
    -- Distinguishes multiple provider accounts within one tenant.

    display_name          TEXT NOT NULL,

    -- The sigel that goes into the Libris URL path.
    --
    -- The API key is organisation-scoped, so this value — not the credential —
    -- selects the data. Tenant → sigel mapping is therefore part of isolation.

    local_library_scheme  TEXT NOT NULL DEFAULT 'SIGEL',
    local_library_code    TEXT NOT NULL,

    base_url              TEXT NOT NULL,

    secret_ref            TEXT NOT NULL,
    -- POINTER only, e.g. 'vault://...' or 'env://...'.
    -- Never store the actual API key here.

    enabled               BOOLEAN NOT NULL DEFAULT false,

    writes_enabled        BOOLEAN NOT NULL DEFAULT false,
    -- Libris has no undo. Keep provider writes explicitly disabled by default.

    mapping_version       TEXT NOT NULL,

    config_version        BIGINT NOT NULL DEFAULT 1,

    poll_interval_seconds INTEGER NOT NULL DEFAULT 60
                          CHECK (poll_interval_seconds >= 10),

    capabilities          JSONB NOT NULL DEFAULT '{}',

    config                JSONB NOT NULL DEFAULT '{}',

    created_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at             TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- Required so children can use a composite foreign key.
    UNIQUE (tenant_id, id),

    UNIQUE (tenant_id, adapter_key, account_key)
);


-- ============================================================================
-- 2.3 ill_requests
-- ============================================================================

CREATE TABLE ill_requests (
    id                     UUID PRIMARY KEY,

    tenant_id              UUID NOT NULL REFERENCES tenants(id),

    provider_id            UUID NOT NULL,

    -- Staff-facing id (Libris lf_number).
    -- Opaque transaction id, NOT a bibliographic record id.
    external_request_id    TEXT NOT NULL,

    -- Numeric Libris request_id, stored as TEXT to avoid provider typing issues.
    provider_record_id     TEXT,

    direction              TEXT NOT NULL
                           CHECK (
                               direction IN ('BORROWING', 'LENDING')
                           ),

    request_type           TEXT NOT NULL
                           CHECK (
                               request_type IN ('LOAN', 'COPY')
                           ),

    -- Business state.
    -- NULL until a provider status maps confidently.
    workflow_state         TEXT
                           CHECK (
                               workflow_state IN (
                                   'REQUESTED',
                                   'ACCEPTED',
                                   'ON_HOLD',
                                   'IN_TRANSIT',
                                   'RECEIVED',
                                   'READY_FOR_PICKUP',
                                   'ON_LOAN',
                                   'RETURN_PENDING',
                                   'RETURN_IN_TRANSIT',
                                   'RETURNED',
                                   'FULFILLED',
                                   'COMPLETED',
                                   'CANCEL_PENDING',
                                   'CANCELLED',
                                   'REJECTED',
                                   'EXPIRED'
                               )
                           ),

    -- Integration health.
    --
    -- Deliberately separate from workflow_state:
    -- a network outage must never turn an accepted loan into a rejected loan.
    processing_state       TEXT NOT NULL DEFAULT 'PENDING'
                           CHECK (
                               processing_state IN (
                                   'PENDING',
                                   'IN_SYNC',
                                   'RETRYING',
                                   'NEEDS_REVIEW',
                                   'CONFLICT',
                                   'PAUSED'
                               )
                           ),

    requesting_library     JSONB NOT NULL,
    -- {scheme, value, display_name?}

    active_lending_library JSONB,

    bibliographic          JSONB NOT NULL,

    -- Raw provider vocabulary, retained beside the mapped state.
    provider_status_raw    TEXT,
    -- Example: 'Remitterad'

    provider_status_code   TEXT,
    -- Example: '4'

    -- Opaque provider revision token.
    --
    -- TEXT intentionally:
    -- Libris compares this value byte-for-byte.
    -- Do not convert it to INTEGER or TIMESTAMPTZ.
    provider_revision      TEXT,

    -- Unmodelled provider fields.
    -- Retained, but not interpreted by the core model.
    extensions             JSONB NOT NULL DEFAULT '{}',

    observed_at            TIMESTAMPTZ,
    -- When we last observed the record.

    source_updated_at      TIMESTAMPTZ,
    -- When the provider says the record changed.

    mapping_version        TEXT NOT NULL,

    schema_version         INTEGER NOT NULL DEFAULT 1,

    -- Optimistic lock.
    -- Every state-changing write uses WHERE version = :expected.
    version                BIGINT NOT NULL DEFAULT 1,

    created_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at             TIMESTAMPTZ NOT NULL DEFAULT now(),

    closed_at              TIMESTAMPTZ,

    -- Part 6+:
    -- patron_ref_ciphertext
    -- patron_ref_hmac
    -- folio_user_id
    -- pickup_service_point_id
    -- lender_due_at
    -- patron_due_at

    -- Required for composite child foreign keys.
    UNIQUE (tenant_id, id),

    -- THE deduplication / identity key.
    --
    -- Two providers/sigels can legitimately expose the same external id.
    -- Therefore the external id is scoped to provider + direction.
    UNIQUE (
        tenant_id,
        provider_id,
        direction,
        external_request_id
    ),

    -- A request can never point at a provider owned by another tenant.
    FOREIGN KEY (tenant_id, provider_id)
        REFERENCES providers(tenant_id, id)
);


-- ============================================================================
-- 2.4 request_parties
-- ============================================================================

CREATE TABLE request_parties (
    id                UUID PRIMARY KEY,

    tenant_id         UUID NOT NULL,

    ill_request_id    UUID NOT NULL,

    -- MERGED: default added because the current _sync_parties() function
    -- does not explicitly provide role.
    role              TEXT NOT NULL DEFAULT 'LENDER_CANDIDATE'
                      CHECK (
                          role IN (
                              'REQUESTING',
                              'LENDER_CANDIDATE',
                              'ACTIVE_LENDER'
                          )
                      ),

    scheme            TEXT NOT NULL DEFAULT 'SIGEL',

    code              TEXT NOT NULL,
    -- Examples: 'Um', 'Mo', 'Hal'

    ordinal           INTEGER NOT NULL,
    -- Position within provider recipients[].

    is_active         BOOLEAN NOT NULL DEFAULT false,

    response_code     TEXT,
    -- recipients[].response_id

    response_at       TIMESTAMPTZ,

    -- MERGED: used by _sync_parties().
    location          TEXT,

    UNIQUE (
        tenant_id,
        ill_request_id,
        ordinal
    ),

    FOREIGN KEY (tenant_id, ill_request_id)
        REFERENCES ill_requests(tenant_id, id)
        ON DELETE CASCADE
);


-- ============================================================================
-- 2.5 state_audit_logs
-- ============================================================================

CREATE TABLE state_audit_logs (
    id               UUID PRIMARY KEY,

    tenant_id        UUID NOT NULL REFERENCES tenants(id),

    ill_request_id   UUID,

    event_type       TEXT NOT NULL,
    -- 'OBSERVATION' | 'COMMAND' | 'CORRECTION'

    from_state       TEXT,

    to_state         TEXT,

    actor_type       TEXT NOT NULL
                     CHECK (
                         actor_type IN (
                             'STAFF',
                             'PROVIDER',
                             'FOLIO',
                             'SYSTEM'
                         )
                     ),

    actor_id         TEXT,

    reason           TEXT,

    -- Ties this row to the exact upstream event.
    -- Useful for echo suppression / correlation.
    source_event_key TEXT,

    correlation_id   UUID NOT NULL,

    causation_id     UUID,

    mapping_version  TEXT,

    -- Version BEFORE the state change.
    request_version  BIGINT,

    -- When the event happened upstream.
    occurred_at      TIMESTAMPTZ,

    recorded_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- Never store raw PII here.
    details_redacted JSONB NOT NULL DEFAULT '{}',

    FOREIGN KEY (tenant_id, ill_request_id)
        REFERENCES ill_requests(tenant_id, id)
);


-- ============================================================================
-- 2.6 raw_provider_requests
-- ============================================================================

CREATE TABLE raw_provider_requests (
    id              UUID PRIMARY KEY,

    tenant_id       UUID NOT NULL REFERENCES tenants(id),

    provider_id     UUID,

    source_key      TEXT NOT NULL,
    -- Example: 'libris:Hal:incoming'

    event_key       TEXT NOT NULL,
    -- Example: 'Lin1-260909-0010:1789034995'

    payload         JSONB NOT NULL,
    -- Raw provider record.

    payload_hash    TEXT NOT NULL,
    -- SHA-256; useful for change detection.

    received_at     TIMESTAMPTZ NOT NULL DEFAULT now(),

    processed_at    TIMESTAMPTZ,

    result          TEXT,
    -- 'APPLIED' | 'SKIPPED' | 'FAILED'

    schema_version  INTEGER NOT NULL DEFAULT 1,

    -- Re-polling the same unchanged provider record becomes a no-op.
    UNIQUE (
        tenant_id,
        source_key,
        event_key
    )
);


-- ============================================================================
-- 2.7 effect_queue
-- ============================================================================

CREATE TABLE effect_queue (
    id              UUID PRIMARY KEY,

    tenant_id       UUID NOT NULL REFERENCES tenants(id),

    ill_request_id  UUID,

    kind            TEXT NOT NULL,
    -- 'STATE_CHANGED' | 'NEEDS_REVIEW'

    payload         JSONB NOT NULL,

    effect_key      TEXT NOT NULL,
    -- Logical idempotency key.

    available_at    TIMESTAMPTZ NOT NULL DEFAULT now(),

    published_at    TIMESTAMPTZ,

    attempts        INTEGER NOT NULL DEFAULT 0,

    -- MERGED: lease ownership fields originally added later with ALTER TABLE.
    claimed_by      TEXT,

    claimed_until   TIMESTAMPTZ,

    fence           BIGINT NOT NULL DEFAULT 0,

    last_error      TEXT,

    UNIQUE (
        tenant_id,
        effect_key
    ),

    FOREIGN KEY (tenant_id, ill_request_id)
        REFERENCES ill_requests(tenant_id, id)
);


-- ============================================================================
-- 2.8 sync_operations
-- ============================================================================

-- Durable step ledger.
--
-- One row per (request, target, effect).
--
-- This records what we attempted externally, independent of whether we
-- learned the result.
--
-- This makes an unknown outcome recoverable:
--
--   timeout
--       ↓
--   status = UNKNOWN
--       ↓
--   retry
--       ↓
--   use predetermined operation_id / external id
--       ↓
--   ask target whether operation already happened
--
-- Instead of blindly creating a second external object.

CREATE TABLE sync_operations (
    id                  UUID PRIMARY KEY,

    tenant_id           UUID NOT NULL REFERENCES tenants(id),

    ill_request_id      UUID NOT NULL,

    target              TEXT NOT NULL,
    -- 'FOLIO' | 'LIBRIS' | 'EMAIL'

    effect_key          TEXT NOT NULL,

    status              TEXT NOT NULL DEFAULT 'PENDING'
                        CHECK (
                            status IN (
                                'PENDING',
                                'IN_FLIGHT',
                                'CONFIRMED',
                                'REFUSED',
                                'UNKNOWN',
                                'ABANDONED'
                            )
                        ),

    -- Chosen by US before the external call.
    -- Sent to the target as its idempotency key where supported.
    operation_id        UUID NOT NULL,

    -- Learned when the target confirms the operation.
    external_id         TEXT,

    attempts            INTEGER NOT NULL DEFAULT 0
                        CHECK (attempts >= 0),

    expected_version    BIGINT,

    lease_owner         TEXT,

    lease_expires_at    TIMESTAMPTZ,

    fence               BIGINT NOT NULL DEFAULT 0,

    first_attempted_at  TIMESTAMPTZ,

    last_attempted_at   TIMESTAMPTZ,

    next_attempt_at     TIMESTAMPTZ,

    result_redacted     JSONB NOT NULL DEFAULT '{}',

    UNIQUE (
        tenant_id,
        ill_request_id,
        target,
        effect_key
    ),

    FOREIGN KEY (tenant_id, ill_request_id)
        REFERENCES ill_requests(tenant_id, id)
);


-- ============================================================================
-- 2.9 Indexes
-- ============================================================================

-- Dashboard list:
-- GET /requests?direction=&workflow_state=

CREATE INDEX ill_requests_dashboard_idx
    ON ill_requests (
        tenant_id,
        direction,
        workflow_state,
        updated_at DESC
    );


-- Requests requiring human attention.
--
-- Partial index keeps this small when most requests are healthy.

CREATE INDEX ill_requests_attention_idx
    ON ill_requests (
        tenant_id,
        processing_state,
        updated_at DESC
    )
    WHERE processing_state IN (
        'NEEDS_REVIEW',
        'CONFLICT',
        'RETRYING'
    );


-- Request-party lookup.

CREATE INDEX request_parties_request_idx
    ON request_parties (
        tenant_id,
        ill_request_id,
        ordinal
    );


-- Audit timeline.
--
-- (recorded_at, id) gives deterministic ordering even when timestamps match.

CREATE INDEX state_audit_logs_timeline_idx
    ON state_audit_logs (
        tenant_id,
        ill_request_id,
        recorded_at,
        id
    );


-- Unprocessed raw provider records.

CREATE INDEX raw_provider_requests_unprocessed_idx
    ON raw_provider_requests (
        tenant_id,
        received_at
    )
    WHERE processed_at IS NULL;


-- Pending effect queue entries.

CREATE INDEX effect_queue_pending_idx
    ON effect_queue (
        tenant_id,
        available_at
    )
    WHERE published_at IS NULL;


-- MERGED: supports worker lease claiming.
--
-- Same predicate as the pending index above; retained as a separate named
-- index only if the implementation needs a distinct claim-specific index.
--
-- If the pending index is sufficient for the actual query plan, this second
-- index can be omitted.

CREATE INDEX effect_queue_claimable_idx
    ON effect_queue (
        tenant_id,
        available_at
    )
    WHERE published_at IS NULL;


-- Sync operations waiting to run again.

CREATE INDEX sync_operations_due_idx
    ON sync_operations (
        tenant_id,
        next_attempt_at
    )
    WHERE status IN ('PENDING', 'UNKNOWN');


-- ============================================================================
-- 2.10 Row-Level Security
-- ============================================================================

-- Tenant isolation is enabled on every application-facing tenant-scoped table.

ALTER TABLE providers
    ENABLE ROW LEVEL SECURITY;

ALTER TABLE providers
    FORCE ROW LEVEL SECURITY;

ALTER TABLE ill_requests
    ENABLE ROW LEVEL SECURITY;

ALTER TABLE ill_requests
    FORCE ROW LEVEL SECURITY;

ALTER TABLE request_parties
    ENABLE ROW LEVEL SECURITY;

ALTER TABLE request_parties
    FORCE ROW LEVEL SECURITY;

ALTER TABLE state_audit_logs
    ENABLE ROW LEVEL SECURITY;

ALTER TABLE state_audit_logs
    FORCE ROW LEVEL SECURITY;

ALTER TABLE raw_provider_requests
    ENABLE ROW LEVEL SECURITY;

ALTER TABLE raw_provider_requests
    FORCE ROW LEVEL SECURITY;

ALTER TABLE effect_queue
    ENABLE ROW LEVEL SECURITY;

ALTER TABLE effect_queue
    FORCE ROW LEVEL SECURITY;

ALTER TABLE sync_operations
    ENABLE ROW LEVEL SECURITY;

ALTER TABLE sync_operations
    FORCE ROW LEVEL SECURITY;


-- Provider isolation.

CREATE POLICY tenant_isolation
    ON providers
    USING (
        tenant_id =
        current_setting('app.tenant_id', true)::uuid
    )
    WITH CHECK (
        tenant_id =
        current_setting('app.tenant_id', true)::uuid
    );


-- ILL request isolation.

CREATE POLICY tenant_isolation
    ON ill_requests
    USING (
        tenant_id =
        current_setting('app.tenant_id', true)::uuid
    )
    WITH CHECK (
        tenant_id =
        current_setting('app.tenant_id', true)::uuid
    );


-- Request-party isolation.

CREATE POLICY tenant_isolation
    ON request_parties
    USING (
        tenant_id =
        current_setting('app.tenant_id', true)::uuid
    )
    WITH CHECK (
        tenant_id =
        current_setting('app.tenant_id', true)::uuid
    );


-- Audit isolation.

CREATE POLICY tenant_isolation
    ON state_audit_logs
    USING (
        tenant_id =
        current_setting('app.tenant_id', true)::uuid
    )
    WITH CHECK (
        tenant_id =
        current_setting('app.tenant_id', true)::uuid
    );


-- Raw provider record isolation.

CREATE POLICY tenant_isolation
    ON raw_provider_requests
    USING (
        tenant_id =
        current_setting('app.tenant_id', true)::uuid
    )
    WITH CHECK (
        tenant_id =
        current_setting('app.tenant_id', true)::uuid
    );


-- Effect queue isolation.

CREATE POLICY tenant_isolation
    ON effect_queue
    USING (
        tenant_id =
        current_setting('app.tenant_id', true)::uuid
    )
    WITH CHECK (
        tenant_id =
        current_setting('app.tenant_id', true)::uuid
    );


-- Sync operation isolation.

CREATE POLICY tenant_isolation
    ON sync_operations
    USING (
        tenant_id =
        current_setting('app.tenant_id', true)::uuid
    )
    WITH CHECK (
        tenant_id =
        current_setting('app.tenant_id', true)::uuid
    );


-- ============================================================================
-- 2.11 Application-role restrictions
-- ============================================================================

-- Audit history is append-only for the application role.
--
-- This does NOT protect against a DBA or a role with sufficient privileges.
-- It prevents the normal application role from modifying/deleting history.

GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO ill_app;
-- Then lock down audit:
REVOKE UPDATE, DELETE ON state_audit_logs FROM ill_app;
GRANT SELECT, INSERT ON state_audit_logs TO ill_app;

-- Sequences if any (UUID defaults often use gen_random_uuid, so may be none)
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO ill_app;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ill_app') THEN
    REVOKE UPDATE, DELETE ON state_audit_logs FROM ill_app;
  END IF;
END
$$;

GRANT SELECT (id, tenant_id, adapter_key, local_library_code,
              enabled, poll_interval_seconds)
    ON providers TO ill_scheduler;

CREATE POLICY scheduler_reads_routing ON providers
    FOR SELECT TO ill_scheduler
    USING (enabled);

-- ============================================================================
-- 3. Notes / invariants
-- ============================================================================
--
-- 1. Only poll_provider() writes provider observations.
--
-- 2. API GET endpoints are read-only and never call Libris.
--
-- 3. Raw provider records are persisted before normalization.
--
-- 4. CanonicalObservation is ephemeral and is not persisted.
--
-- 5. ill_requests is our CURRENT-STATE projection, not a copy of Libris.
--
-- 6. state_audit_logs is append-only HISTORY.
--
-- 7. effect_queue contains only pending EXTERNAL SIDE EFFECTS.
--    It does not mirror every audit event.
--
-- 8. sync_operations is the durable ledger for external operations.
--
-- 9. provider_revision is TEXT because the provider revision is opaque.
--
-- 10. version is OUR optimistic-lock version.
--
-- 11. RLS uses:
--
--       current_setting('app.tenant_id', true)::uuid
--
--     The 'true' means an unset setting returns NULL rather than raising.
--     NULL matches no tenant rows.
--
-- 12. FORCE ROW LEVEL SECURITY is intentional.
--     Without FORCE, the table owner can bypass RLS.
--
-- 13. The application role must NOT own these tables and must NOT have
--     BYPASSRLS.
--
-- 14. All state change + audit + required effect inserts must happen in
--     one database transaction.
--
-- ============================================================================

