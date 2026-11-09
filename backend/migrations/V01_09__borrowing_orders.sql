-- ============================================================================
-- V01_09 — borrowing_orders
-- ============================================================================
--
-- Phase A of the borrowing (inlån) flow, node A5 in ill_flow.md.
--
-- A borrowing order is created at A5, before any Libris request exists, and
-- is later linked to the BORROWING ill_request a librarian creates by hand in
-- Libris (A6).
--
-- effect_queue gains borrowing_order_id so effects queued at A5 (the infodisk
-- mail), when no ill_request exists yet, can point at the order. Every
-- effect_queue row points at exactly one of ill_request_id or
-- borrowing_order_id.
--
-- The link itself (ill_requests.borrowing_order_id) belongs to the A6-link
-- work and is not part of this migration.
--
-- ============================================================================


-- ============================================================================
-- borrowing_orders
-- ============================================================================

CREATE TABLE borrowing_orders (
    id                       UUID PRIMARY KEY,

    tenant_id                UUID NOT NULL REFERENCES tenants(id),

    -- Staff/patron-facing order id (beställnings-id).
    -- Supplied by the caller; a re-submit with the same value is a no-op.
    order_ref                TEXT NOT NULL,

    state                    TEXT NOT NULL DEFAULT 'SUBMITTED'
                             CHECK (
                                 state IN (
                                     'SUBMITTED',
                                     'LINKED',
                                     'CANCELLED'
                                 )
                             ),
    -- SUBMITTED  saved, infodisk mail queued
    -- LINKED     at least one Libris request linked; NOT terminal
    --            (a re-order links another request)
    -- CANCELLED  cancelled before Libris; terminal

    request_type             TEXT NOT NULL
                             CHECK (
                                 request_type IN ('LOAN', 'COPY')
                             ),

    -- Prefilled from discovery (A4).
    bibliographic            JSONB NOT NULL,

    -- Patron identifier supplied at A5; used for the FOLIO patron check.
    -- Provisional: storage form may change after discussion with the customer.
    patron_barcode           TEXT NOT NULL,

    -- låntagarens namn (N1). Shown on the N1 staff screen.
    -- Provisional: storage form may change after discussion with the customer.
    patron_name              TEXT NOT NULL,

    -- Result of the FOLIO patron check at intake. Never blocks the order.
    folio_user_status        TEXT NOT NULL
                             CHECK (
                                 folio_user_status IN (
                                     'FOUND',
                                     'NOT_FOUND',
                                     'AMBIGUOUS'
                                 )
                             ),

    -- Set when folio_user_status = 'FOUND'.
    folio_user_id            UUID,

    pickup_service_point_id  UUID,

    -- The Libris lf_number the librarian entered after creating the request
    -- in the Libris UI. Written once; kept as the record of what the human
    -- entered, not cleared when the link resolves.
    libris_lf_number         TEXT,

    created_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at               TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- Required for composite child foreign keys.
    UNIQUE (tenant_id, id),

    -- Idempotent intake.
    UNIQUE (tenant_id, order_ref)
);


-- ============================================================================
-- borrowing_order_comments
-- ============================================================================

-- Staff notes (personalkommentarer). One row per note so author and time
-- are kept, instead of a single mutable column.

CREATE TABLE borrowing_order_comments (
    id                   UUID PRIMARY KEY,

    tenant_id            UUID NOT NULL REFERENCES tenants(id),

    borrowing_order_id   UUID NOT NULL,

    author               TEXT NOT NULL,

    body                 TEXT NOT NULL,

    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),

    FOREIGN KEY (tenant_id, borrowing_order_id)
        REFERENCES borrowing_orders(tenant_id, id)
);


-- ============================================================================
-- effect_queue — borrowing order as effect subject
-- ============================================================================

-- Effects queued at A5 have no ill_request yet; they point at the order.
-- Once the order is linked, effects point at the ill_request as before.

ALTER TABLE effect_queue
    ADD COLUMN borrowing_order_id UUID;

ALTER TABLE effect_queue
    ADD CONSTRAINT effect_queue_tenant_id_borrowing_order_id_fkey
    FOREIGN KEY (tenant_id, borrowing_order_id)
        REFERENCES borrowing_orders(tenant_id, id);

-- Exactly one subject per effect.
-- Fails if any existing row has ill_request_id IS NULL.

ALTER TABLE effect_queue
    ADD CONSTRAINT effect_queue_one_subject_check
    CHECK (
        num_nonnulls(ill_request_id, borrowing_order_id) = 1
    );


-- ============================================================================
-- Indexes
-- ============================================================================

-- At most one order may claim a given Libris lf_number (A6-link).

CREATE UNIQUE INDEX borrowing_orders_lf_number_uq
    ON borrowing_orders (
        tenant_id,
        libris_lf_number
    )
    WHERE libris_lf_number IS NOT NULL;


-- Staff list:
-- GET /borrowing/orders?state=

CREATE INDEX borrowing_orders_dashboard_idx
    ON borrowing_orders (
        tenant_id,
        state,
        updated_at DESC
    );


-- Patron lookup:
-- GET /borrowing/orders?patron=

CREATE INDEX borrowing_orders_patron_idx
    ON borrowing_orders (
        tenant_id,
        patron_barcode
    );


-- Comment timeline per order.

CREATE INDEX borrowing_order_comments_order_idx
    ON borrowing_order_comments (
        tenant_id,
        borrowing_order_id,
        created_at,
        id
    );


-- ============================================================================
-- Row-Level Security
-- ============================================================================

ALTER TABLE borrowing_orders
    ENABLE ROW LEVEL SECURITY;

ALTER TABLE borrowing_orders
    FORCE ROW LEVEL SECURITY;

ALTER TABLE borrowing_order_comments
    ENABLE ROW LEVEL SECURITY;

ALTER TABLE borrowing_order_comments
    FORCE ROW LEVEL SECURITY;


CREATE POLICY tenant_isolation
    ON borrowing_orders
    USING (
        tenant_id =
        current_setting('app.tenant_id', true)::uuid
    )
    WITH CHECK (
        tenant_id =
        current_setting('app.tenant_id', true)::uuid
    );


CREATE POLICY tenant_isolation
    ON borrowing_order_comments
    USING (
        tenant_id =
        current_setting('app.tenant_id', true)::uuid
    )
    WITH CHECK (
        tenant_id =
        current_setting('app.tenant_id', true)::uuid
    );


-- ============================================================================
-- Application-role grants
-- ============================================================================

-- V01_01 grants ON ALL TABLES, which only covers tables that existed then.

GRANT SELECT, INSERT, UPDATE, DELETE ON borrowing_orders TO ill_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON borrowing_order_comments TO ill_app;
