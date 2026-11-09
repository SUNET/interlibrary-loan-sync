-- ============================================================================
-- V01_12 — borrowing_orders: drop pickup_service_point_id, allow early
--          libris_lf_number
-- ============================================================================
--
-- 1. pickup_service_point_id is removed from the order.
--
--    It was carried here so A6-link could copy it onto the ill_request for
--    the FOLIO hold created at A7. The pickup point is a FOLIO circulation
--    concern, not something the order needs to know at A5, and open question
--    Q4 (patron choice, or a tenant default?) was never settled -- so the
--    column stored nothing anybody had decided how to fill.
--
--    A7 still needs a pickup service point to create the hold. It must come
--    from tenant configuration or from the FOLIO user, and that decision is
--    now unavoidable rather than deferred behind an unused column. The
--    reserved comment on ill_requests (V01_01, "Part 6+") is untouched.
--
-- 2. libris_lf_number is unchanged structurally, but is now writable at
--    creation time as well as by a later update. The column, its NULL
--    default and the partial unique index borrowing_orders_lf_number_uq all
--    already allow this; nothing in the schema had to change. Recorded here
--    because it is a deliberate behavioural change in the API, not an
--    accident:
--
--      * normal case  -- order created at A5 with no reference, a librarian
--                        records the lf_number after creating the request by
--                        hand in Libris (A6)
--      * direct case  -- the Libris request already exists, so the order is
--                        created with its reference in one call
--
--    Setting the reference does NOT move the order to LINKED. It records
--    what a human typed; the link itself is ill_requests.borrowing_order_id,
--    resolved against the Libris record.
--
-- ============================================================================


-- ============================================================================
-- 1. Drop pickup_service_point_id
-- ============================================================================

ALTER TABLE borrowing_orders
    DROP COLUMN IF EXISTS pickup_service_point_id;
