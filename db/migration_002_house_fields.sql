-- Migration 002: add fields carried over from the old house_crud skill's
-- `houses` table (year_built, bedrooms, bathrooms, notes), plus a separate
-- occupancy_status column distinct from the existing active/deleted
-- `status` column. Run once against your existing property_platform DB —
-- safe to run as postgres superuser (RLS doesn't restrict DDL).
--
--   psql -U postgres -d property_platform -f migration_002_house_fields.sql

ALTER TABLE rental_units
    ADD COLUMN IF NOT EXISTS year_built INTEGER,
    ADD COLUMN IF NOT EXISTS bedrooms INTEGER,
    ADD COLUMN IF NOT EXISTS bathrooms NUMERIC(3, 1),
    ADD COLUMN IF NOT EXISTS notes TEXT,
    ADD COLUMN IF NOT EXISTS occupancy_status VARCHAR(50);
