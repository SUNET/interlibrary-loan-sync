-- ============================================================================
-- V01_15 — tenants: infodisk recipient address
-- ============================================================================
--
-- The A5 infodisk mail needs a destination, and it differs per institution,
-- so it cannot be a constant in the handler or a single value in Settings.
-- It belongs beside the tenant it describes.
--
-- Nullable on purpose. A tenant that has not been given an address yet is a
-- real state -- HH below is in it -- and the NOT NULL alternative would mean
-- inventing an address for every tenant at migration time. The NOTIFY_INFODISK
-- handler must treat NULL as REFUSED: it is a configuration gap for a human
-- to close, not a transient failure worth retrying.
--
-- One address, not an array. A desk with several readers is served by a
-- distribution-list address, which needs no schema change. Add an array only
-- when a tenant genuinely needs independent recipients.
--
-- ============================================================================


-- ============================================================================
-- 1. Column
-- ============================================================================

ALTER TABLE tenants
    ADD COLUMN IF NOT EXISTS infodisk_email TEXT;


-- Sanity check, not validation. Catches an empty string or a value that is
-- plainly not an address; it does not attempt RFC 5322. Deliverability is
-- proven by sending, not by a constraint.

ALTER TABLE tenants
    DROP CONSTRAINT IF EXISTS tenants_infodisk_email_check;

ALTER TABLE tenants
    ADD CONSTRAINT tenants_infodisk_email_check
    CHECK (
        infodisk_email IS NULL
        OR position('@' IN infodisk_email) > 1
    );
