# Maintenance Schema (INFORMATIONAL ONLY)

This skill no longer creates or manages these tables — schema lives in
Postgres, managed by migration files. Reference only.

## `maintenance_requests`
```sql
-- Core columns from Phase B, plus columns added migrating this skill:
id                       UUID PRIMARY KEY
company_id               UUID NOT NULL REFERENCES companies(id)
rental_unit_id           UUID NOT NULL REFERENCES rental_units(id)
submitted_by             UUID REFERENCES users(id)         -- who used the system
reported_by_tenant_id    UUID REFERENCES tenants(id)       -- which tenant it concerns (added)
description              TEXT NOT NULL
location_detail          TEXT                               -- added
tenant_availability      TEXT                               -- added
priority                 VARCHAR(20) NOT NULL DEFAULT 'normal'  -- added
status                   VARCHAR(20) NOT NULL DEFAULT 'Submitted'
assigned_contractor_id   UUID REFERENCES contractors(id)
verified_by              UUID REFERENCES users(id)
scheduled_date           DATE                               -- added, the REAL planned work date
is_deleted                BOOLEAN NOT NULL DEFAULT false     -- added
submitted_at / scheduled_at / in_progress_at / on_hold_at /
    cancelled_at / completed_at / verified_at   TIMESTAMPTZ  -- status-change timestamps
created_at / updated_at  TIMESTAMPTZ
```
Note `submitted_by` (a user) and `reported_by_tenant_id` (a tenant) are
genuinely different things — see `references/columns.md`.

## `maintenance_log` (brand new — didn't exist until this migration)
```sql
CREATE TABLE maintenance_log (
    id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id               UUID NOT NULL REFERENCES companies(id),
    maintenance_request_id   UUID NOT NULL REFERENCES maintenance_requests(id),
    entry_text               TEXT NOT NULL,
    recorded_by              UUID REFERENCES users(id),
    created_at               TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

## Row-Level Security
Same as every table in this system — scoped to your own company.
