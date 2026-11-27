"""
The bell on the website.

  GET  /notifications              my notifications (newest first)
  GET  /notifications/unread-count
  POST /notifications/{id}/read    mark one read (and others about the same job)
  POST /notifications/read-all
  GET  /notifications/delivery     staff/admin: read receipts for what my company sent
"""
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user, require_roles
from ..models import Notification, User
from ..notify import mark_read

router = APIRouter(prefix="/notifications", tags=["notifications"])
MANAGE_ROLES = ("company_admin", "staff")


class NotificationOut(BaseModel):
    id: uuid.UUID
    kind: str
    title: str
    body: Optional[str]
    entity_type: Optional[str]
    entity_id: Optional[uuid.UUID]
    link_tab: Optional[str]
    created_at: datetime
    read_at: Optional[datetime]

    class Config:
        from_attributes = True


class DeliveryOut(BaseModel):
    entity_id: uuid.UUID
    user_id: uuid.UUID
    kind: str
    sent_at: datetime
    read_at: Optional[datetime]
    telegram_status: Optional[str]
    pings: int


@router.get("", response_model=list[NotificationOut])
def my_notifications(limit: int = 30, db: Session = Depends(get_db),
                     current_user: User = Depends(get_current_user)):
    return (db.query(Notification).filter(Notification.user_id == current_user.id)
            .order_by(Notification.created_at.desc()).limit(min(max(limit, 1), 100)).all())


@router.get("/unread-count")
def unread_count(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    n = (db.query(func.count(Notification.id))
         .filter(Notification.user_id == current_user.id, Notification.read_at.is_(None)).scalar())
    return {"unread": n}


@router.post("/{notification_id}/read", response_model=NotificationOut)
def read_one(notification_id: uuid.UUID, db: Session = Depends(get_db),
             current_user: User = Depends(get_current_user)):
    # Filter on the recipient: the sending company can SEE the row (RLS)
    # but must not be able to mark it read on the contractor's behalf.
    n = db.query(Notification).filter(Notification.id == notification_id,
                                      Notification.user_id == current_user.id).first()
    if n is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")
    mark_read(db, n)
    db.flush()
    db.refresh(n)          # still inside the request's RLS context
    result = NotificationOut.model_validate(n)
    db.commit()
    return result


@router.post("/read-all")
def read_all(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    n = (db.query(Notification)
         .filter(Notification.user_id == current_user.id, Notification.read_at.is_(None))
         .update({Notification.read_at: func.now()}, synchronize_session=False))
    db.commit()
    return {"marked": n}


@router.get("/delivery", response_model=list[DeliveryOut])
def delivery(entity_type: str = "maintenance_request", db: Session = Depends(get_db),
             current_user: User = Depends(require_roles(*MANAGE_ROLES))):
    """Latest notification my company sent about each job, with read
    status. A ping counts as read once any notice about that job is read."""
    rows = (db.query(Notification)
            .filter(Notification.company_id == current_user.company_id,
                    Notification.entity_type == entity_type)
            .order_by(Notification.created_at.desc()).all())
    out: dict = {}
    for n in rows:
        key = (n.entity_id, n.user_id)
        d = out.get(key)
        if d is None:
            out[key] = d = DeliveryOut(entity_id=n.entity_id, user_id=n.user_id, kind=n.kind,
                                       sent_at=n.created_at, read_at=n.read_at,
                                       telegram_status=n.telegram_status, pings=0)
        if n.kind == "job_reminder":
            d.pings += 1
    # newest assignment per job only (a reassigned job shows the new contractor)
    latest: dict = {}
    for d in out.values():
        if d.entity_id not in latest or d.sent_at > latest[d.entity_id].sent_at:
            latest[d.entity_id] = d
    return list(latest.values())
