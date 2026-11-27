# Data model + multi-tenancy foundation — setup

Your Postgres 18 service is already running natively on Windows (`postgresql-x64-18`),
already hosting the old `rental_house` DB for EMMA. This system gets its own
**separate database** — don't reuse `rental_house`, the schemas have nothing in common.

## 1. Create a new database

Open PowerShell / psql as the `postgres` superuser:

```sql
CREATE DATABASE property_platform;
```

## 2. Create a dedicated, non-superuser app role

This is the role your future FastAPI app (and these test scripts) will connect as.
It must NOT be a superuser and must NOT have BYPASSRLS — either one makes Postgres
silently skip Row-Level Security no matter what the policies say.

```sql
CREATE ROLE app_platform WITH LOGIN PASSWORD 'choose-a-real-password' NOSUPERUSER NOBYPASSRLS;
```

## 3. Load the schema (as postgres superuser, against the new DB)

```
psql -U postgres -d property_platform -f schema.sql
```

## 4. Apply the migrations, in order (as postgres superuser)

```
psql -U postgres -d property_platform -f migration_002_house_fields.sql
psql -U postgres -d property_platform -f migration_003_lease_end_reason.sql
psql -U postgres -d property_platform -f migration_004_rent_history.sql
psql -U postgres -d property_platform -f migration_005_rent_rate_history_softdelete.sql
psql -U postgres -d property_platform -f migration_006_maintenance_gaps.sql
psql -U postgres -d property_platform -f migration_007_pit_crew_gaps.sql
psql -U postgres -d property_platform -f migration_008_review_fixes.sql
psql -U postgres -d property_platform -f migration_009_usernames.sql
```

Every migration is safe to re-run. Migration 008 also does the app-role
grants (step 5), including tables created by earlier migrations, and sets
default privileges so tables added by future migrations are granted
automatically.

## 5. Grant the app role access (done by migration 008; manual equivalent)

```sql
\c property_platform
GRANT USAGE ON SCHEMA public TO app_platform;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO app_platform;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO app_platform;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_platform;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO app_platform;
```

A GRANT ... ON ALL TABLES only covers tables that exist at that moment, which
is why the default privileges matter.

## 6. Verify RLS actually isolates companies

Run this **as `app_platform`**, not as `postgres` — testing as superuser would pass
even with broken policies, since superusers ignore RLS entirely.

```
psql -U app_platform -d property_platform -f verify_rls.sql
```

Read the output against the `-- Expected:` comments in the file. If Test 1 or Test 2
returns both rows instead of one, something's wrong with the policy setup — stop and
fix it before building anything on top of this.

## How the app will use this (for when you get to the FastAPI step)

Every request, after authenticating the user, your API layer needs to run:

```sql
SET LOCAL app.current_company_id = '<the logged-in user''s company_id>';
SET LOCAL app.current_user_id = '<the logged-in user''s id>';
SET LOCAL app.is_super_admin = 'true';  -- only if role = super_admin
```

...on that request's DB connection/transaction before running any queries. That's what
makes the RLS policies actually filter — without setting those session variables,
`current_company_id()` returns NULL and everything except super-admin-visible rows
disappears (fails closed, which is the safe direction).

## Known gaps to solve at the next layer, not now

- **Contractor / Super Admin user creation**: inserting a `users` row with
  `company_id IS NULL` requires `app.is_super_admin = 'true'` to be set for that
  transaction (see the `WITH CHECK` on the `users` policy). Your signup/provisioning
  flow needs to explicitly set that flag when creating those two role types.
- **Company self-serve signup** (PRD 5.8) needs the same treatment — the row being
  created doesn't have a `current_company_id` yet, so the insert path needs a
  privileged connection or a `SECURITY DEFINER` function. Worth designing deliberately
  rather than bolting on later.
