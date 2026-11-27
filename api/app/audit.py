import uuid
from typing import Optional

from sqlalchemy.orm import Session

from .models import AuditLog


def write_audit_log(
    db: Session,
    *,
    company_id: Optional[uuid.UUID],
    actor_id: Optional[uuid.UUID],
    actor_type: str,  # "user" or "hermes"
    action: str,      # e.g. "create", "update", "soft_delete"
    entity_type: str,  # e.g. "rental_unit"
    entity_id: Optional[uuid.UUID],
    before_state: Optional[dict] = None,
    after_state: Optional[dict] = None,
) -> None:
    """
    Writes one audit_log row. Call this in the SAME transaction as the
    write it's logging (don't commit separately) — if the write rolls
    back, the audit entry should roll back with it, not record an
    action that never actually happened.
    """
    db.add(AuditLog(
        id=uuid.uuid4(),
        company_id=company_id,
        actor_id=actor_id,
        actor_type=actor_type,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        before_state=before_state,
        after_state=after_state,
    ))
