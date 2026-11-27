#!/bin/bash
# Runs once, on the demo database's first start (postgres image init hook).
set -euo pipefail
psql -v ON_ERROR_STOP=1 -U postgres <<SQL
CREATE DATABASE property_platform;
CREATE ROLE app_platform WITH LOGIN PASSWORD '${APP_DB_PASSWORD}' NOSUPERUSER NOBYPASSRLS;
SQL
cd /db-foundation
psql -v ON_ERROR_STOP=1 -U postgres -d property_platform -f schema.sql
for f in migration_00*.sql; do
  psql -v ON_ERROR_STOP=1 -U postgres -d property_platform -f "$f"
done
