"""
Runs as a system-level job, not on behalf of any one company's request —
that's why it uses super_admin_session/set_rls_context directly rather
than depending on a logged-in user's session like every other write in
this app does.
"""
import logging
from datetime import date, timedelta

from apscheduler.schedulers.background import BackgroundScheduler

from .database import SessionLocal, set_rls_context
from .models import AnnualCheckin

logger = logging.getLogger("reminders")

REMINDER_WINDOW_DAYS = 30  # start reminding this many days before due_date


def send_reminder_stub(checkin: AnnualCheckin) -> None:
    """
    STUB — no email/SMS provider has been chosen yet (open PRD item).
    This logs what WOULD be sent so the rest of the pipeline (finding
    who needs a reminder, tracking reminder_count) is real and testable
    tonight even though actual delivery isn't wired up. Replace the body
    of this function with a real provider call once one's picked —
    everything calling it stays the same.
    """
    logger.info(
        "[REMINDER STUB] Would notify tenant(s) on lease %s about %s check-in "
        "due %s (reminder #%d)",
        checkin.lease_id, checkin.hazard_type, checkin.due_date, checkin.reminder_count + 1,
    )


def run_reminder_sweep(company_id: str | None = None) -> int:
    """Returns the number of check-ins reminded, mainly for testing/logging.

    company_id=None (the daily job, or a super_admin trigger) sweeps every
    company. With a company_id it runs under that company's normal RLS
    scope, so a company admin's manual trigger can't touch other
    companies' reminder counts."""
    db = SessionLocal()
    count = 0
    try:
        if company_id is None:
            set_rls_context(db, company_id=None, is_super_admin=True)
        else:
            set_rls_context(db, company_id=company_id, is_super_admin=False)
        cutoff = date.today() + timedelta(days=REMINDER_WINDOW_DAYS)
        due_soon = (
            db.query(AnnualCheckin)
            .filter(AnnualCheckin.acknowledged_at.is_(None))
            .filter(AnnualCheckin.due_date <= cutoff)
            .all()
        )
        for checkin in due_soon:
            send_reminder_stub(checkin)
            checkin.reminder_count += 1
            count += 1
        db.commit()
    finally:
        db.close()
    logger.info("Reminder sweep complete: %d check-in(s) reminded.", count)
    return count


_scheduler = BackgroundScheduler()


def start_scheduler() -> None:
    # Daily at 8am SERVER time — no timezone pinned here, worth revisiting
    # once this runs somewhere other than a dev machine.
    _scheduler.add_job(run_reminder_sweep, "cron", hour=8, minute=0, id="annual_checkin_reminders")
    # Unread job notifications get one automatic follow-up (notify.py).
    from .notify import followup_sweep
    _scheduler.add_job(followup_sweep, "interval", minutes=15, id="notification_followups")
    _scheduler.start()


def stop_scheduler() -> None:
    _scheduler.shutdown(wait=False)
