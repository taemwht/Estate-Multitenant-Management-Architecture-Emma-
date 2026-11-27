-- ============================================================
-- Migration 016: more details on a rental unit
-- ============================================================
-- Size, floor, parking, laundry, pets, furnished, utilities included and
-- the asking (market) rent, so a unit record describes the actual home.
--
-- Safe to re-run. Apply as the database owner (postgres):
--   psql -U postgres -d property_platform -1 -v ON_ERROR_STOP=1 -f migration_016_unit_details.sql
-- ============================================================

ALTER TABLE rental_units ADD COLUMN IF NOT EXISTS square_feet        INTEGER;
ALTER TABLE rental_units ADD COLUMN IF NOT EXISTS floor              VARCHAR(20);
ALTER TABLE rental_units ADD COLUMN IF NOT EXISTS parking            VARCHAR(100);
ALTER TABLE rental_units ADD COLUMN IF NOT EXISTS laundry            VARCHAR(30);
ALTER TABLE rental_units ADD COLUMN IF NOT EXISTS pets_allowed       BOOLEAN;
ALTER TABLE rental_units ADD COLUMN IF NOT EXISTS furnished          BOOLEAN;
ALTER TABLE rental_units ADD COLUMN IF NOT EXISTS utilities_included VARCHAR(255);
ALTER TABLE rental_units ADD COLUMN IF NOT EXISTS market_rent        NUMERIC(10, 2);

ALTER TABLE rental_units DROP CONSTRAINT IF EXISTS chk_unit_square_feet;
ALTER TABLE rental_units ADD CONSTRAINT chk_unit_square_feet CHECK (square_feet IS NULL OR square_feet > 0);
ALTER TABLE rental_units DROP CONSTRAINT IF EXISTS chk_unit_market_rent;
ALTER TABLE rental_units ADD CONSTRAINT chk_unit_market_rent CHECK (market_rent IS NULL OR market_rent >= 0);
