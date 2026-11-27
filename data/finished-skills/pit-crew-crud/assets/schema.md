# Contractor Schema (INFORMATIONAL ONLY)

This skill no longer creates or manages this table — schema lives in
Postgres, managed by migration files. Reference only.

```sql
CREATE TABLE contractors (
    id                         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id                    UUID REFERENCES users(id),
    name                       VARCHAR(255) NOT NULL,
    contact_email              VARCHAR(255),
    contact_phone              VARCHAR(50),
    trade                      VARCHAR(100) NOT NULL,
    preferred_payment_method   VARCHAR(100),
    notes                      TEXT,
    is_deleted                 BOOLEAN NOT NULL DEFAULT false,
    created_at                 TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at                 TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (trade IN (
        'plumber', 'electrician', 'hvac', 'handyman', 'roofer',
        'appliance', 'locksmith', 'pest_control', 'landscaping',
        'general', 'other'
    ))
);
```

Note: contractors have no company_id on this table — they can work
across multiple companies. Which companies they're actually visible to
is tracked via a separate contractor_companies join table.

## contractor_payments (new — cost used to live on maintenance_requests)
```sql
CREATE TABLE contractor_payments (
    id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id               UUID NOT NULL REFERENCES companies(id),
    contractor_id             UUID NOT NULL REFERENCES contractors(id),
    maintenance_request_id   UUID REFERENCES maintenance_requests(id),
    amount                   NUMERIC(10, 2) NOT NULL,
    date_paid                DATE NOT NULL,
    invoice_file             VARCHAR(500),
    recorded_by              UUID REFERENCES users(id),
    created_at                TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

## Row-Level Security
Contractors use a different RLS pattern than most tables — visibility
comes through the contractor_companies join, not a direct company_id
column. Doesn't change how you call pit_crew_crud.py; only matters for
direct psql debugging.
