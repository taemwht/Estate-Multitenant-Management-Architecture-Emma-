-- Migration 008: fixes from the 2026-11-26 review.
--
--   psql -U postgres -d property_platform -f migration_008_review_fixes.sql
--
-- Safe to re-run. Covers:
--   1. maintenance_requests.status CHECK never allowed 'On Hold' or
--      'Cancelled' (migration 006 added the timestamps but not the values),
--      so the API's PATCH to either status failed with a 500.
--   2. users RLS let every company read every super_admin / contractor
--      login row (company_id IS NULL), password_hash included. Now a
--      company-less row is visible only to super admin or to that user.
--   3. contractors RLS let any linked company edit or soft-delete a
--      contractor shared with other companies. Edits are now limited to
--      the company that created the contractor; "delete" is per-company
--      (contractor_companies.is_deleted) so it only hides the contractor
--      from the company that removed it.
--   4. Tables created by migrations (rent_rate_history, maintenance_log)
--      were never granted to app_platform. Re-grants everything and sets
--      default privileges so future tables are covered automatically.

-- ------------------------------------------------------------
-- 1. Maintenance status vocabulary
-- ------------------------------------------------------------
DO $$
DECLARE
    c TEXT;
BEGIN
    FOR c IN
        SELECT conname FROM pg_constraint
        WHERE conrelid = 'maintenance_requests'::regclass
          AND contype = 'c'
          AND pg_get_constraintdef(oid) LIKE '%status%'
    LOOP
        EXECUTE format('ALTER TABLE maintenance_requests DROP CONSTRAINT %I', c);
    END LOOP;
END $$;

ALTER TABLE maintenance_requests
    ADD CONSTRAINT chk_maintenance_status CHECK (
        status IN ('Submitted', 'Scheduled', 'In Progress', 'On Hold',
                   'Completed', 'Verified', 'Cancelled')
    );

-- ------------------------------------------------------------
-- 2. Users: company-less rows visible only to super admin / self
-- ------------------------------------------------------------
-- The API sets app.current_user_id from the JWT on every request.
CREATE OR REPLACE FUNCTION current_user_id() RETURNS UUID AS $$
    SELECT NULLIF(current_setting('app.current_user_id', true), '')::UUID;
$$ LANGUAGE sql STABLE;

DROP POLICY IF EXISTS tenant_isolation ON users;
CREATE POLICY tenant_isolation ON users
    USING (is_super_admin() OR company_id = current_company_id() OR id = current_user_id())
    WITH CHECK (is_super_admin() OR company_id = current_company_id());

-- ------------------------------------------------------------
-- 3. Contractors: owner-company edits, per-company delete
-- ------------------------------------------------------------
ALTER TABLE contractors
    ADD COLUMN IF NOT EXISTS created_by_company_id UUID REFERENCES companies(id);
ALTER TABLE contractor_companies
    ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN NOT NULL DEFAULT false;

-- Backfill owner = the first company that linked the contractor.
UPDATE contractors c
SET created_by_company_id = (
    SELECT cc.company_id FROM contractor_companies cc
    WHERE cc.contractor_id = c.id
    ORDER BY cc.created_at, cc.company_id
    LIMIT 1
)
WHERE c.created_by_company_id IS NULL;

-- Existing soft-deletes were made by one company through the API, so move
-- them onto that company's link instead of hiding the contractor globally.
UPDATE contractor_companies cc
SET is_deleted = true
FROM contractors c
WHERE c.id = cc.contractor_id AND c.is_deleted AND NOT cc.is_deleted;
UPDATE contractors SET is_deleted = false WHERE is_deleted;

DROP POLICY IF EXISTS tenant_isolation ON contractors;
DROP POLICY IF EXISTS contractor_select ON contractors;
DROP POLICY IF EXISTS contractor_insert ON contractors;
DROP POLICY IF EXISTS contractor_update ON contractors;
DROP POLICY IF EXISTS contractor_delete ON contractors;

CREATE POLICY contractor_select ON contractors FOR SELECT
    USING (
        is_super_admin()
        OR created_by_company_id = current_company_id()
        OR EXISTS (
            SELECT 1 FROM contractor_companies cc
            WHERE cc.contractor_id = contractors.id
              AND cc.company_id = current_company_id()
        )
    );
CREATE POLICY contractor_insert ON contractors FOR INSERT
    WITH CHECK (is_super_admin() OR created_by_company_id = current_company_id());
CREATE POLICY contractor_update ON contractors FOR UPDATE
    USING (is_super_admin() OR created_by_company_id = current_company_id())
    WITH CHECK (is_super_admin() OR created_by_company_id = current_company_id());
CREATE POLICY contractor_delete ON contractors FOR DELETE
    USING (is_super_admin());

-- ------------------------------------------------------------
-- 4. Grants for the app role (incl. tables created by migrations)
-- ------------------------------------------------------------
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_platform') THEN
        GRANT USAGE ON SCHEMA public TO app_platform;
        GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO app_platform;
        GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO app_platform;
        -- Future tables created by the role running migrations get the
        -- same grants without anyone having to remember.
        EXECUTE format(
            'ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA public '
            'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_platform',
            current_user);
        EXECUTE format(
            'ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA public '
            'GRANT USAGE, SELECT ON SEQUENCES TO app_platform',
            current_user);
    ELSE
        RAISE NOTICE 'Role app_platform does not exist; skipping grants.';
    END IF;
END $$;
