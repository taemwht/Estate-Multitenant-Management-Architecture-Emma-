-- ============================================================
-- Migration 013: signed lease documents (PDFs)
-- ============================================================
-- The file itself is stored by the API on disk (FILES_DIR, outside the
-- database); this table records which lease it belongs to. Several files
-- per lease are allowed (original lease, renewals, addenda).
--
-- Visibility follows the lease: company scope here (RLS), and the API
-- additionally limits a tenant to their own leases.
--
-- Safe to re-run. Apply as the database owner (postgres):
--   psql -U postgres -d property_platform -1 -v ON_ERROR_STOP=1 -f migration_013_lease_documents.sql
-- ============================================================

CREATE TABLE IF NOT EXISTS lease_documents (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id   UUID NOT NULL REFERENCES companies(id),
    lease_id     UUID NOT NULL REFERENCES leases(id),
    filename     VARCHAR(255) NOT NULL,       -- name as uploaded, shown to people
    stored_name  VARCHAR(80)  NOT NULL,       -- name on disk (random, never user input)
    size_bytes   INTEGER NOT NULL,
    uploaded_by  UUID REFERENCES users(id),
    uploaded_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    is_deleted   BOOLEAN NOT NULL DEFAULT false
);
CREATE INDEX IF NOT EXISTS idx_lease_documents_lease ON lease_documents(lease_id);

ALTER TABLE lease_documents ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON lease_documents;
CREATE POLICY tenant_isolation ON lease_documents
    USING (is_super_admin() OR company_id = current_company_id())
    WITH CHECK (is_super_admin() OR company_id = current_company_id());

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_platform') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON lease_documents TO app_platform;
    END IF;
END $$;
