# Tenant Schema (INFORMATIONAL ONLY)

This skill no longer creates or manages this table — schema lives in
Postgres, managed by migration files, same as house-crud. Reference only.

The table is `tenants`, in the `property_platform` database (not
`rental_house`, not the old `houses`-linked `tenants` table).

```sql
CREATE TABLE tenants (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id  UUID NOT NULL REFERENCES companies(id),
    user_id     UUID REFERENCES users(id),  -- nullable: portal login is optional
    name        VARCHAR(255) NOT NULL,      -- was: first_name + last_name
    email       VARCHAR(255),
    phone       VARCHAR(50),
    is_deleted  BOOLEAN NOT NULL DEFAULT false,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

## What's gone from this table (moved elsewhere — see columns.md)
`house_id`, `unit_label`, `lease_id` (in the old lightweight sense),
`move_in_date`, `move_out_date`, `status` — none of these exist here
anymore. They're properties of a **lease** now (a much richer entity:
unit, dates, rent amount, due day, status, end_reason), not the tenant.

## Row-Level Security
Same as every table in this system — scoped to your own company. Doesn't
change how you call `tenant_crud.py`; only matters if you're ever
connecting with `psql` directly.
