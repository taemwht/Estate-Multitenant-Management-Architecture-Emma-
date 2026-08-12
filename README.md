# EMMA — Property Management AI Platform

EMMA is a multi-tier AI-driven property management system built for managing rental properties (houses, units, tenants, rent, maintenance, and contractor/"pit crew" workflows) through a conversational agent backed by a proper API and database layer.

## Architecture

Three-tier design:

- **Hermes/EMMA** — the conversational agent. Runs in Docker, exposes five migrated skills that call the FastAPI backend instead of touching the database directly.
- **property_platform (FastAPI)** — the backend API layer. Runs directly on the host via `uvicorn` (not containerized), so EMMA reaches it via `host.docker.internal:8000`.
- **PostgreSQL** — source of truth, with row-level security (RLS) enforced at the DB layer.

## Repositories (submodules)

| Submodule | Purpose |
|---|---|
| [`hermes`](https://github.com/taemwht/Emma-hermes) | EMMA agent, skill definitions (`house-crud`, `tenant-crud`, `rent-crud`, `maintenance-crud`, `pit-crew-crud`), Docker Compose setup |
| [`api-foundation`](https://github.com/taemwht/Emma-api-foundation) | FastAPI backend — routers, models, auth, database access |
| [`db-foundation`](https://github.com/taemwht/Emma-db-foundation) | PostgreSQL schema, migrations, RLS verification scripts |

## Skills

EMMA's five CRUD skills are fully migrated off direct database access and call the FastAPI layer exclusively:

- `house-crud`
- `tenant-crud`
- `rent-crud`
- `maintenance-crud`
- `pit-crew-crud`

Skills are mounted read-only into the EMMA container (`data/finished-skills/`) to prevent the agent from modifying its own skill files at runtime.

## Local setup notes

- Hermes/EMMA working directory: `hermes/` (mounted via Docker Compose)
- FastAPI runs on the host, **not** in Docker — EMMA reaches it at `host.docker.internal:8000`
- Database: PostgreSQL, native install, database `rental_house`, user `emma`
- Safety controls: `write_approval: true` (skill writes require manual `/skills approve`), `guard_agent_created: true`

## Cloning with submodules

```bash
git clone --recurse-submodules https://github.com/taemwht/Estate-Multitenant-Management-Architecture-Emma-.git
```

If already cloned without `--recurse-submodules`:

```bash
git submodule update --init --recursive
```
