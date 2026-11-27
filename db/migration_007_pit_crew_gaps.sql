-- Migration 007: pit-crew-crud gaps + trade vocabulary alignment.
--
-- Fixes a REAL BUG, not just a missing field: maintenance-crud's
-- nlp-parsing.md mapped plumbing problems to trade="plumbing", but this
-- system's actual fixed vocabulary (from the real old pit-crew-crud
-- schema, only seen now) uses "plumber". Those never matched — a
-- plumbing complaint would have silently found zero candidates. Fixing
-- existing test data to the correct value before enforcing the
-- constraint going forward.
--
--   psql -U postgres -d property_platform -f migration_007_pit_crew_gaps.sql

UPDATE contractors SET trade = 'plumber' WHERE trade = 'plumbing';
UPDATE contractors SET trade = 'other' WHERE trade IS NULL;

ALTER TABLE contractors
    ADD COLUMN IF NOT EXISTS preferred_payment_method VARCHAR(100),
    ADD COLUMN IF NOT EXISTS notes TEXT;

ALTER TABLE contractors
    ALTER COLUMN trade SET NOT NULL;

ALTER TABLE contractors DROP CONSTRAINT IF EXISTS chk_contractors_trade;
ALTER TABLE contractors
    ADD CONSTRAINT chk_contractors_trade CHECK (
        trade IN (
            'plumber', 'electrician', 'hvac', 'handyman', 'roofer',
            'appliance', 'locksmith', 'pest_control', 'landscaping',
            'general', 'other'
        )
    );
