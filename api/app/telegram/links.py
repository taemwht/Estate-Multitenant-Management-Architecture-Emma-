"""
Linking a Telegram account to an EMMA login.

  GET    /telegram/link        is the bot on, and is my Telegram linked?
  POST   /telegram/link-code   get a one-time code (and a t.me link) to link
  DELETE /telegram/link        unlink my Telegram

The code is single-use, lasts 10 minutes, and lives only in this API
process's memory (the bot runs in the same process). Sending it to the
bot proves the Telegram account belongs to whoever is signed in here.
"""
import secrets
import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import SessionLocal, get_db, super_admin_session
from ..deps import get_current_user
from ..models import TelegramLink, User

router = APIRouter(prefix="/telegram", tags=["telegram"])

CODE_SECONDS = 600
_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"   # no 0/O, 1/I/L
_codes: dict[str, tuple[str, float]] = {}       # code -> (user_id, expires)
bot_state = {"username": None}                  # set by the bot when it starts


class LinkStatus(BaseModel):
    enabled: bool
    linked: bool
    bot_username: Optional[str] = None
    telegram_username: Optional[str] = None


class LinkCode(BaseModel):
    code: str
    bot_username: str
    link: str
    expires_in: int


def _purge():
    now = time.time()
    for c in [c for c, (_, exp) in _codes.items() if exp < now]:
        del _codes[c]


def take_code(code: str) -> Optional[str]:
    """Bot side: swap a code for the user id it was issued to (once)."""
    _purge()
    entry = _codes.pop((code or "").strip().upper(), None)
    return entry[0] if entry else None


# ---- DB helpers used by the bot (it has no signed-in user yet) ----------

def lookup(telegram_user_id: int) -> Optional[dict]:
    """Which live EMMA login is this Telegram account linked to?"""
    db = SessionLocal()
    try:
        with super_admin_session(db):
            row = (
                db.query(TelegramLink, User)
                .join(User, User.id == TelegramLink.user_id)
                .filter(TelegramLink.telegram_user_id == telegram_user_id, User.is_deleted.is_(False))
                .first()
            )
        if row is None:
            return None
        _, user = row
        return {"id": str(user.id), "company_id": str(user.company_id) if user.company_id else None,
                "role": user.role, "username": user.username}
    finally:
        db.close()


def telegram_id_for_user(user_id: str) -> Optional[int]:
    """The Telegram account linked to an EMMA login, if any (private chat id == user id)."""
    db = SessionLocal()
    try:
        with super_admin_session(db):
            row = db.query(TelegramLink).filter(TelegramLink.user_id == user_id).first()
        return row.telegram_user_id if row else None
    finally:
        db.close()


def link(telegram_user_id: int, telegram_username: Optional[str], user_id: str) -> None:
    """Replaces any earlier link for either side."""
    db = SessionLocal()
    try:
        with super_admin_session(db):
            db.query(TelegramLink).filter(
                (TelegramLink.telegram_user_id == telegram_user_id) | (TelegramLink.user_id == user_id)
            ).delete(synchronize_session=False)
            db.add(TelegramLink(telegram_user_id=telegram_user_id, user_id=user_id,
                                telegram_username=(telegram_username or None)))
            db.flush()   # must hit the DB while the bypass is on
        db.commit()
    finally:
        db.close()


def unlink(telegram_user_id: int) -> bool:
    db = SessionLocal()
    try:
        with super_admin_session(db):
            n = db.query(TelegramLink).filter(TelegramLink.telegram_user_id == telegram_user_id).delete()
            db.flush()
        db.commit()
        return n > 0
    finally:
        db.close()


# ---- website side --------------------------------------------------------

@router.get("/link", response_model=LinkStatus)
def link_status(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    row = db.query(TelegramLink).filter(TelegramLink.user_id == current_user.id).first()
    return LinkStatus(enabled=bool(bot_state["username"]), linked=row is not None,
                      bot_username=bot_state["username"],
                      telegram_username=row.telegram_username if row else None)


@router.post("/link-code", response_model=LinkCode)
def new_link_code(current_user: User = Depends(get_current_user)):
    if not bot_state["username"]:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail="The Telegram bot isn't running on this server.")
    _purge()
    for c in [c for c, (uid, _) in _codes.items() if uid == str(current_user.id)]:
        del _codes[c]   # one live code per person
    code = "".join(secrets.choice(_ALPHABET) for _ in range(8))
    _codes[code] = (str(current_user.id), time.time() + CODE_SECONDS)
    bot = bot_state["username"]
    return LinkCode(code=code, bot_username=bot, link=f"https://t.me/{bot}?start={code}",
                    expires_in=CODE_SECONDS)


@router.delete("/link", status_code=status.HTTP_204_NO_CONTENT)
def remove_link(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    # RLS: a person can only see (and so delete) their own link.
    db.query(TelegramLink).filter(TelegramLink.user_id == current_user.id).delete()
    db.commit()
