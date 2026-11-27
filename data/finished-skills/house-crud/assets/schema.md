# Rental Unit Schema (INFORMATIONAL ONLY — changed 2026-08)

**This skill no longer creates or manages this table.** The old
`CREATE TABLE IF NOT EXISTS` behavior (previously run automatically by
`house_crud.py` on every connection) is gone — `init` is now a no-op.
Schema lives in Postgres already, managed by migration files
(`db-foundation/schema.sql` + `migration_002_house_fields.sql`), not by
this skill. This file exists purely as a reference for what the
underlying table looks like, in case you're debugging directly against
Postgres rather than going through `house_crud.py`.

The table is `rental_units`, in the `property_platform` database — NOT
`rental_house`, and NOT a table called `houses` anymore.

```sql
CREATE TABLE rental_units (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id        UUID NOT NULL REFERENCES companies(id),
    unit_reference    VARCHAR(100) NOT NULL,   -- was: nickname
    address_line1     VARCHAR(255),            -- was: street_address
    address_line2     VARCHAR(255),            -- was: unit
    city              VARCHAR(100),
    state             VARCHAR(50),
    zip_code          VARCHAR(20),
    unit_type         VARCHAR(50),
    year_built        INTEGER,
    bedrooms          INTEGER,
    bathrooms         NUMERIC(3, 1),
    notes             TEXT,
    occupancy_status  VARCHAR(50),             -- was: status (free text)
    status            VARCHAR(20) NOT NULL DEFAULT 'active'
                          CHECK (status IN ('active', 'deleted')),  -- NOT the same meaning as old `status`
    is_deleted        BOOLEAN NOT NULL DEFAULT false,
    deleted_at        TIMESTAMPTZ,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (company_id, unit_reference)
);
```

## What changed from the old `houses` table
- Primary key is `id` (UUID), not `house_id` (integer).
- `nickname` is unique **per company** now (`company_id, unit_reference`),
  not globally — every row also carries a `company_id`, since this is a
  multi-tenant system now, not a single household's private database.
- `modified_by` is gone entirely — replaced by a separate `audit_log`
  table that records every write with who did it and whether it came
  through Hermes or the web UI.
- Row-Level Security (RLS) is enabled on this table — a database-level
  restriction that only shows/allows rows for the querying session's own
  company. This is invisible to `house_crud.py`'s callers (the API
  handles it), but matters if you're ever connecting with `psql` directly
  — plain queries as a non-superuser will only see one company's rows,
  by design, not by accident.

None of this changes how you call `house_crud.py` — it's translation this
file's functions handle internally. See `columns.md` for the old-name ↔
new-name mapping the script uses.
