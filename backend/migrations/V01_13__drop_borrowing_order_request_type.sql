-- ============================================================================
-- V01_13 — borrowing_orders: drop request_type
-- ============================================================================
--
-- request_type (LOAN | COPY) does not belong to the local order.
--
-- It is a property of the Libris request, set by the librarian in the Libris
-- interface at A6 when they choose to order a loan or a copy. The bridge
-- learns it from the request record once the order is linked, where it is
-- already modelled as ill_requests.request_type with the same CHECK.
--
-- Carrying it on the order meant intake had to be told the type by its
-- caller, and the bridge had no way to confirm it. An order declared LOAN
-- that Libris later reports as COPY would have disagreed with itself, with
-- the local value having no authority behind it.
--
-- Consequence: N1's "typ av fjärrlån" is not available while an order is
-- still SUBMITTED. It joins the Libris reference and Status as a field that
-- appears once the order is linked, rather than at A5.
--
-- ============================================================================


-- ============================================================================
-- 1. Drop the CHECK, then the column
-- ============================================================================

-- DROP COLUMN removes the constraint with it; naming it keeps the intent
-- visible and makes the migration readable on its own.

ALTER TABLE borrowing_orders
    DROP CONSTRAINT IF EXISTS borrowing_orders_request_type_check;

ALTER TABLE borrowing_orders
    DROP COLUMN IF EXISTS request_type;
