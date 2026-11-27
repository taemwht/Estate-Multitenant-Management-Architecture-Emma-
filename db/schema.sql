-- ============================================================
-- Multi-Company Property Management System
-- Core schema + Postgres Row-Level Security (multi-tenancy)
-- Ref: PRD v1, 2026-08-05
--
-- Run this against a FRESH database (not `rental_house`, which is
-- EMMA's old single-tenant schema). See README.md for setup steps.
-- ============================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;  -- for gen_random_uuid()

-- ------------------------------------------------------------
-- Helper: auto-update updated_at on row UPDATE
-- ------------------------------------------------------------
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ============================================================
-- 1. Companies (PRD 2.1 / 4)
-- ============================================================
CREATE TABLE companies (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            VARCHAR(255) NOT NULL,
    contact_email   VARCHAR(255),
    contact_phone   VARCHAR(50),
    status          VARCHAR(20) NOT NULL DEFAULT 'active'
                        CHECK (status IN ('active', 'suspended')),
    settings        JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TRIGGER trg_companies_updated_at
    BEFORE UPDATE ON companies
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ============================================================
-- 2. Users (auth + role)  (PRD 2.2-2.6, 3, 4.11)
--
-- company_id is nullable for BOTH super_admin and contractor roles.
-- See the PRD inconsistency note above the file / in chat.
-- ============================================================
CREATE TABLE users (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id          UUID REFERENCES companies(id),
    role                VARCHAR(20) NOT NULL
                            CHECK (role IN ('super_admin', 'company_admin', 'staff', 'contractor', 'tenant')),
    email               VARCHAR(255) NOT NULL UNIQUE,
    password_hash       VARCHAR(255) NOT NULL,
    telegram_link_id    VARCHAR(255) UNIQUE,
    is_deleted          BOOLEAN NOT NULL DEFAULT false,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_company_required_by_role CHECK (
        (role = 'super_admin' AND company_id IS NULL)
        OR (role = 'contractor')  -- nullable either way; real scope is contractor_companies
        OR (role IN ('company_admin', 'staff', 'tenant') AND company_id IS NOT NULL)
    )
);
CREATE INDEX idx_users_company ON users(company_id);
CREATE TRIGGER trg_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ============================================================
-- 3. Rental Units (PRD 4.1)
-- ============================================================
CREATE TABLE rental_units (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id      UUID NOT NULL REFERENCES companies(id),
    unit_reference  VARCHAR(100) NOT NULL,  -- admin-defined, used as import join key
    address_line1   VARCHAR(255),
    address_line2   VARCHAR(255),
    city            VARCHAR(100),
    state           VARCHAR(50),
    zip_code        VARCHAR(20),
    unit_type       VARCHAR(50),
    status          VARCHAR(20) NOT NULL DEFAULT 'active'
                        CHECK (status IN ('active', 'deleted')),
    is_deleted      BOOLEAN NOT NULL DEFAULT false,
    deleted_at      TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (company_id, unit_reference)
);
CREATE INDEX idx_rental_units_company ON rental_units(company_id);
CREATE TRIGGER trg_rental_units_updated_at
    BEFORE UPDATE ON rental_units
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ============================================================
-- 4. Leases (PRD 4.2)
-- ============================================================
CREATE TABLE leases (
    id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id               UUID NOT NULL REFERENCES companies(id),  -- denormalized for RLS
    rental_unit_id           UUID NOT NULL REFERENCES rental_units(id),
    start_date               DATE NOT NULL,
    end_date                 DATE,
    monthly_rent             NUMERIC(10, 2) NOT NULL,
    due_day_of_month         SMALLINT NOT NULL CHECK (due_day_of_month BETWEEN 1 AND 31),
    security_deposit_amount  NUMERIC(10, 2) NOT NULL DEFAULT 0,
    status                   VARCHAR(20) NOT NULL DEFAULT 'active'
                                 CHECK (status IN ('active', 'ended')),
    created_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at               TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- Enforce one active lease per unit
CREATE UNIQUE INDEX uq_one_active_lease_per_unit ON leases(rental_unit_id) WHERE status = 'active';
CREATE INDEX idx_leases_company ON leases(company_id);
CREATE INDEX idx_leases_unit ON leases(rental_unit_id);
CREATE TRIGGER trg_leases_updated_at
    BEFORE UPDATE ON leases
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ============================================================
-- 5. Tenants — business entity (PRD 4.3)
-- ============================================================
CREATE TABLE tenants (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id  UUID NOT NULL REFERENCES companies(id),
    user_id     UUID REFERENCES users(id),  -- nullable: portal login is optional
    name        VARCHAR(255) NOT NULL,
    email       VARCHAR(255),
    phone       VARCHAR(50),
    is_deleted  BOOLEAN NOT NULL DEFAULT false,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_tenants_company ON tenants(company_id);
CREATE TRIGGER trg_tenants_updated_at
    BEFORE UPDATE ON tenants
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- Co-tenants per lease
CREATE TABLE lease_tenants (
    lease_id    UUID NOT NULL REFERENCES leases(id),
    tenant_id   UUID NOT NULL REFERENCES tenants(id),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (lease_id, tenant_id)
);

-- ============================================================
-- 6. Rent Receipts (PRD 4.4)
-- ============================================================
CREATE TABLE rent_receipts (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id     UUID NOT NULL REFERENCES companies(id),
    lease_id       UUID NOT NULL REFERENCES leases(id),
    amount         NUMERIC(10, 2) NOT NULL,
    date_received  DATE NOT NULL,
    method         VARCHAR(20) NOT NULL CHECK (method IN ('check', 'cash', 'other')),
    recorded_by    UUID REFERENCES users(id),
    notes          TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_rent_receipts_company ON rent_receipts(company_id);
CREATE INDEX idx_rent_receipts_lease ON rent_receipts(lease_id);

-- ============================================================
-- 7. Security Deposits (PRD 4.5)
-- ============================================================
CREATE TABLE security_deposits (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id         UUID NOT NULL REFERENCES companies(id),
    lease_id           UUID NOT NULL UNIQUE REFERENCES leases(id),
    amount_collected   NUMERIC(10, 2) NOT NULL DEFAULT 0,
    amount_returned    NUMERIC(10, 2),
    amount_deducted    NUMERIC(10, 2),
    deduction_reason   TEXT,
    status             VARCHAR(20) NOT NULL DEFAULT 'collected'
                           CHECK (status IN ('collected', 'held', 'returned', 'deducted')),
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_security_deposits_company ON security_deposits(company_id);
CREATE TRIGGER trg_security_deposits_updated_at
    BEFORE UPDATE ON security_deposits
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ============================================================
-- 8. Contractors — cross-company entity (PRD 4.7)
-- ============================================================
CREATE TABLE contractors (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id        UUID REFERENCES users(id),
    name           VARCHAR(255) NOT NULL,
    contact_email  VARCHAR(255),
    contact_phone  VARCHAR(50),
    trade          VARCHAR(100),
    is_deleted     BOOLEAN NOT NULL DEFAULT false,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TRIGGER trg_contractors_updated_at
    BEFORE UPDATE ON contractors
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- Which companies a contractor works for — this table drives their
-- RLS visibility, NOT users.company_id
CREATE TABLE contractor_companies (
    contractor_id  UUID NOT NULL REFERENCES contractors(id),
    company_id     UUID NOT NULL REFERENCES companies(id),
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (contractor_id, company_id)
);
CREATE INDEX idx_contractor_companies_company ON contractor_companies(company_id);

-- ============================================================
-- 9. Maintenance Requests (PRD 4.6)
-- ============================================================
CREATE TABLE maintenance_requests (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id              UUID NOT NULL REFERENCES companies(id),
    rental_unit_id          UUID NOT NULL REFERENCES rental_units(id),
    submitted_by            UUID REFERENCES users(id),
    description             TEXT NOT NULL,
    status                  VARCHAR(20) NOT NULL DEFAULT 'Submitted'
                                CHECK (status IN ('Submitted', 'Scheduled', 'In Progress', 'Completed', 'Verified')),
    assigned_contractor_id  UUID REFERENCES contractors(id),
    verified_by             UUID REFERENCES users(id),
    submitted_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    scheduled_at            TIMESTAMPTZ,
    in_progress_at          TIMESTAMPTZ,
    completed_at            TIMESTAMPTZ,
    verified_at             TIMESTAMPTZ,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_maintenance_company ON maintenance_requests(company_id);
CREATE INDEX idx_maintenance_unit ON maintenance_requests(rental_unit_id);
CREATE INDEX idx_maintenance_status ON maintenance_requests(status);
CREATE TRIGGER trg_maintenance_updated_at
    BEFORE UPDATE ON maintenance_requests
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE maintenance_photos (
    id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    maintenance_request_id  UUID NOT NULL REFERENCES maintenance_requests(id),
    file_url                VARCHAR(500) NOT NULL,
    uploaded_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_maintenance_photos_request ON maintenance_photos(maintenance_request_id);

-- ============================================================
-- 10. Contractor Payments (PRD 4.8)
-- ============================================================
CREATE TABLE contractor_payments (
    id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id               UUID NOT NULL REFERENCES companies(id),
    contractor_id            UUID NOT NULL REFERENCES contractors(id),
    maintenance_request_id   UUID REFERENCES maintenance_requests(id),
    amount                   NUMERIC(10, 2) NOT NULL,
    date_paid                DATE NOT NULL,
    invoice_file             VARCHAR(500),
    recorded_by              UUID REFERENCES users(id),
    created_at                TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_contractor_payments_company ON contractor_payments(company_id);
CREATE INDEX idx_contractor_payments_contractor ON contractor_payments(contractor_id);

-- ============================================================
-- 11. Annual Safety Check-ins (PRD 4.9)
-- ============================================================
CREATE TABLE annual_checkins (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id       UUID NOT NULL REFERENCES companies(id),
    lease_id         UUID NOT NULL REFERENCES leases(id),
    year             SMALLINT NOT NULL,
    hazard_type      VARCHAR(30) NOT NULL
                         CHECK (hazard_type IN ('co_detector', 'smoke_detector', 'mold', 'lead_paint', 'asbestos')),
    acknowledged_by  UUID REFERENCES tenants(id),
    acknowledged_at  TIMESTAMPTZ,
    evidence_file    VARCHAR(500),
    due_date         DATE NOT NULL,
    reminder_count   INT NOT NULL DEFAULT 0,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (lease_id, year, hazard_type)
);
CREATE INDEX idx_annual_checkins_company ON annual_checkins(company_id);
CREATE INDEX idx_annual_checkins_lease ON annual_checkins(lease_id);

-- ============================================================
-- 12. Audit Log (PRD 4.10)
-- ============================================================
CREATE TABLE audit_log (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id    UUID REFERENCES companies(id),  -- nullable: super_admin cross-company actions
    actor_id      UUID REFERENCES users(id),
    actor_type    VARCHAR(10) NOT NULL CHECK (actor_type IN ('user', 'hermes')),
    action        VARCHAR(100) NOT NULL,
    entity_type   VARCHAR(100) NOT NULL,
    entity_id     UUID,
    before_state  JSONB,
    after_state   JSONB,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_audit_log_company ON audit_log(company_id);
CREATE INDEX idx_audit_log_entity ON audit_log(entity_type, entity_id);

-- ============================================================
-- 13. Import Batches (PRD 4 / 12)
-- ============================================================
CREATE TABLE import_batches (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id          UUID NOT NULL REFERENCES companies(id),
    uploaded_by         UUID REFERENCES users(id),
    file_name           VARCHAR(255) NOT NULL,
    uploaded_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    status              VARCHAR(20) NOT NULL DEFAULT 'processing'
                            CHECK (status IN ('processing', 'completed', 'failed')),
    rows_succeeded      INT NOT NULL DEFAULT 0,
    rows_failed         INT NOT NULL DEFAULT 0,
    error_report_file   VARCHAR(500)
);
CREATE INDEX idx_import_batches_company ON import_batches(company_id);

-- ============================================================
-- ROW-LEVEL SECURITY (multi-tenancy isolation)
--
-- Pattern: every company-scoped table gets a policy that only
-- allows rows where company_id matches the session's
-- app.current_company_id, unless app.is_super_admin = 'true'.
--
-- IMPORTANT: the app's DB connection role must NOT be a superuser
-- and must NOT have BYPASSRLS. Postgres superusers silently bypass
-- RLS no matter what the policy says. See README.md.
-- ============================================================

CREATE OR REPLACE FUNCTION current_company_id() RETURNS UUID AS $$
    SELECT NULLIF(current_setting('app.current_company_id', true), '')::UUID;
$$ LANGUAGE sql STABLE;

CREATE OR REPLACE FUNCTION is_super_admin() RETURNS BOOLEAN AS $$
    SELECT COALESCE(current_setting('app.is_super_admin', true), 'false') = 'true';
$$ LANGUAGE sql STABLE;

-- Companies: visible if it's your own company, or you're super admin
ALTER TABLE companies ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON companies
    USING (is_super_admin() OR id = current_company_id())
    WITH CHECK (is_super_admin());

-- Users: own company's users, plus rows with no company (super admin / contractor)
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON users
    USING (is_super_admin() OR company_id = current_company_id() OR company_id IS NULL)
    WITH CHECK (is_super_admin() OR company_id = current_company_id());

-- Straightforward company_id-scoped tables
DO $$
DECLARE
    t TEXT;
BEGIN
    FOR t IN
        SELECT unnest(ARRAY[
            'rental_units', 'leases', 'tenants', 'rent_receipts',
            'security_deposits', 'maintenance_requests', 'contractor_payments',
            'annual_checkins', 'import_batches'
        ])
    LOOP
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
        EXECUTE format(
            'CREATE POLICY tenant_isolation ON %I
                USING (is_super_admin() OR company_id = current_company_id())
                WITH CHECK (is_super_admin() OR company_id = current_company_id())',
            t
        );
    END LOOP;
END $$;

-- Audit log: read-scoped by company, nullable for cross-company super admin actions
ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON audit_log
    USING (is_super_admin() OR company_id = current_company_id());

-- Contractors: no company_id column — visibility comes through contractor_companies
ALTER TABLE contractors ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON contractors
    USING (
        is_super_admin()
        OR EXISTS (
            SELECT 1 FROM contractor_companies cc
            WHERE cc.contractor_id = contractors.id
              AND cc.company_id = current_company_id()
        )
    );

ALTER TABLE contractor_companies ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON contractor_companies
    USING (is_super_admin() OR company_id = current_company_id());

-- Join/child tables scoped via their parent's company_id
ALTER TABLE lease_tenants ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON lease_tenants
    USING (
        is_super_admin()
        OR EXISTS (SELECT 1 FROM leases l WHERE l.id = lease_tenants.lease_id AND l.company_id = current_company_id())
    );

ALTER TABLE maintenance_photos ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON maintenance_photos
    USING (
        is_super_admin()
        OR EXISTS (
            SELECT 1 FROM maintenance_requests m
            WHERE m.id = maintenance_photos.maintenance_request_id
              AND m.company_id = current_company_id()
        )
    );
