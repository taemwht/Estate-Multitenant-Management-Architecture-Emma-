import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..audit import write_audit_log
from ..database import get_db, super_admin_session
from ..security import hash_password
from ..deps import require_roles, get_actor_type
from ..models import Tenant, User
from ..schemas import TenantCreate, TenantUpdate, TenantOut, TenantLoginCreate
from ..scoping import STAFF_AND_TENANT_ROLES, tenant_scope_for

router = APIRouter(prefix="/tenants", tags=["tenants"])

# INFERRED, not stated in the PRD: the Roles & Permissions table (PRD
# section 3) never lists who can add/edit tenants — only rental units,
# maintenance, contractors, etc. Using the same roles as rental units,
# since tenant records are the same kind of administrative data. Flag if
# this should be different (e.g. if tenants should be able to self-edit
# their own contact info once tenant login/portal exists).
WRITE_ROLES = ("company_admin", "staff")


@router.post("", response_model=TenantOut, status_code=status.HTTP_201_CREATED)
def create_tenant(
    body: TenantCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*WRITE_ROLES)),
    actor_type: str = Depends(get_actor_type),
):
    tenant = Tenant(
        id=uuid.uuid4(),
        company_id=current_user.company_id,
        **body.model_dump(),
    )
    db.add(tenant)
    db.flush()

    write_audit_log(
        db,
        company_id=current_user.company_id,
        actor_id=current_user.id,
        actor_type=actor_type,
        action="create",
        entity_type="tenant",
        entity_id=tenant.id,
        after_state=body.model_dump(),
    )

    result = TenantOut.model_validate(tenant)
    db.commit()
    return result


@router.get("", response_model=list[TenantOut])
def list_tenants(
    name: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*STAFF_AND_TENANT_ROLES)),
):
    query = db.query(Tenant).filter(Tenant.is_deleted.is_(False))
    scope = tenant_scope_for(db, current_user)
    if scope is not None:
        # A tenant sees only their own record, not their neighbours'.
        if scope.tenant_id is None:
            return []
        query = query.filter(Tenant.id == scope.tenant_id)
    if name:
        query = query.filter(func.lower(func.trim(Tenant.name)).contains(name.strip().lower()))
    return query.order_by(Tenant.name).all()


@router.get("/{tenant_id}", response_model=TenantOut)
def get_tenant(
    tenant_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*STAFF_AND_TENANT_ROLES)),
):
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    scope = tenant_scope_for(db, current_user)
    if not tenant or (scope is not None and tenant.id != scope.tenant_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    return tenant


@router.patch("/{tenant_id}", response_model=TenantOut)
def update_tenant(
    tenant_id: uuid.UUID,
    body: TenantUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*WRITE_ROLES)),
    actor_type: str = Depends(get_actor_type),
):
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    before = TenantOut.model_validate(tenant).model_dump(mode="json")
    changes = body.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(tenant, field, value)
    db.flush()

    write_audit_log(
        db,
        company_id=current_user.company_id,
        actor_id=current_user.id,
        actor_type=actor_type,
        action="update",
        entity_type="tenant",
        entity_id=tenant.id,
        before_state=before,
        after_state=changes,
    )

    result = TenantOut.model_validate(tenant)
    db.commit()
    return result


@router.delete("/{tenant_id}", status_code=status.HTTP_204_NO_CONTENT)
def soft_delete_tenant(
    tenant_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*WRITE_ROLES)),
    actor_type: str = Depends(get_actor_type),
):
    """
    NOTE: unlike rental units, there's no active-lease-style block here.
    The PRD doesn't specify one for tenants, and it's not obvious one is
    warranted — a tenant who's moved out but whose lease record you still
    want to keep is a normal case, not an error state. Soft-delete just
    hides them from default listings.
    """
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    tenant.is_deleted = True
    db.flush()

    write_audit_log(
        db,
        company_id=current_user.company_id,
        actor_id=current_user.id,
        actor_type=actor_type,
        action="soft_delete",
        entity_type="tenant",
        entity_id=tenant.id,
    )
    db.commit()


@router.post("/{tenant_id}/restore", response_model=TenantOut)
def restore_tenant(
    tenant_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*WRITE_ROLES)),
    actor_type: str = Depends(get_actor_type),
):
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    if not tenant.is_deleted:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Tenant is not deleted")

    tenant.is_deleted = False
    db.flush()

    write_audit_log(
        db,
        company_id=current_user.company_id,
        actor_id=current_user.id,
        actor_type=actor_type,
        action="restore",
        entity_type="tenant",
        entity_id=tenant.id,
    )

    result = TenantOut.model_validate(tenant)
    db.commit()
    return result


@router.post("/{tenant_id}/login", response_model=TenantOut, status_code=status.HTTP_201_CREATED)
def create_tenant_login(
    tenant_id: uuid.UUID,
    body: TenantLoginCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*WRITE_ROLES)),
    actor_type: str = Depends(get_actor_type),
):
    """Give a tenant record a portal login (a `tenant`-role user in the
    same company, linked through tenants.user_id). The tenant then signs
    in with /auth/login and only sees their own lease data."""
    if len(body.password) < 8:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                             detail="Password must be at least 8 characters")
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id, Tenant.is_deleted.is_(False)).first()
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    if tenant.user_id is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This tenant already has a login")

    # Emails are unique across ALL companies, so the duplicate check has to
    # look past RLS. It only reveals "taken or not", same as /signup.
    with super_admin_session(db, company_id=str(current_user.company_id)):
        taken = db.query(User.id).filter(User.email == body.email).first()
    if taken:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    user = User(
        id=uuid.uuid4(),
        company_id=current_user.company_id,
        role="tenant",
        email=body.email,
        password_hash=hash_password(body.password),
    )
    db.add(user)
    db.flush()
    tenant.user_id = user.id
    db.flush()

    write_audit_log(
        db, company_id=current_user.company_id, actor_id=current_user.id,
        actor_type=actor_type, action="create_login", entity_type="tenant",
        entity_id=tenant.id, after_state={"email": body.email},
    )

    result = TenantOut.model_validate(tenant)
    db.commit()
    return result
