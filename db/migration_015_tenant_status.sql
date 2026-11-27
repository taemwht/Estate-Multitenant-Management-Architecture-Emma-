-- ============================================================
-- Migration 015: tenant status (active / inactive / evicted)
-- ============================================================
-- Lets the Tenants page split current tenants from former ones, and
-- records an eviction: who, when and why. Evicting also switches off the
-- tenant's login (done by the API, not here).
--
-- Safe to re-run. Apply as the database owner (postgres):
--   psql -U postgres -d property_platform -1 -v ON_ERROR_STOP=1 -f migration_015_tenant_status.sql
-- ============================================================

ALTER TABLE tenants ADD COLUMN IF NOT EXISTS status VARCHAR(20) NOT NULL DEFAULT 'active';
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS status_changed_at TIMESTAMPTZ;
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS status_reason TEXT;

ALTER TABLE tenants DROP CONSTRAINT IF EXISTS chk_tenant_status;
ALTER TABLE tenants ADD CONSTRAINT chk_tenant_status CHECK (status IN ('active', 'inactive', 'evicted'));
