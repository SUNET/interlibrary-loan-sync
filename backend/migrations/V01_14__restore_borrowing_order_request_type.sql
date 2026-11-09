-- ============================================================================
-- V01_14 — borrowing_orders: restore request_type
-- ============================================================================
--
-- Reverts V01_13. request_type (LOAN | COPY) belongs on the local order after
-- all: the patron chooses between ordering the item and ordering a copy at
-- A3/B3, before any Libris request exists, so the order must carry it from
-- A5. ill_requests.request_type remains the Libris-side value; the two are
-- the same question answered at different points, and a disagreement between
-- them is information rather than a contradiction.
--
-- Restores the exact shape V01_09 created: TEXT NOT NULL, CHECK (LOAN|COPY),
-- no default.
--
-- DATA LOSS WARNING
-- -----------------
-- V01_13 dropped the column. Any value it held is gone and cannot be
-- recovered from the order. The backfill below assigns 'LOAN' to rows that
-- survive the round trip, which is a guess: a COPY order mislabelled LOAN
-- would be given real FOLIO inventory at A7 for something that arrives as a
-- PDF by email.
--
-- Verify before applying:
--
--     SELECT count(*) FROM borrowing_orders;
--
-- If that is 0, the backfill touches nothing and the guess is harmless. If
-- it is not 0, check those rows by hand afterwards.
--
-- ============================================================================


-- ============================================================================
-- 1. Add the column back, nullable for the backfill
-- ============================================================================

ALTER TABLE borrowing_orders
    ADD COLUMN IF NOT EXISTS request_type TEXT;


-- ============================================================================
-- 2. Backfill rows whose value V01_13 destroyed
-- ============================================================================

UPDATE borrowing_orders
    SET request_type = 'LOAN'
    WHERE request_type IS NULL;


-- ============================================================================
-- 3. Reinstate the original constraints
-- ============================================================================

ALTER TABLE borrowing_orders
    ALTER COLUMN request_type SET NOT NULL;

ALTER TABLE borrowing_orders
    DROP CONSTRAINT IF EXISTS borrowing_orders_request_type_check;

ALTER TABLE borrowing_orders
    ADD CONSTRAINT borrowing_orders_request_type_check
    CHECK (
        request_type IN (
            'LOAN',
            'COPY'
        )
    );
