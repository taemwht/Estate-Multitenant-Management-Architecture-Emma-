import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..audit import write_audit_log
from ..database import get_db
from ..deps import require_roles, get_actor_type
from ..models import RentalUnit, Lease, User
from ..schemas import RentalUnitCreate, RentalUnitUpdate, RentalUnitOut
from ..scoping import STAFF_AND_TENANT_ROLES, tenant_scope_for

router = APIRouter(prefix="/rental-units", tags=["rental-units"])

# NOTE: super_admin creating/editing units on behalf of a specific
# company isn't handled here yet — this endpoint assumes the caller
# has their own company_id (company_admin/staff always do; super_admin
# doesn't). Flagging as a known gap rather than guessing at a design
# for it, same as the other cross-company edge cases noted so far.
WRITE_ROLES = ("company_admin", "staff")


@router.post("", response_model=RentalUnitOut, status_code=status.HTTP_201_CREATED)
def create_rental_unit(
    body: RentalUnitCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*WRITE_ROLES)),
    actor_type: str = Depends(get_actor_type),
):
    existing = (
        db.query(RentalUnit)
        .filter(RentalUnit.company_id == current_user.company_id,
                RentalUnit.unit_reference == body.unit_reference)
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"unit_reference '{body.unit_reference}' already exists for this company",
        )

    unit = RentalUnit(
        id=uuid.uuid4(),
        company_id=current_user.company_id,
        **body.model_dump(),
    )
    db.add(unit)
    db.flush()  # populate defaults (status, timestamps) before we read them below

    write_audit_log(
        db,
        company_id=current_user.company_id,
        actor_id=current_user.id,
        actor_type=actor_type,
        action="create",
        entity_type="rental_unit",
        entity_id=unit.id,
        after_state=body.model_dump(),
    )

    # Read everything we need BEFORE commit — see create_first_admin.py
    # for why: post-commit attribute access re-triggers a SELECT outside
    # this transaction's RLS context and would incorrectly appear empty.
    result = RentalUnitOut.model_validate(unit)
    db.commit()
    return result


@router.get("", response_model=list[RentalUnitOut])
def list_rental_units(
    unit_reference: str | None = None,
    address_line1: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*STAFF_AND_TENANT_ROLES)),
):
    # RLS scopes this to current_user's company. Tenants additionally
    # only see the units they currently rent.
    query = db.query(RentalUnit).filter(RentalUnit.is_deleted.is_(False))
    scope = tenant_scope_for(db, current_user)
    if scope is not None:
        if not scope.active_unit_ids:
            return []
        query = query.filter(RentalUnit.id.in_(scope.active_unit_ids))

    # Case-insensitive, trimmed — matches the old house_crud skill's
    # LOWER(TRIM(...)) nickname-lookup behavior, which callers depend on.
    if unit_reference:
        query = query.filter(func.lower(func.trim(RentalUnit.unit_reference))
                              == unit_reference.strip().lower())
    if address_line1:
        query = query.filter(func.lower(func.trim(RentalUnit.address_line1))
                              == address_line1.strip().lower())

    return query.order_by(RentalUnit.unit_reference).all()


@router.get("/{unit_id}", response_model=RentalUnitOut)
def get_rental_unit(
    unit_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*STAFF_AND_TENANT_ROLES)),
):
    unit = db.query(RentalUnit).filter(RentalUnit.id == unit_id).first()
    scope = tenant_scope_for(db, current_user)
    if not unit or (scope is not None and unit.id not in scope.active_unit_ids):
        # RLS makes another company's unit invisible the same way a
        # truly nonexistent id would be — both correctly 404, and we
        # can't (and shouldn't) tell the caller which case it was.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rental unit not found")
    return unit


@router.patch("/{unit_id}", response_model=RentalUnitOut)
def update_rental_unit(
    unit_id: uuid.UUID,
    body: RentalUnitUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*WRITE_ROLES)),
    actor_type: str = Depends(get_actor_type),
):
    unit = db.query(RentalUnit).filter(RentalUnit.id == unit_id).first()
    if not unit:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rental unit not found")

    before = RentalUnitOut.model_validate(unit).model_dump(mode="json")
    changes = body.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(unit, field, value)
    db.flush()

    write_audit_log(
        db,
        company_id=current_user.company_id,
        actor_id=current_user.id,
        actor_type=actor_type,
        action="update",
        entity_type="rental_unit",
        entity_id=unit.id,
        before_state=before,
        after_state=changes,
    )

    result = RentalUnitOut.model_validate(unit)
    db.commit()
    return result


@router.delete("/{unit_id}", status_code=status.HTTP_204_NO_CONTENT)
def soft_delete_rental_unit(
    unit_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*WRITE_ROLES)),
    actor_type: str = Depends(get_actor_type),
):
    unit = db.query(RentalUnit).filter(RentalUnit.id == unit_id).first()
    if not unit:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rental unit not found")

    # PRD workflow 5.2: blocked if an active lease references the unit.
    active_lease = (
        db.query(Lease)
        .filter(Lease.rental_unit_id == unit_id, Lease.status == "active")
        .first()
    )
    if active_lease:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot delete: unit has an active lease. End or transfer the lease first.",
        )

    unit.is_deleted = True
    unit.status = "deleted"
    unit.deleted_at = datetime.now(timezone.utc)
    db.flush()

    write_audit_log(
        db,
        company_id=current_user.company_id,
        actor_id=current_user.id,
        actor_type=actor_type,
        action="soft_delete",
        entity_type="rental_unit",
        entity_id=unit.id,
    )
    db.commit()


@router.post("/{unit_id}/restore", response_model=RentalUnitOut)
def restore_rental_unit(
    unit_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*WRITE_ROLES)),
    actor_type: str = Depends(get_actor_type),
):
    """Undelete — parity with the old skill's restore_house. Not in the
    PRD explicitly, but removing this capability during migration would
    be a silent regression, so it's here."""
    unit = db.query(RentalUnit).filter(RentalUnit.id == unit_id).first()
    if not unit:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rental unit not found")
    if not unit.is_deleted:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unit is not deleted")

    unit.is_deleted = False
    unit.status = "active"
    unit.deleted_at = None
    db.flush()

    write_audit_log(
        db,
        company_id=current_user.company_id,
        actor_id=current_user.id,
        actor_type=actor_type,
        action="restore",
        entity_type="rental_unit",
        entity_id=unit.id,
    )

    result = RentalUnitOut.model_validate(unit)
    db.commit()
    return result
