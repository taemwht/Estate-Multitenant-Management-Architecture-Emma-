# Rent-Related Schema (INFORMATIONAL ONLY)

This skill no longer creates or manages these tables — schema lives in
Postgres, managed by migration files. Reference only.

## `leases` (was: implicit, via tenants.lease_id text label)
Now a real table — see house-crud's `schema.md` for the full column list.
Relevant here: `monthly_rent`, `due_day_of_month`, `status` (active/ended),
`end_reason` (free text, e.g. "eviction").

## `rent_rate_history` (was: `rent_agreements`)
```sql
CREATE TABLE rent_rate_history (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id         UUID NOT NULL REFERENCES companies(id),
    lease_id           UUID NOT NULL REFERENCES leases(id),
    monthly_rent       NUMERIC(10, 2) NOT NULL,
    due_day_of_month   SMALLINT NOT NULL CHECK (due_day_of_month BETWEEN 1 AND 31),
    effective_date     DATE NOT NULL,
    recorded_by        UUID REFERENCES users(id),
    is_deleted         BOOLEAN NOT NULL DEFAULT false,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
```
No `status: active/superseded` column — "current" rate is whichever row
has the latest `effective_date`. Every lease gets an initial entry here
automatically when created, so historical calculations always have a
starting point even if rent's never explicitly been changed since.

## `rent_receipts` (was: `rent_payments`)
```sql
CREATE TABLE rent_receipts (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id     UUID NOT NULL REFERENCES companies(id),
    lease_id       UUID NOT NULL REFERENCES leases(id),
    amount         NUMERIC(10, 2) NOT NULL,
    date_received  DATE NOT NULL,
    method         VARCHAR(20) NOT NULL CHECK (method IN ('check', 'cash', 'other')),
    late_fee       NUMERIC(10, 2) NOT NULL DEFAULT 0,
    recorded_by    UUID REFERENCES users(id),
    notes          TEXT,
    is_deleted     BOOLEAN NOT NULL DEFAULT false,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
```
`method` is CHECK-constrained to exactly `check`/`cash`/`other` — free
text like "Venmo" now needs to go in `notes` instead, or map to `other`.

## Row-Level Security
Same as every table in this system — scoped to your own company.
