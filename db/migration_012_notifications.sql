-- ============================================================
-- Migration 012: notifications (website bell + Telegram)
-- ============================================================
-- One row per message to one person, e.g. "New job assigned" to a
-- contractor. read_at is set when they open it (website or Telegram), so
-- the company that sent it can see "Read" / "Unread" and ping again.
--
-- Visibility: the recipient sees their own rows; the sending company can
-- see rows it sent (for read receipts). Only the recipient may mark a row
-- read; the API enforces that.
--
-- Safe to re-run. Apply as the database owner (postgres):
--   psql -U postgres -d property_platform -1 -v ON_ERROR_STOP=1 -f migration_012_notifications.sql
-- ============================================================

CREATE TABLE IF NOT EXISTS notifications (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id           UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,   -- recipient
    company_id        UUID REFERENCES companies(id),                          -- sender company
    created_by        UUID REFERENCES users(id),
    kind              VARCHAR(30) NOT NULL,         -- job_assigned, job_rescheduled, job_reminder
    title             VARCHAR(200) NOT NULL,
    body              TEXT,
    entity_type       VARCHAR(40),
    entity_id         UUID,
    link_tab          VARCHAR(30),                  -- which website tab to open
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    read_at           TIMESTAMPTZ,
    telegram_status   VARCHAR(20),                  -- NULL = not tried yet, sent, not_linked, failed
    followup_sent_at  TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_notifications_user_unread ON notifications(user_id, read_at);
CREATE INDEX IF NOT EXISTS idx_notifications_entity ON notifications(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_notifications_telegram ON notifications(telegram_status) WHERE telegram_status IS NULL;

ALTER TABLE notifications ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS notification_access ON notifications;
CREATE POLICY notification_access ON notifications
    USING (is_super_admin() OR user_id = current_user_id() OR company_id = current_company_id())
    WITH CHECK (is_super_admin() OR user_id = current_user_id() OR company_id = current_company_id());

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_platform') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON notifications TO app_platform;
    END IF;
END $$;
