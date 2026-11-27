-- Migration 005: soft-delete support on rent_rate_history, so a
-- data-entry error on a historical rent-change record can be corrected
-- the same way rent_receipts can (migration 004).
--
--   psql -U postgres -d property_platform -f migration_005_rent_rate_history_softdelete.sql

ALTER TABLE rent_rate_history
    ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();

CREATE OR REPLACE TRIGGER trg_rent_rate_history_updated_at
    BEFORE UPDATE ON rent_rate_history
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
