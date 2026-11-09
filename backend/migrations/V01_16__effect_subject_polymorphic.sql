-- ============================================================================
-- V01_16 — effect_queue: polymorphic subject
-- ============================================================================
--
-- Replaces the two nullable subject columns (ill_request_id, borrowing_order_id)
-- with a single polymorphic reference: subject_type says which table the
-- subject lives in, subject_id is its id.
--
--     subject_type = 'ILL_REQUEST'     -> subject_id = ill_requests.id
--     subject_type = 'BORROWING_ORDER' -> subject_id = borrowing_orders.id
--
-- A single column cannot carry a foreign key into two different tables, so the
-- two composite FKs are dropped and referential integrity for the subject
-- moves into application code and the dispatcher (a missing subject is already
-- an anticipated state: it is kept queued and flagged NEEDS_REVIEW, never
-- silently discarded).
--
-- Unaffected by this migration: row-level security on tenant_id, the
-- UNIQUE (tenant_id, effect_key) idempotency key, and the lease/fence columns.
--
-- ============================================================================


-- ============================================================================
-- 1. New columns (nullable first, so existing rows can be backfilled)
-- ============================================================================

ALTER TABLE effect_queue
    ADD COLUMN subject_type TEXT;

ALTER TABLE effect_queue
    ADD COLUMN subject_id UUID;


-- ============================================================================
-- 2. Backfill from the old columns
-- ============================================================================

-- Every existing row points at exactly one subject (enforced until now by
-- effect_queue_one_subject_check), so these two statements are disjoint and
-- together cover every row.

UPDATE effect_queue
    SET subject_type = 'ILL_REQUEST',
        subject_id   = ill_request_id
    WHERE ill_request_id IS NOT NULL;

UPDATE effect_queue
    SET subject_type = 'BORROWING_ORDER',
        subject_id   = borrowing_order_id
    WHERE borrowing_order_id IS NOT NULL;


-- ============================================================================
-- 3. Tighten: NOT NULL + allowed subject types
-- ============================================================================

ALTER TABLE effect_queue
    ALTER COLUMN subject_type SET NOT NULL;

ALTER TABLE effect_queue
    ALTER COLUMN subject_id SET NOT NULL;

ALTER TABLE effect_queue
    ADD CONSTRAINT effect_queue_subject_type_check
    CHECK (subject_type IN ('ILL_REQUEST', 'BORROWING_ORDER'));


-- ============================================================================
-- 4. Drop the old subject design
-- ============================================================================

ALTER TABLE effect_queue
    DROP CONSTRAINT IF EXISTS effect_queue_one_subject_check;

ALTER TABLE effect_queue
    DROP CONSTRAINT IF EXISTS effect_queue_tenant_id_ill_request_id_fkey;

ALTER TABLE effect_queue
    DROP CONSTRAINT IF EXISTS effect_queue_tenant_id_borrowing_order_id_fkey;

ALTER TABLE effect_queue
    DROP COLUMN ill_request_id;

ALTER TABLE effect_queue
    DROP COLUMN borrowing_order_id;


-- ============================================================================
-- 5. Index the subject lookup the dropped FKs used to cover
-- ============================================================================

CREATE INDEX effect_queue_subject_idx
    ON effect_queue (tenant_id, subject_type, subject_id);
