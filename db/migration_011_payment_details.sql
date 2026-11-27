-- ============================================================
-- Migration 011: who paid, how, and for which month
-- ============================================================
-- Rent payments get:
--   * more payment methods (Zelle, Venmo, bank transfer, card, money
--     order), so "other" is only for anything else;
--   * method_detail: free text such as a check number, or what "other" was;
--   * paid_by_tenant_id: which tenant on the lease actually paid (useful when
--     roommates split rent, or only one of them pays);
--   * paid_by_name: someone who isn't a tenant on the lease (a subtenant,
--     a parent, a housing agency...);
--   * for_month: which month's rent this payment is for (first of month).
--
-- Safe to re-run. Apply as the database owner (postgres):
--   psql -U postgres -d property_platform -1 -v ON_ERROR_STOP=1 -f migration_011_payment_details.sql
-- ============================================================

ALTER TABLE rent_receipts DROP CONSTRAINT IF EXISTS rent_receipts_method_check;
ALTER TABLE rent_receipts DROP CONSTRAINT IF EXISTS chk_rent_receipt_method;
ALTER TABLE rent_receipts ADD CONSTRAINT chk_rent_receipt_method
    CHECK (method IN ('check', 'cash', 'zelle', 'venmo', 'bank_transfer', 'card', 'money_order', 'other'));

ALTER TABLE rent_receipts ADD COLUMN IF NOT EXISTS method_detail     VARCHAR(120);
ALTER TABLE rent_receipts ADD COLUMN IF NOT EXISTS paid_by_tenant_id UUID REFERENCES tenants(id);
ALTER TABLE rent_receipts ADD COLUMN IF NOT EXISTS paid_by_name      VARCHAR(120);
ALTER TABLE rent_receipts ADD COLUMN IF NOT EXISTS for_month         DATE;

ALTER TABLE rent_receipts DROP CONSTRAINT IF EXISTS chk_rent_receipt_for_month;
ALTER TABLE rent_receipts ADD CONSTRAINT chk_rent_receipt_for_month
    CHECK (for_month IS NULL OR EXTRACT(DAY FROM for_month) = 1);

CREATE INDEX IF NOT EXISTS idx_rent_receipts_paid_by ON rent_receipts(paid_by_tenant_id);
