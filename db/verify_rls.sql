-- ============================================================
-- RLS verification script
--
-- Run this AS THE APP ROLE (not as postgres/superuser — superusers
-- bypass RLS entirely, so testing as superuser would tell you
-- nothing). e.g.:
--
--   psql -U app_platform -d property_platform -f verify_rls.sql
-- ============================================================

-- Seeding needs super-admin bypass: the companies/rental_units RLS
-- policies won't let a normal session insert rows for companies it
-- doesn't belong to yet (that's the policy working correctly).
SET app.is_super_admin = 'true';

-- Clean slate for repeat runs
DELETE FROM rental_units WHERE unit_reference IN ('A-101', 'B-101');
DELETE FROM companies WHERE name IN ('Test Co A', 'Test Co B');

-- Seed two companies, one unit each
INSERT INTO companies (id, name) VALUES
    ('11111111-1111-1111-1111-111111111111', 'Test Co A'),
    ('22222222-2222-2222-2222-222222222222', 'Test Co B');

INSERT INTO rental_units (company_id, unit_reference, city) VALUES
    ('11111111-1111-1111-1111-111111111111', 'A-101', 'Fremont'),
    ('22222222-2222-2222-2222-222222222222', 'B-101', 'Oakland');

-- Drop the bypass before the actual isolation tests below —
-- otherwise we'd be testing nothing.
SET app.is_super_admin = 'false';

-- --- Test 1: as Company A, should see ONLY A-101 ---
SET app.current_company_id = '11111111-1111-1111-1111-111111111111';
SET app.is_super_admin = 'false';
SELECT unit_reference, city FROM rental_units;
-- Expected: 1 row, A-101 only

-- --- Test 2: as Company B, should see ONLY B-101 ---
SET app.current_company_id = '22222222-2222-2222-2222-222222222222';
SELECT unit_reference, city FROM rental_units;
-- Expected: 1 row, B-101 only

-- --- Test 3: as super admin, should see BOTH ---
SET app.is_super_admin = 'true';
SELECT unit_reference, city FROM rental_units ORDER BY unit_reference;
-- Expected: 2 rows, A-101 and B-101

-- --- Test 4: Company A cannot write into Company B's row ---
SET app.is_super_admin = 'false';
SET app.current_company_id = '11111111-1111-1111-1111-111111111111';
UPDATE rental_units SET city = 'Hacked' WHERE unit_reference = 'B-101';
-- Expected: UPDATE 0 (the row is invisible, so nothing matches)

RESET app.current_company_id;
RESET app.is_super_admin;
