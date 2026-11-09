-- ============================================================================
-- V01_10 — borrowing_orders: patron check outcome + handling state
-- ============================================================================
--
-- Two changes to the A5 order table:
--
--   1. folio_user_status gains CHECK_FAILED and loses AMBIGUOUS.
--      The patron check matches on patron_barcode, which is unique in FOLIO,
--      so more than one hit is not an expected outcome. An unreachable FOLIO
--      must still be recorded, and must not be recorded as NOT_FOUND: the
--      infodisk mail would then tell staff the patron does not exist when we
--      simply do not know.
--
--   2. processing_state records whether the effects owed by the order have
--      completed. Deliberately NOT the ill_requests vocabulary: an order owes
--      one effect (the infodisk mail), so it is either handled or it is not.
--      Why it is unhandled lives on the effect_queue row (attempts,
--      last_error), not here.
--
-- ============================================================================


-- ============================================================================
-- 1. folio_user_status: AMBIGUOUS -> CHECK_FAILED
-- ============================================================================

-- No endpoint writes this column yet, so this should match no rows. Kept so
-- the migration cannot fail on a hand-inserted test row.

UPDATE borrowing_orders
    SET folio_user_status = 'CHECK_FAILED'
    WHERE folio_user_status = 'AMBIGUOUS';

ALTER TABLE borrowing_orders
    DROP CONSTRAINT IF EXISTS borrowing_orders_folio_user_status_check;

ALTER TABLE borrowing_orders
    ADD CONSTRAINT borrowing_orders_folio_user_status_check
    CHECK (
        folio_user_status IN (
            'FOUND',
            'NOT_FOUND',
            'CHECK_FAILED'
        )
    );


-- ============================================================================
-- 2. processing_state
-- ============================================================================

-- UNHANDLED  at least one effect is still queued, retrying or abandoned
-- HANDLED    every effect owed by this order was confirmed
--
-- Set by the effect dispatcher, not by intake: an order starts UNHANDLED
-- because its infodisk mail has not been sent yet.

ALTER TABLE borrowing_orders
    ADD COLUMN processing_state TEXT NOT NULL DEFAULT 'UNHANDLED';

ALTER TABLE borrowing_orders
    ADD CONSTRAINT borrowing_orders_processing_state_check
    CHECK (
        processing_state IN (
            'HANDLED',
            'UNHANDLED'
        )
    );


-- ============================================================================
-- 3. Indexes
-- ============================================================================

-- Orders whose effects have not completed. Partial, so it stays small once
-- the mail has gone out for most orders. Mirrors ill_requests_attention_idx.

CREATE INDEX borrowing_orders_attention_idx
    ON borrowing_orders (
        tenant_id,
        updated_at DESC
    )
    WHERE processing_state = 'UNHANDLED';
