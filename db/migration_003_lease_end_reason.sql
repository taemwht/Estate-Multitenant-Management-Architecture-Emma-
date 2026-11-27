-- Migration 003: add end_reason to leases, so ending a lease can record
-- WHY (eviction, normal move-out, etc.) — not just that it ended.
--
--   psql -U postgres -d property_platform -f migration_003_lease_end_reason.sql

ALTER TABLE leases
    ADD COLUMN IF NOT EXISTS end_reason VARCHAR(50);
