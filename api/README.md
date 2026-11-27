# FastAPI skeleton + JWT auth — setup

Builds on `../db` (schema + RLS) from the previous step. This gives you
`/auth/login`, `/auth/refresh`, `/auth/me`, and a `/health` check — enough to prove
auth works end-to-end against the real database before adding any business logic.

## 1. Get Python set up on the EMMA machine

If you don't already have Python on that machine (separate from whatever Hermes uses
inside its Docker container):

```powershell
python --version
```

If that fails, install Python 3.11+ from python.org first.

## 2. Get the code

This folder is `api/` inside the Emma repo
(`C:\Users\claremont70\Documents\Emma\api`).

## 3. Create a virtual environment and install dependencies

From inside that folder on the EMMA machine:

```powershell
cd C:\Users\claremont70\Documents\Emma\api
python -m venv venv
.\venv\Scripts\pip install -r requirements.txt
```

## 4. Configure environment variables

All secrets live in one git-ignored file at the repo root, `Emma\.env`
(start from `Emma\.env.example`). The API reads it as `../.env`, so run
`uvicorn` from inside `api/`. Set these keys in it:
- `DATABASE_URL` — put in the real `app_platform` password (the one you set with
  `CREATE ROLE app_platform ...`). Never write it in this README or any other
  committed file. Use `localhost` instead of `host.docker.internal`
  in the URL if you're running `uvicorn` directly on Windows rather than in Docker.
- `JWT_SECRET_KEY` — generate a real one:
  ```powershell
  .\venv\Scripts\python -c "import secrets; print(secrets.token_urlsafe(48))"
  ```
  Paste that in. Don't leave the placeholder — anyone with it can forge valid tokens.

## 5. Create your first login

There's no signup endpoint yet (that's PRD 5.8, still an open item), so seed one
company + admin user directly:

```powershell
.\venv\Scripts\python scripts\create_first_admin.py
```

It'll prompt for a company name, admin email, and password.

## 6. Run the API

```powershell
.\venv\Scripts\uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## 7. Test it

In another terminal (or Postman, or curl from the same machine):

```powershell
curl -X POST http://localhost:8000/auth/login -H "Content-Type: application/json" -d "{\"email\":\"YOUR_EMAIL\",\"password\":\"YOUR_PASSWORD\"}"
```

Should return an `access_token` and `refresh_token`. Then:

```powershell
curl http://localhost:8000/auth/me -H "Authorization: Bearer PASTE_ACCESS_TOKEN_HERE"
```

Should return your user id, company_id, role, and email — confirming the token → RLS
context → DB lookup chain all actually works together, not just in isolation.

## What's real vs. what's a stand-in right now

**Solid:** password hashing (bcrypt), JWT signing/verification, the RLS context
handoff on every authenticated request (this is the part that proves the auth layer
and the multi-tenancy foundation from the last step are actually wired together
correctly, not just two things that each work alone).

**Deliberately deferred** (flagged in code comments too, not hidden):
- No refresh token revocation/blacklist — a leaked refresh token is valid until it
  expires. Fine for now, needs a real fix before this is internet-facing.
- No rate limiting on `/auth/login` — brute-force protection isn't built yet.
- No signup endpoint — `create_first_admin.py` is a stand-in for PRD 5.8.
- Contractor/self-serve signup's "privileged insert path" (flagged in the
  db/README.md) is now implemented as `super_admin_session()` in
  `app/database.py` — the mechanism exists, but no endpoint uses it for signup yet.
