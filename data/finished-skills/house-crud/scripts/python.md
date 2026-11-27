# Calling `house_crud.py` (now an API client — migrated 2026-08)

**Absolute path — use this exact path, don't search for the file:**
```
/opt/data/skills/house-crud/scripts/house_crud.py
```
If a read/find/search tool can't locate `house_crud.py` by bare filename
or a relative path, that's a working-directory mismatch, not a missing
file — use the absolute path above rather than falling back to
placeholder/fake/memory-based data.

**History note:** this file was previously overwritten with a broken stub
at one point (same failure mode documented in the old `SKILL.md`) — worth
knowing this file specifically has had integrity problems before. If its
contents ever look wrong again, that's the pattern to suspect.

This version calls the property-platform FastAPI backend instead of
touching Postgres directly (see `SKILL.md`'s Data Location section). The
function names and call shapes below are the SAME as the pre-migration
version on purpose — the only required setup change is environment
variables (see bottom of this file).

## As a library
```python
from house_crud import (
    insert_house, get_house, get_house_by_nickname, list_houses,
    update_house, delete_house, restore_house, HouseCrudError,
)

house_a = insert_house(
    nickname="Longford A",
    street_address="138 Longford Drive",
    city="South San Francisco",
    zip_code="94080",
    unit="#A",              # optional
)

house_b = insert_house(
    nickname="Longford B",
    street_address="138 Longford Drive",   # same address
    city="South San Francisco",
    zip_code="94080",
    unit="#B",               # different unit
)

# No unit at all — perfectly fine
claremont = insert_house(
    nickname="Claremont",
    street_address="102 Claremont Ave",
    city="South San Francisco",
    zip_code="94080",
)

houses = list_houses()                                    # all non-deleted
houses = list_houses(street_address="138 Longford Drive")  # just units at one address

house = get_house(house_id="5e779923-f029-4635-8211-bbb795a91f6d")  # NOTE: UUID string now, not an int
house = get_house_by_nickname("Claremont")

update_house(house_id=house["house_id"], status="occupied")

try:
    delete_house(house_id=house_b["house_id"])   # soft-delete
except HouseCrudError as e:
    # e.g. "API error 409: Cannot delete: unit has an active lease..."
    print(f"Couldn't delete: {e}")

restore_house(house_id=house_b["house_id"])
```

**Removed:** `modified_by` used to be a parameter on every write function.
It's still accepted (so old calling code doesn't crash) but does nothing
now except emit a warning — see `columns.md` for why.

## As a CLI
```bash
python3 /opt/data/skills/house-crud/scripts/house_crud.py init    # no-op now — prints an explanation, does nothing
python3 /opt/data/skills/house-crud/scripts/house_crud.py insert --nickname "Longford A" --street-address "138 Longford Drive" --unit "#A" --city "South San Francisco" --zip-code 94080
python3 /opt/data/skills/house-crud/scripts/house_crud.py insert --nickname "Longford B" --street-address "138 Longford Drive" --unit "#B" --city "South San Francisco" --zip-code 94080
python3 /opt/data/skills/house-crud/scripts/house_crud.py list
python3 /opt/data/skills/house-crud/scripts/house_crud.py list --street-address "138 Longford Drive"
python3 /opt/data/skills/house-crud/scripts/house_crud.py get --house-id 5e779923-f029-4635-8211-bbb795a91f6d
python3 /opt/data/skills/house-crud/scripts/house_crud.py get-by-nickname --nickname "Claremont"
python3 /opt/data/skills/house-crud/scripts/house_crud.py update --house-id 5e779923-f029-4635-8211-bbb795a91f6d --status occupied
python3 /opt/data/skills/house-crud/scripts/house_crud.py delete --house-id 5e779923-f029-4635-8211-bbb795a91f6d
python3 /opt/data/skills/house-crud/scripts/house_crud.py restore --house-id 5e779923-f029-4635-8211-bbb795a91f6d
```

**Changed:** `--house-id` now takes a UUID string (like the examples
above), not a plain integer. Old saved integer IDs from before the
migration are not valid anymore — data was carried over with new UUIDs
assigned, the old integer values aren't stored anywhere in the new system.

`--modified-by` is still accepted everywhere for compatibility but does
nothing (see "Removed" above).

## Required environment variables (new — didn't exist before)
- `API_BASE_URL` — defaults to `http://host.docker.internal:8000` if unset.
- `API_EMAIL` / `API_PASSWORD` — the temporary shared login this skill
  authenticates as, until real per-person auth exists (see `SKILL.md`).
  **Required** — `house_crud.py` raises immediately with a clear message
  if these aren't set, rather than failing confusingly later.

`init` is now a no-op — the underlying schema is managed by migration
files, not by this script connecting and creating tables. Kept as a CLI
command so old scripts/muscle-memory calling it don't break, but it just
prints an explanation.
