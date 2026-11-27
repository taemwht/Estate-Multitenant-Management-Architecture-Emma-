"""
house_crud.py — API CLIENT for rental units. Migrated 2026-08 from direct
Postgres access to calling the property-platform FastAPI backend, per the
PRD's 3-tier architecture (Hermes is a presentation-tier client, same as
the web UI — it doesn't touch the database directly anymore).

Function names and most parameter names are kept the same as the old
version on purpose, so callers and behavior docs need the smallest
possible set of changes. Real, deliberate differences from the old
version — read this before assuming old behavior still applies:

  - `house_id` is now a UUID STRING, not an auto-incrementing integer.
    This is the one change that couldn't be papered over — anything
    that stored or compared house_id as an int will break.
  - `nickname` -> the new schema's `unit_reference`. Kept as `nickname`
    in this file's function signatures/return values, translated
    internally.
  - `street_address`/`unit` -> `address_line1`/`address_line2`.
    Same translation approach.
  - Old free-text `status` (e.g. "occupied") -> the new `occupancy_status`
    field. The new schema's own `status` column is reserved strictly for
    active/deleted bookkeeping and would reject free text outright.
  - `modified_by` no longer exists server-side. The API's audit_log table
    now records who (actor_id, from the logged-in identity) and what kind
    of caller (actor_type: 'hermes', sent by this file on every write)
    made each change. Passing modified_by is accepted here for backward
    compatibility but is IGNORED — see insert_house/update_house/etc.
  - Delete's "is anyone living here" check now looks at ACTIVE LEASES,
    not a tenant status flag — the new schema tracks occupancy via
    leases. This is enforced by the server (a 409 error), not this
    script, and happens to be the ONLY way to test it right now since
    the tenants API doesn't exist yet.
  - Nickname/unit_reference uniqueness is now per-company, not global.
    Not a practical difference for single-company use.
  - There is no schema auto-creation anymore (`init` used to run
    CREATE TABLE IF NOT EXISTS). Schema lives in Postgres already,
    managed by migration files. `init` is kept as a CLI command for
    compatibility but is now a no-op that says so.

## Auth (temporary, see SKILL.md)
Real per-person Telegram-linked auth (PRD 3.2) doesn't exist yet. Until
it does, this file logs in with a single shared "service" account —
credentials read from the API_EMAIL / API_PASSWORD environment
variables — meaning every action EMMA takes shows up in the audit log
as that one account, not whichever person is actually chatting. Known,
accepted limitation for now; not a bug in this file.

Requires the `requests` package. If it's not already installed in this
container: `pip install requests`.
"""

import argparse
import os
import threading
import warnings

import requests

API_BASE_URL = os.environ.get("API_BASE_URL", "http://host.docker.internal:8000")
API_EMAIL = os.environ.get("API_EMAIL")
API_PASSWORD = os.environ.get("API_PASSWORD")

_token_lock = threading.Lock()
_access_token = None


class HouseCrudError(ValueError):
    """Raised for any API error (validation, conflict, not-found, etc.)
    so callers can catch one thing, same as the old version raising
    ValueError for its equivalent failures."""


def _login():
    global _access_token
    if not API_EMAIL or not API_PASSWORD:
        raise RuntimeError(
            "API_EMAIL / API_PASSWORD environment variables are not set. "
            "These are the temporary stand-in credentials for EMMA until "
            "real per-person auth is built — see SKILL.md's Auth section."
        )
    resp = requests.post(
        f"{API_BASE_URL}/auth/login",
        json={"email": API_EMAIL, "password": API_PASSWORD},
        timeout=10,
    )
    resp.raise_for_status()
    _access_token = resp.json()["access_token"]


def _headers():
    global _access_token
    with _token_lock:
        if _access_token is None:
            _login()
    return {
        "Authorization": f"Bearer {_access_token}",
        "X-Actor-Type": "hermes",  # PRD 6.3 — tags every write as agent-initiated
    }


def _request(method, path, **kwargs):
    """One retry on 401 — access tokens expire after 15 minutes, so any
    long-running EMMA session will hit this routinely, not as an edge
    case. Re-logs in once and retries; a second 401 means something's
    actually wrong (bad credentials, account deactivated) and is allowed
    to surface."""
    resp = requests.request(method, f"{API_BASE_URL}{path}", headers=_headers(), timeout=15, **kwargs)
    if resp.status_code == 401:
        global _access_token
        with _token_lock:
            _access_token = None
        resp = requests.request(method, f"{API_BASE_URL}{path}", headers=_headers(), timeout=15, **kwargs)
    return resp


def _raise_for_api_error(resp):
    if resp.ok:
        return
    try:
        detail = resp.json().get("detail", resp.text)
    except Exception:
        detail = resp.text
    raise HouseCrudError(f"API error {resp.status_code}: {detail}")


def _warn_if_modified_by(modified_by):
    if modified_by is not None:
        warnings.warn(
            "modified_by is no longer used — the API's audit log tracks "
            "this automatically now. This value was silently ignored.",
            stacklevel=3,
        )


def _to_house_dict(unit):
    """Translates the API's field names back to the old houses-table
    shape, so existing callers/behavior docs don't need to change their
    expectations beyond what's documented above."""
    return {
        "house_id": unit["id"],
        "nickname": unit["unit_reference"],
        "street_address": unit.get("address_line1"),
        "unit": unit.get("address_line2"),
        "city": unit.get("city"),
        "state": unit.get("state"),
        "zip_code": unit.get("zip_code"),
        "year_built": unit.get("year_built"),
        "bedrooms": unit.get("bedrooms"),
        "bathrooms": unit.get("bathrooms"),
        "status": unit.get("occupancy_status"),
        "notes": unit.get("notes"),
        "is_deleted": 1 if unit.get("is_deleted") else 0,
    }


def insert_house(nickname, street_address, city, zip_code, unit=None, state="CA",
                  year_built=None, bedrooms=None, bathrooms=None, status=None,
                  notes=None, modified_by=None):
    _warn_if_modified_by(modified_by)
    body = {
        "unit_reference": nickname,
        "address_line1": street_address,
        "address_line2": unit,
        "city": city,
        "state": state,
        "zip_code": zip_code,
        "year_built": year_built,
        "bedrooms": bedrooms,
        "bathrooms": bathrooms,
        "occupancy_status": status,
        "notes": notes,
    }
    resp = _request("POST", "/rental-units", json=body)
    _raise_for_api_error(resp)
    return _to_house_dict(resp.json())


def get_house(house_id):
    resp = _request("GET", f"/rental-units/{house_id}")
    if resp.status_code == 404:
        return None
    _raise_for_api_error(resp)
    return _to_house_dict(resp.json())


def get_house_by_nickname(nickname, include_deleted=False):
    if include_deleted:
        warnings.warn(
            "include_deleted is not yet supported server-side for lookup "
            "by nickname — the API's list endpoint only returns "
            "non-deleted units. Returning a non-deleted match only, or "
            "None.",
            stacklevel=2,
        )
    resp = _request("GET", "/rental-units", params={"unit_reference": nickname})
    _raise_for_api_error(resp)
    results = resp.json()
    return _to_house_dict(results[0]) if results else None


def list_houses(street_address=None, include_deleted=False):
    if include_deleted:
        warnings.warn(
            "include_deleted is not yet supported server-side — only "
            "non-deleted units are ever returned.",
            stacklevel=2,
        )
    params = {}
    if street_address:
        params["address_line1"] = street_address
    resp = _request("GET", "/rental-units", params=params)
    _raise_for_api_error(resp)
    return [_to_house_dict(r) for r in resp.json()]


def update_house(house_id, modified_by=None, **fields):
    _warn_if_modified_by(modified_by)
    if "nickname" in fields:
        raise HouseCrudError(
            "Renaming a unit's nickname/unit_reference isn't supported by "
            "the API yet — this is a real gap carried over from the "
            "migration, not a bug in this script. Everything else can "
            "still be updated normally."
        )

    field_map = {
        "street_address": "address_line1", "unit": "address_line2",
        "city": "city", "state": "state", "zip_code": "zip_code",
        "year_built": "year_built", "bedrooms": "bedrooms",
        "bathrooms": "bathrooms", "status": "occupancy_status", "notes": "notes",
    }
    bad = set(fields) - set(field_map)
    if bad:
        raise HouseCrudError(f"Unknown fields: {bad}")
    if not fields:
        raise HouseCrudError("No fields to update")

    body = {field_map[k]: v for k, v in fields.items()}
    resp = _request("PATCH", f"/rental-units/{house_id}", json=body)
    _raise_for_api_error(resp)
    return _to_house_dict(resp.json())


def delete_house(house_id, modified_by=None):
    _warn_if_modified_by(modified_by)
    resp = _request("DELETE", f"/rental-units/{house_id}")
    if resp.status_code == 409:
        # Active-lease block (the new-schema equivalent of the old
        # active-tenant check — see module docstring). Surfaced as the
        # same exception type as any other API error, so callers don't
        # need a special case for it, but the message tells the real story.
        _raise_for_api_error(resp)
    _raise_for_api_error(resp)
    return None


def restore_house(house_id, modified_by=None):
    _warn_if_modified_by(modified_by)
    resp = _request("POST", f"/rental-units/{house_id}/restore")
    _raise_for_api_error(resp)
    return _to_house_dict(resp.json())


def _cli():
    p = argparse.ArgumentParser(description="house-crud CLI (now an API client)")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="No-op now — schema is managed by migrations, not this script")

    ins = sub.add_parser("insert")
    ins.add_argument("--nickname", required=True)
    ins.add_argument("--street-address", required=True)
    ins.add_argument("--unit")
    ins.add_argument("--city", required=True)
    ins.add_argument("--zip-code", required=True)
    ins.add_argument("--state", default="CA")
    ins.add_argument("--year-built", type=int)
    ins.add_argument("--bedrooms", type=int)
    ins.add_argument("--bathrooms", type=float)
    ins.add_argument("--status")
    ins.add_argument("--notes")
    ins.add_argument("--modified-by")

    get = sub.add_parser("get")
    get.add_argument("--house-id", required=True, help="UUID string, not an integer anymore")

    getn = sub.add_parser("get-by-nickname")
    getn.add_argument("--nickname", required=True)

    lst = sub.add_parser("list")
    lst.add_argument("--street-address")
    lst.add_argument("--include-deleted", action="store_true")

    upd = sub.add_parser("update")
    upd.add_argument("--house-id", required=True)
    upd.add_argument("--street-address")
    upd.add_argument("--unit")
    upd.add_argument("--city")
    upd.add_argument("--state")
    upd.add_argument("--zip-code")
    upd.add_argument("--year-built", type=int)
    upd.add_argument("--bedrooms", type=int)
    upd.add_argument("--bathrooms", type=float)
    upd.add_argument("--status")
    upd.add_argument("--notes")
    upd.add_argument("--modified-by")

    dele = sub.add_parser("delete")
    dele.add_argument("--house-id", required=True)
    dele.add_argument("--modified-by")

    res = sub.add_parser("restore")
    res.add_argument("--house-id", required=True)
    res.add_argument("--modified-by")

    args = p.parse_args()

    if args.command == "init":
        print("No-op: schema is managed by migrations now, not this script. Nothing to do.")
    elif args.command == "insert":
        print(insert_house(args.nickname, args.street_address, args.city,
                            args.zip_code, args.unit, args.state,
                            args.year_built, args.bedrooms, args.bathrooms,
                            args.status, args.notes, args.modified_by))
    elif args.command == "get":
        print(get_house(args.house_id))
    elif args.command == "get-by-nickname":
        print(get_house_by_nickname(args.nickname))
    elif args.command == "list":
        for h in list_houses(args.street_address, args.include_deleted):
            print(h)
    elif args.command == "update":
        fields = {k: v for k, v in {
            "street_address": args.street_address, "unit": args.unit,
            "city": args.city, "state": args.state, "zip_code": args.zip_code,
            "year_built": args.year_built, "bedrooms": args.bedrooms,
            "bathrooms": args.bathrooms, "status": args.status, "notes": args.notes,
        }.items() if v is not None}
        print(update_house(args.house_id, args.modified_by, **fields))
    elif args.command == "delete":
        delete_house(args.house_id, args.modified_by)
        print("Deleted.")
    elif args.command == "restore":
        print(restore_house(args.house_id, args.modified_by))


if __name__ == "__main__":
    _cli()
