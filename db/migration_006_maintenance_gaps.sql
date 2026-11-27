-- Migration 006: maintenance_requests gaps found migrating maintenance-crud
-- + a new maintenance_log table (didn't exist at all before).
--
--   psql -U postgres -d property_platform -f migration_006_maintenance_gaps.sql

ALTER TABLE maintenance_requests
    ADD COLUMN IF NOT EXISTS priority VARCHAR(20) NOT NULL DEFAULT 'normal',
    ADD COLUMN IF NOT EXISTS location_detail TEXT,
    ADD COLUMN IF NOT EXISTS tenant_availability TEXT,
    ADD COLUMN IF NOT EXISTS reported_by_tenant_id UUID REFERENCES tenants(id),
    -- Distinct from scheduled_at (a timestamp of when status changed to
    -- Scheduled) — this is the actual planned work date, e.g. "Bob's
    -- coming 2026-08-10." Conflating these two was a real bug in the
    -- original build, not just a missing field.
    ADD COLUMN IF NOT EXISTS scheduled_date DATE,
    ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS on_hold_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS cancelled_at TIMESTAMPTZ;

CREATE TABLE IF NOT EXISTS maintenance_log (
    id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id               UUID NOT NULL REFERENCES companies(id),
    maintenance_request_id   UUID NOT NULL REFERENCES maintenance_requests(id),
    entry_text               TEXT NOT NULL,
    recorded_by              UUID REFERENCES users(id),
    created_at               TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_maintenance_log_request ON maintenance_log(maintenance_request_id);

ALTER TABLE maintenance_log ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON maintenance_log;
CREATE POLICY tenant_isolation ON maintenance_log
    USING (is_super_admin() OR company_id = current_company_id())
    WITH CHECK (is_super_admin() OR company_id = current_company_id());
