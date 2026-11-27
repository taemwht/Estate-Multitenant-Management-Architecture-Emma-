-- ============================================================
-- Migration 010: link a Telegram account to an EMMA login
-- ============================================================
-- One row per linked person. The Telegram bot looks up who is writing
-- (telegram_user_id) and then acts as that EMMA login, with exactly
-- that login's role and data. A login can have at most one Telegram
-- account, and a Telegram account at most one login.
--
-- Safe to re-run. Apply as the database owner (postgres):
--   psql -U postgres -d property_platform -1 -v ON_ERROR_STOP=1 -f migration_010_telegram_links.sql
-- ============================================================

CREATE TABLE IF NOT EXISTS telegram_links (
    telegram_user_id  BIGINT PRIMARY KEY,
    user_id           UUID NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    telegram_username VARCHAR(64),
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- A person sees and manages only their own link. The bot looks links up
-- by Telegram id before it knows who is writing, so it uses the API's
-- narrow super-admin bypass for that one lookup.
ALTER TABLE telegram_links ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS own_link ON telegram_links;
CREATE POLICY own_link ON telegram_links
    USING (is_super_admin() OR user_id = current_user_id())
    WITH CHECK (is_super_admin() OR user_id = current_user_id());

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_platform') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON telegram_links TO app_platform;
    END IF;
END $$;
