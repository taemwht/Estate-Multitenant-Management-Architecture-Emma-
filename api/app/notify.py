"""
Notifications: a message to one person, shown under the bell on the
website and (if they've linked Telegram) sent by the bot with a
"Mark as read" button. Reading it in either place sets read_at, which
the sending company sees as a read receipt.

Today they're sent when a contractor is assigned a job, when the job's
date changes, and as a follow-up ping (automatic after FOLLOWUP_HOURS
unread, or on demand from the Maintenance page).
"""
import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy.orm import Session

from .database import SessionLocal, set_rls_context
from .models import Company, Contractor, MaintenanceRequest, Notification, RentalUnit

log = logging.getLogger("emma.notify")

FOLLOWUP_HOURS = 24
DONE = ("Completed", "Verified", "Cancelled")


def _job_text(db: Session, req: MaintenanceRequest) -> str:
    unit = db.query(RentalUnit).filter(RentalUnit.id == req.rental_unit_id).first()
    company = db.query(Company).filter(Company.id == req.company_id).first()
    where = ", ".join(x for x in [unit and unit.address_line1, unit and unit.unit_reference] if x) or "Unit"
    d = req.scheduled_date
    if isinstance(d, str):
        d = date.fromisoformat(d)
    when = d.strftime("%a %b %d, %Y").replace(" 0", " ") if d else "date to be confirmed"
    parts = [company.name if company else None, where, f"Priority: {req.priority}", f"Scheduled: {when}"]
    return " · ".join(p for p in parts if p)


def notify_job(db: Session, req: MaintenanceRequest, kind: str, sender_id=None) -> Notification | None:
    """Queue a job notification for the assigned contractor's login.
    Returns None if nobody is assigned or the contractor has no login."""
    if req.assigned_contractor_id is None:
        return None
    contractor = db.query(Contractor).filter(Contractor.id == req.assigned_contractor_id).first()
    if contractor is None or contractor.user_id is None:
        return None
    what = (req.description or "Maintenance job").strip()
    title = {
        "job_assigned": "New job: ",
        "job_rescheduled": "Job date changed: ",
        "job_reminder": "Reminder, please check: ",
    }.get(kind, "") + (what[:150] + ("…" if len(what) > 150 else ""))
    n = Notification(user_id=contractor.user_id, company_id=req.company_id, created_by=sender_id,
                     kind=kind, title=title, body=_job_text(db, req),
                     entity_type="maintenance_request", entity_id=req.id, link_tab="jobs")
    db.add(n)
    db.flush()
    return n


def followup_sweep() -> int:
    """Scheduler job: one automatic reminder for job notifications still
    unread after FOLLOWUP_HOURS, if the job is still open and still theirs."""
    db = SessionLocal()
    sent = 0
    try:
        set_rls_context(db, company_id=None, is_super_admin=True)
        cutoff = datetime.now(timezone.utc) - timedelta(hours=FOLLOWUP_HOURS)
        stale = (
            db.query(Notification)
            .filter(Notification.kind.in_(("job_assigned", "job_rescheduled")),
                    Notification.read_at.is_(None), Notification.followup_sent_at.is_(None),
                    Notification.created_at < cutoff)
            .all()
        )
        for n in stale:
            n.followup_sent_at = datetime.now(timezone.utc)
            req = db.query(MaintenanceRequest).filter(MaintenanceRequest.id == n.entity_id).first()
            if not req or req.is_deleted or req.status in DONE:
                continue
            contractor = db.query(Contractor).filter(Contractor.id == req.assigned_contractor_id).first()
            if not contractor or contractor.user_id != n.user_id:
                continue
            if notify_job(db, req, "job_reminder"):
                sent += 1
        db.commit()
    except Exception:
        log.exception("follow-up sweep failed")
        db.rollback()
    finally:
        db.close()
    if sent:
        log.warning("Sent %d follow-up reminder(s)", sent)
    return sent


# ---- used by the Telegram bot (it has no signed-in user) ---------------

def telegram_outbox(limit: int = 20) -> list[dict]:
    """Recent notifications not yet tried on Telegram."""
    db = SessionLocal()
    try:
        set_rls_context(db, company_id=None, is_super_admin=True)
        since = datetime.now(timezone.utc) - timedelta(days=2)
        rows = (db.query(Notification)
                .filter(Notification.telegram_status.is_(None), Notification.created_at > since)
                .order_by(Notification.created_at).limit(limit).all())
        return [{"id": str(n.id), "user_id": str(n.user_id), "kind": n.kind, "title": n.title,
                 "body": n.body, "read": n.read_at is not None} for n in rows]
    finally:
        db.close()


def set_telegram_status(notification_id: str, value: str) -> None:
    db = SessionLocal()
    try:
        set_rls_context(db, company_id=None, is_super_admin=True)
        db.query(Notification).filter(Notification.id == notification_id).update({Notification.telegram_status: value})
        db.commit()
    finally:
        db.close()


def mark_read_as(notification_id: str, user_id: str) -> bool:
    """Marks a notification (and the same person's other unread ones about
    the same job) read, but only if it belongs to user_id."""
    db = SessionLocal()
    try:
        set_rls_context(db, company_id=None, is_super_admin=True)
        n = db.query(Notification).filter(Notification.id == notification_id,
                                          Notification.user_id == user_id).first()
        if n is None:
            return False
        mark_read(db, n)
        db.commit()
        return True
    finally:
        db.close()


def mark_read(db: Session, n: Notification) -> None:
    now = datetime.now(timezone.utc)
    q = db.query(Notification).filter(Notification.user_id == n.user_id, Notification.read_at.is_(None))
    if n.entity_id is not None:
        q = q.filter(Notification.entity_id == n.entity_id)
    else:
        q = q.filter(Notification.id == n.id)
    q.update({Notification.read_at: now}, synchronize_session=False)
