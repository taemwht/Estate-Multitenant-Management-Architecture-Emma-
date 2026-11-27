-- ============================================================
-- Migration 009: sign in with a username instead of an email
-- ============================================================
-- Adds users.username (unique, case-insensitive), fills it in for every
-- existing account from the part of the email before the "@" (adding
-- -2, -3 ... when two accounts would clash), and makes email optional.
-- Email login keeps working for accounts that have one (EMMA's skills
-- sign in that way).
--
-- Safe to re-run. Apply as the database owner (postgres):
--   psql -U postgres -d property_platform -1 -v ON_ERROR_STOP=1 -f migration_009_usernames.sql
-- ============================================================

ALTER TABLE users ADD COLUMN IF NOT EXISTS username VARCHAR(50);

-- Backfill: lowercase local part of the email, cleaned to the allowed
-- characters, de-duplicated with a numeric suffix.
WITH base AS (
    SELECT id,
           COALESCE(NULLIF(regexp_replace(lower(split_part(email, '@', 1)), '[^a-z0-9._-]', '', 'g'), ''), 'user') AS b,
           created_at
    FROM users
    WHERE username IS NULL
),
numbered AS (
    SELECT id, b,
           row_number() OVER (PARTITION BY b ORDER BY created_at, id) AS n
    FROM base
)
UPDATE users u
SET username = CASE WHEN n = 1 AND NOT EXISTS (
                        SELECT 1 FROM users x WHERE lower(x.username) = numbered.b)
                    THEN left(numbered.b, 50)
                    ELSE left(numbered.b, 44) || '-' || n END
FROM numbered
WHERE u.id = numbered.id;

ALTER TABLE users ALTER COLUMN username SET NOT NULL;
ALTER TABLE users ALTER COLUMN email DROP NOT NULL;

ALTER TABLE users DROP CONSTRAINT IF EXISTS chk_username_format;
ALTER TABLE users ADD CONSTRAINT chk_username_format
    CHECK (username ~ '^[a-z0-9][a-z0-9._-]{2,49}$');

CREATE UNIQUE INDEX IF NOT EXISTS uq_users_username ON users (lower(username));
