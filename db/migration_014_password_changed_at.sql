-- ============================================================
-- Migration 014: sign out everywhere when a password is changed
-- ============================================================
-- The API stamps password_changed_at whenever a password is set by the
-- super admin, and rejects any login token issued before that moment.
-- So a reset password also ends every session that used the old one.
--
-- Safe to re-run. Apply as the database owner (postgres):
--   psql -U postgres -d property_platform -1 -v ON_ERROR_STOP=1 -f migration_014_password_changed_at.sql
-- ============================================================

ALTER TABLE users ADD COLUMN IF NOT EXISTS password_changed_at TIMESTAMPTZ;
