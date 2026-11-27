"""
CSV bulk import for rental units, upserting by unit_reference (match key
decided back in the original PRD review — flagged as an open item then,
resolved here).

THE HARD PART: partial success. A 200-row file where row 47 has bad data
still needs rows 1-46 and 48-200 to save — one bad row can't be allowed
to wipe out the whole batch. Standard db.commit()/db.rollback() operate
on the WHOLE transaction, so naive error handling (catch exception,
rollback, continue) would roll back every row already processed in this
same transaction, not just the failed one.

The fix: db.begin_nested() opens a SAVEPOINT per row. If that row fails,
only ITS savepoint rolls back — everything before it (including the
ImportBatch row itself and prior successful rows) stays intact in the
outer transaction, which only gets committed once, at the very end.
"""
import csv
import io
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.exc import DataError, IntegrityError
from sqlalchemy.orm import Session

from ..audit import write_audit_log
from ..database import get_db
from ..deps import require_roles, get_actor_type
from ..models import RentalUnit, ImportBatch, User
from ..schemas import ImportResultOut, ImportBatchOut
from ..scoping import STAFF_ROLES, ACCOUNT_VIEW_ROLES, ADMIN_ROLES

logger = logging.getLogger("bulk_import")
router = APIRouter(prefix="/bulk-import", tags=["bulk-import"])
WRITE_ROLES = ("company_admin", "staff")

ALLOWED_FIELDS = {
    "unit_reference", "address_line1", "address_line2", "city", "state",
    "zip_code", "unit_type", "year_built", "bedrooms", "bathrooms",
    "notes", "occupancy_status",
}
INT_FIELDS = {"year_built", "bedrooms"}
FLOAT_FIELDS = {"bathrooms"}


@router.post("/rental-units", response_model=ImportResultOut, status_code=status.HTTP_201_CREATED)
async def bulk_import_rental_units(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*ADMIN_ROLES)),
    actor_type: str = Depends(get_actor_type),
):
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                             detail="Only .csv files are supported right now")

    raw = await file.read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                             detail="File must be UTF-8 encoded text")

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames or "unit_reference" not in reader.fieldnames:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                             detail="CSV must have a 'unit_reference' column")

    batch = ImportBatch(
        id=uuid.uuid4(),
        company_id=current_user.company_id,
        uploaded_by=current_user.id,
        file_name=file.filename,
        status="processing",
    )
    db.add(batch)
    db.flush()

    seen_refs = set()
    errors = []
    succeeded = 0

    for row_number, row in enumerate(reader, start=2):
        ref = (row.get("unit_reference") or "").strip()
        if not ref:
            errors.append({"row_number": row_number, "unit_reference": None,
                            "error": "Missing unit_reference"})
            continue
        if ref in seen_refs:
            errors.append({"row_number": row_number, "unit_reference": ref,
                            "error": "Duplicate unit_reference within this file"})
            continue
        seen_refs.add(ref)

        fields = {}
        row_error = None
        for key, value in row.items():
            if key not in ALLOWED_FIELDS or not value or not value.strip():
                continue
            try:
                if key in INT_FIELDS:
                    fields[key] = int(value)
                elif key in FLOAT_FIELDS:
                    fields[key] = float(value)
                else:
                    fields[key] = value.strip()
            except ValueError:
                row_error = f"Invalid number for '{key}': '{value}'"
                break
        if row_error:
            errors.append({"row_number": row_number, "unit_reference": ref, "error": row_error})
            continue

        existing = (
            db.query(RentalUnit)
            .filter(RentalUnit.company_id == current_user.company_id,
                     RentalUnit.unit_reference == ref)
            .first()
        )
        if existing is not None and existing.is_deleted:
            # Updating it would report success while the unit stays
            # hidden. Make the caller restore it on purpose instead.
            errors.append({
                "row_number": row_number, "unit_reference": ref,
                "error": f"unit_reference '{ref}' belongs to a deleted unit; restore it "
                         f"(POST /rental-units/{existing.id}/restore) and re-import",
            })
            continue

        try:
            with db.begin_nested():
                if existing:
                    for k, v in fields.items():
                        if k != "unit_reference":
                            setattr(existing, k, v)
                else:
                    db.add(RentalUnit(id=uuid.uuid4(), company_id=current_user.company_id, **fields))
            succeeded += 1
        except (DataError, IntegrityError) as e:
            # Log the database's message server-side; don't hand raw SQL
            # and constraint internals back to the caller.
            logger.warning("Bulk import row %d (%s) rejected: %s", row_number, ref, e.orig)
            kind = "a value is out of range or the wrong type" if isinstance(e, DataError) \
                else "it conflicts with existing data"
            errors.append({"row_number": row_number, "unit_reference": ref,
                            "error": f"Row rejected by the database: {kind}"})
        except Exception:
            logger.exception("Bulk import row %d (%s) failed", row_number, ref)
            errors.append({"row_number": row_number, "unit_reference": ref,
                            "error": "Row could not be saved (unexpected error, see server log)"})

    batch.rows_succeeded = succeeded
    batch.rows_failed = len(errors)
    batch.status = "completed"
    db.flush()

    write_audit_log(
        db,
        company_id=current_user.company_id,
        actor_id=current_user.id,
        actor_type=actor_type,
        action="bulk_import",
        entity_type="rental_unit",
        entity_id=batch.id,
        after_state={"rows_succeeded": succeeded, "rows_failed": len(errors)},
    )

    result = ImportResultOut(
        batch_id=batch.id,
        file_name=batch.file_name,
        rows_succeeded=succeeded,
        rows_failed=len(errors),
        errors=errors,
    )
    db.commit()
    return result


@router.get("", response_model=list[ImportBatchOut])
def list_import_batches(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*ACCOUNT_VIEW_ROLES)),
):
    return db.query(ImportBatch).order_by(ImportBatch.uploaded_at.desc()).all()


@router.get("/{batch_id}", response_model=ImportBatchOut)
def get_import_batch(
    batch_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*ACCOUNT_VIEW_ROLES)),
):
    batch = db.query(ImportBatch).filter(ImportBatch.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Import batch not found")
    return batch
