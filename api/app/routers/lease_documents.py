"""
Signed lease PDFs.

  GET    /lease-documents                          every document I can see
  POST   /leases/{lease_id}/documents              upload a PDF (staff/admin)
  GET    /leases/{lease_id}/documents/{id}/file    open it (anyone who can see the lease)
  POST   /leases/{lease_id}/documents/{id}/link    a 2-minute link that opens it in a browser tab
  GET    /lease-documents/open?t=...               where that link points
  DELETE /leases/{lease_id}/documents/{id}         remove it (admin; soft delete)

Files live on disk under FILES_DIR/leases/<company>/<random>.pdf, never in a
public place: the only way to read one is this API with a valid login, and
a tenant only ever gets their own lease's files.
"""
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from jose import JWTError, jwt
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..audit import write_audit_log
from ..config import settings
from ..database import get_db, set_rls_context
from ..deps import get_actor_type, require_roles
from ..models import Lease, LeaseDocument, User
from ..scoping import ADMIN_ROLES, STAFF_AND_TENANT_ROLES, ensure_lease_visible, tenant_scope_for

router = APIRouter(tags=["lease-documents"])
WRITE_ROLES = ("company_admin", "staff")
MAX_BYTES = 20 * 1024 * 1024


class LeaseDocumentOut(BaseModel):
    id: uuid.UUID
    lease_id: uuid.UUID
    filename: str
    size_bytes: int
    uploaded_at: datetime
    uploaded_by: Optional[uuid.UUID]

    class Config:
        from_attributes = True


def _path(doc: LeaseDocument) -> str:
    return os.path.join(settings.files_dir, "leases", str(doc.company_id), doc.stored_name)


def _lease(db: Session, lease_id, user: User) -> Lease:
    lease = db.query(Lease).filter(Lease.id == lease_id).first()
    if not lease:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lease not found")
    ensure_lease_visible(tenant_scope_for(db, user), lease.id, "Lease not found")
    return lease


def _doc(db: Session, lease_id, doc_id) -> LeaseDocument:
    doc = (db.query(LeaseDocument)
           .filter(LeaseDocument.id == doc_id, LeaseDocument.lease_id == lease_id,
                   LeaseDocument.is_deleted.is_(False)).first())
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return doc


@router.get("/lease-documents", response_model=list[LeaseDocumentOut])
def list_documents(db: Session = Depends(get_db),
                   current_user: User = Depends(require_roles(*STAFF_AND_TENANT_ROLES))):
    q = db.query(LeaseDocument).filter(LeaseDocument.is_deleted.is_(False))
    scope = tenant_scope_for(db, current_user)
    if scope is not None:
        if not scope.lease_ids:
            return []
        q = q.filter(LeaseDocument.lease_id.in_(scope.lease_ids))
    return q.order_by(LeaseDocument.uploaded_at.desc()).all()


@router.post("/leases/{lease_id}/documents", response_model=LeaseDocumentOut, status_code=status.HTTP_201_CREATED)
async def upload_document(
    lease_id: uuid.UUID,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*WRITE_ROLES)),
    actor_type: str = Depends(get_actor_type),
):
    lease = _lease(db, lease_id, current_user)
    data = await file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="PDF is larger than 20 MB.")
    if not data.startswith(b"%PDF-"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="That file isn't a PDF.")
    name = os.path.basename(file.filename or "lease.pdf").strip()[:200] or "lease.pdf"
    if not name.lower().endswith(".pdf"):
        name += ".pdf"
    doc = LeaseDocument(id=uuid.uuid4(), company_id=lease.company_id, lease_id=lease.id, filename=name,
                        stored_name=f"{uuid.uuid4().hex}.pdf", size_bytes=len(data), uploaded_by=current_user.id)
    path = _path(doc)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)
    try:
        db.add(doc)
        db.flush()
        write_audit_log(db, company_id=lease.company_id, actor_id=current_user.id, actor_type=actor_type,
                        action="create", entity_type="lease_document", entity_id=doc.id,
                        after_state={"lease_id": str(lease.id), "filename": name, "size_bytes": len(data)})
        result = LeaseDocumentOut.model_validate(doc)
        db.commit()
    except Exception:
        os.remove(path)
        raise
    return result


@router.get("/leases/{lease_id}/documents/{doc_id}/file")
def open_document(lease_id: uuid.UUID, doc_id: uuid.UUID, db: Session = Depends(get_db),
                  current_user: User = Depends(require_roles(*STAFF_AND_TENANT_ROLES))):
    _lease(db, lease_id, current_user)
    return _serve(_doc(db, lease_id, doc_id))


def _serve(doc: LeaseDocument):
    path = _path(doc)
    if not os.path.exists(path):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="The file is missing on the server.")
    return FileResponse(path, media_type="application/pdf", filename=doc.filename,
                        content_disposition_type="inline",
                        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})


LINK_SECONDS = 120


@router.post("/leases/{lease_id}/documents/{doc_id}/link")
def document_link(lease_id: uuid.UUID, doc_id: uuid.UUID, db: Session = Depends(get_db),
                  current_user: User = Depends(require_roles(*STAFF_AND_TENANT_ROLES))):
    """A browser tab can't send the login header, so after the normal access
    check we hand out a link that works for this one file for 2 minutes."""
    _lease(db, lease_id, current_user)
    doc = _doc(db, lease_id, doc_id)
    token = jwt.encode({"type": "doc_link", "sub": str(current_user.id), "doc": str(doc.id),
                        "co": str(doc.company_id),
                        "exp": datetime.now(timezone.utc) + timedelta(seconds=LINK_SECONDS)},
                       settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return {"url": f"lease-documents/open?t={token}", "expires_in": LINK_SECONDS}


@router.get("/lease-documents/open")
def open_by_link(t: str, db: Session = Depends(get_db)):
    try:
        claims = jwt.decode(t, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This link has expired. Open the lease again from EMMA.")
    if claims.get("type") != "doc_link":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a document link.")
    # The link was issued after a full access check; scope this lookup to
    # the document's own company so RLS still applies.
    set_rls_context(db, company_id=claims["co"], is_super_admin=False)
    doc = db.query(LeaseDocument).filter(LeaseDocument.id == claims["doc"], LeaseDocument.is_deleted.is_(False)).first()
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return _serve(doc)


@router.delete("/leases/{lease_id}/documents/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(lease_id: uuid.UUID, doc_id: uuid.UUID, db: Session = Depends(get_db),
                    current_user: User = Depends(require_roles(*ADMIN_ROLES)),
                    actor_type: str = Depends(get_actor_type)):
    _lease(db, lease_id, current_user)
    doc = _doc(db, lease_id, doc_id)
    doc.is_deleted = True   # the file stays on disk so it can be restored
    db.flush()
    write_audit_log(db, company_id=doc.company_id, actor_id=current_user.id, actor_type=actor_type,
                    action="soft_delete", entity_type="lease_document", entity_id=doc.id)
    db.commit()
