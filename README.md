# EMMA — Property Management AI Platform

EMMA is a multi-tier AI-driven property management system built for managing rental properties (houses, units, tenants, rent, maintenance, and contractor/"pit crew" workflows) through a conversational agent backed by a proper API and database layer.

## Architecture

Three-tier design:

- **EMMA (Hermes agent)** — the conversational agent. Runs in Docker, exposes five skills that call the FastAPI backend. EMMA has no direct database connection.
- **property_platform (FastAPI)** — the backend API layer. Runs on the host via `uvicorn`, so EMMA reaches it via `host.docker.internal:8000`.
- **PostgreSQL** — source of truth (`property_platform` database), with row-level security (RLS) enforced at the DB layer plus role scoping in the API (tenants see only their own records, company admins only their company, super admin everything).

## Repository layout

Everything lives in this one repo (no submodules):

| Path | Purpose |
|---|---|
| `Dockerfile`, `docker-compose.yml`, `data/finished-skills/` | EMMA agent and skill definitions (`house-crud`, `tenant-crud`, `rent-crud`, `maintenance-crud`, `pit-crew-crud`) |
| `api/` | FastAPI backend — routers, models, auth, role scoping, database access |
| `db/` | PostgreSQL schema, migrations 002–012, RLS verification scripts |
| `demo/` | Public demo stack: its own Postgres + API (127.0.0.1:8100) with seeded demo data |
| `web/` | The website (one static `index.html`), hosted on Vercel at estate-multitenant-management-architecture.vercel.app. `/api/*` is forwarded to the API (`vercel.json`). Deploy: `cd web; vercel deploy --prod` |

## Roles

| Role | Sees | Can do |
|---|---|---|
| Super admin | Every company and account | Creates companies and each one's first admin (`POST /companies`). There is no public signup. |
| Company admin | Everything in their company | All staff work, plus user accounts (staff, tenant and contractor logins), deleting/restoring records, bulk import |
| Staff | Everything in their company except the account list | Day-to-day work: units, tenants, leases, rent, deposits, maintenance, contractors, check-ins |
| Tenant | Only their own lease, payments, requests, check-ins | Report problems, confirm repairs, acknowledge check-ins |
| Contractor | Only jobs assigned to them (`/my-jobs`) | Mark jobs In Progress / On Hold / Completed, add notes |

Company isolation is enforced by Postgres RLS; the role rules above are enforced in the API (`api/app/scoping.py`).

## Skills

EMMA's five CRUD skills call the FastAPI layer exclusively:

- `house-crud`
- `tenant-crud`
- `rent-crud`
- `maintenance-crud`
- `pit-crew-crud`

Skills are mounted read-only into the EMMA container (`data/finished-skills/`) to prevent the agent from modifying its own skill files at runtime.

## Ask EMMA (website chat)

`api/app/chat/` adds a chat to the API that every signed-in role can use:

- `POST /chat` — the person's conversation goes in; EMMA answers using tools that call this API's own endpoints **with the person's own token**, so role checks and row-level security decide what she can see. Each role is only offered the tools it can use.
- `POST /chat/confirm` — EMMA never changes data herself. A write comes back as a signed, 10-minute proposal that only the same person can confirm with a click.
- No shell, files or web access: the only tools are the property endpoints. Per-person rate limits keep AI costs bounded.

Settings in `.env` (change any time, then `docker compose up -d`):

```
OPENAI_API_KEY=...
CHAT_PROVIDER=openai
CHAT_MODEL=gpt-6-luna
TIMEZONE=America/Los_Angeles
```

Adding another AI provider means one more function in `api/app/chat/provider.py`.

### EMMA on Telegram

One bot for everyone (`api/app/telegram/`). A person links their Telegram once from the website (Ask EMMA → Telegram → a one-time, 10-minute code); after that the bot sends their messages through the same `/chat`, as their own login. Unlinked accounts and group chats get nothing. Proposed changes arrive with Confirm / Cancel buttons that only that person can press. Links are stored in `telegram_links` (migration 010); unlink from the website or with `/unlink`.

```
TELEGRAM_BOT_TOKEN=...   # from @BotFather
TELEGRAM_BOT_FOR=demo    # which API runs the bot: demo or real (only one can)
```

## Secrets

Every password lives in **one** git-ignored file: `.env` at the repo root. Copy `.env.example` to `.env` and fill it in. Never commit `.env`.

- EMMA + the real API: `docker compose up -d` from the repo root (reads `.env`; API docs at http://localhost:8000/docs)
- API: run `uvicorn` from `api/` (reads `../.env`); see `api/README.md`
- Database setup and migrations: see `db/README.md`
- Demo: `cd demo; docker compose --env-file ../.env up -d`

## Local setup notes

- FastAPI runs on the host, **not** in Docker — EMMA reaches it at `host.docker.internal:8000`
- Database: PostgreSQL 18, native install, database `property_platform`, app role `app_platform`
- Safety controls: `write_approval: true` (skill writes require manual `/skills approve`), `guard_agent_created: true`

## Cloning

```bash
git clone https://github.com/taemwht/Estate-Multitenant-Management-Architecture-Emma-.git
```
