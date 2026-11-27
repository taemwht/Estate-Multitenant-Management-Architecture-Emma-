-- Migration 004: rent history tracking + fixes to rent_receipts
--
--   psql -U postgres -d property_platform -f migration_004_rent_history.sql

ALTER TABLE rent_receipts
    ADD COLUMN IF NOT EXISTS late_fee NUMERIC(10, 2) NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();

CREATE OR REPLACE TRIGGER trg_rent_receipts_updated_at
    BEFORE UPDATE ON rent_receipts
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE IF NOT EXISTS rent_rate_history (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id         UUID NOT NULL REFERENCES companies(id),
    lease_id           UUID NOT NULL REFERENCES leases(id),
    monthly_rent       NUMERIC(10, 2) NOT NULL,
    due_day_of_month   SMALLINT NOT NULL CHECK (due_day_of_month BETWEEN 1 AND 31),
    effective_date     DATE NOT NULL,
    recorded_by        UUID REFERENCES users(id),
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_rent_rate_history_lease ON rent_rate_history(lease_id);

ALTER TABLE rent_rate_history ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON rent_rate_history;
CREATE POLICY tenant_isolation ON rent_rate_history
    USING (is_super_admin() OR company_id = current_company_id())
    WITH CHECK (is_super_admin() OR company_id = current_company_id());
