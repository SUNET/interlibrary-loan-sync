-- ============================================================================
-- V01_11 — borrowing_orders: drop order_ref
-- ============================================================================
--
-- order_ref tried to be two things at once and was good at neither:
--
--   * the staff/patron-facing beställnings-id (N1), and
--   * the idempotency key for POST /borrowing/orders.
--
-- Neither ill_flow.md nor borrowing_flow_findings.md says who creates the
-- beställnings-id, and a free-text column gave the bridge no control over
-- what a patron would be quoted. borrowing_orders.id is already unique per
-- tenant -- UNIQUE (tenant_id, id) exists for the composite child foreign
-- keys -- so it can serve as the order reference on its own.
--
-- Consequence for intake: idempotency now rests on the primary key, so the
-- caller must supply the order id for a retried POST to be a no-op. A
-- server-generated id makes every retry a new order. See
-- BorrowingOrderRepository.create_order.
--
-- ============================================================================


-- ============================================================================
-- 1. Drop the idempotency constraint
-- ============================================================================

-- DROP COLUMN would remove this automatically; naming it keeps the intent
-- visible and makes the migration readable on its own.

ALTER TABLE borrowing_orders
    DROP CONSTRAINT IF EXISTS borrowing_orders_tenant_id_order_ref_key;


-- ============================================================================
-- 2. Drop the column
-- ============================================================================

ALTER TABLE borrowing_orders
    DROP COLUMN IF EXISTS order_ref;
