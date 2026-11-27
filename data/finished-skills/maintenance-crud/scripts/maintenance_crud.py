"""
maintenance_crud.py — API CLIENT for maintenance requests and the
per-request follow-up log. Migrated 2026-08 from direct Postgres access.

STRUCTURAL CHANGES — read before assuming old behavior applies:

  - request_id is now a UUID string, not an integer.
  - `house_id` (int) -> resolve by `unit_reference` instead (like the
    other migrated skills) — insert_request/list_requests take a unit
    reference string, resolved to the real rental_unit_id internally.
  - `unit_label` is GONE — same reasoning as house-crud/tenant-crud: the
    new system distinguishes units via separate rental_unit records, not
    a free-text tag on each request.
  - `assigned_pit_crew_id` -> `assigned_contractor_id`. Same soft-
    reference philosophy (validated in application code / the API layer,
    not a hard FK forcing tight coupling to pit-crew-crud).
  - `cost` / `payment_method` / `completed_date` are GONE from the
    request itself. In the old system these lived directly on
    maintenance_requests; in the new system they're properly split out
    into pit-crew-crud's ContractorPayment entity (linked back to this
    request via maintenance_request_id), and completed_date is just
    `completed_at`, set automatically when status becomes Completed.
    Concretely: marking something Completed here is now a SEPARATE step
    from recording what it cost — see procedures/complete.md.
  - Status list is now Submitted/Scheduled/In Progress/On Hold/Completed/
    Verified/Cancelled — a deliberate merge of the old system's list
    (open/in_progress/on_hold/completed/cancelled) with the new
    platform's Scheduled and Verified steps (the latter matters: someone
    OTHER than whoever did the work confirms it's actually done before
    the request closes).
  - The auto-transition-to-Scheduled rule is preserved but was actually
    BUGGY in the initial platform build (it fired off the status label
    being set, not the real condition) — fixed server-side; this client
    doesn't need to do anything special, just set assigned_contractor_id
    and scheduled_date and the server handles the rest correctly now.
  - `reported_by_tenant_id` can be set at creation but is NOT editable
    via update in this version — known gap, not silently dropped: if you
    need to correct who reported something after the fact, that's not
    supported yet.
  - modified_by is gone — replaced by the API's audit log, same as every
    other migrated skill.

Reuses the same API_BASE_URL / API_EMAIL / API_PASSWORD environment
variables already configured. Requires `requests`, already installed.
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


class MaintenanceCrudError(ValueError):
    pass


def _login():
    global _access_token
    if not API_EMAIL or not API_PASSWORD:
        raise RuntimeError(
            "API_EMAIL / API_PASSWORD environment variables are not set. "
            "These should already be configured from the house-crud migration."
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
    return {"Authorization": f"Bearer {_access_token}", "X-Actor-Type": "hermes"}


def _request(method, path, **kwargs):
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
    raise MaintenanceCrudError(f"API error {resp.status_code}: {detail}")


def _warn_if_modified_by(modified_by):
    if modified_by is not None:
        warnings.warn(
            "modified_by is no longer used — tracked automatically via the audit log now.",
            stacklevel=3,
        )


def _resolve_unit_id(unit_reference):
    resp = _request("GET", "/rental-units", params={"unit_reference": unit_reference})
    _raise_for_api_error(resp)
    units = resp.json()
    if not units:
        raise MaintenanceCrudError(f"No rental unit found with reference '{unit_reference}'")
    return units[0]["id"]


# ============================================================
# Maintenance requests
# ============================================================

def insert_request(unit_reference, problem_description, location_detail=None,
                    priority="normal", reported_by_tenant_id=None,
                    tenant_availability=None, modified_by=None):
    _warn_if_modified_by(modified_by)
    unit_id = _resolve_unit_id(unit_reference)
    body = {
        "rental_unit_id": unit_id,
        "description": problem_description,
        "priority": priority,
        "location_detail": location_detail,
        "tenant_availability": tenant_availability,
        "reported_by_tenant_id": reported_by_tenant_id,
    }
    resp = _request("POST", "/maintenance-requests", json=body)
    _raise_for_api_error(resp)
    return resp.json()


def get_request(request_id):
    resp = _request("GET", f"/maintenance-requests/{request_id}")
    if resp.status_code == 404:
        return None
    _raise_for_api_error(resp)
    return resp.json()


def list_requests(unit_reference=None, status=None, assigned_contractor_id=None):
    """NOTE: include_deleted isn't supported server-side (only
    non-deleted, non-Cancelled requests show by default — pass
    status="Cancelled" explicitly to see cancelled ones)."""
    params = {}
    if unit_reference:
        params["rental_unit_id"] = _resolve_unit_id(unit_reference)
    if status:
        params["status_filter"] = status
    if assigned_contractor_id:
        params["assigned_contractor_id"] = assigned_contractor_id
    resp = _request("GET", "/maintenance-requests", params=params)
    _raise_for_api_error(resp)
    return resp.json()


def update_request(request_id, modified_by=None, **fields):
    """fields: any of description, location_detail, tenant_availability,
    priority, status, assigned_contractor_id, scheduled_date.

    REMOVED from the old field set (raises clearly, doesn't silently
    ignore):
      - unit_label: no longer exists (see module docstring)
      - cost, payment_method, completed_date: now pit-crew-crud's
        ContractorPayment + the automatic completed_at timestamp
      - reported_by_tenant_id: settable at creation only right now,
        known gap, not silently dropped
    """
    removed = {"unit_label", "cost", "payment_method", "completed_date", "reported_by_tenant_id"}
    used_removed = set(fields) & removed
    if used_removed:
        raise MaintenanceCrudError(
            f"These fields are no longer updatable here: {used_removed}. "
            f"cost/payment_method now go through pit-crew-crud's contractor "
            f"payment recording; completed_date is automatic (set when status "
            f"becomes Completed); unit_label and reported_by_tenant_id changes "
            f"aren't supported post-creation yet."
        )
    _warn_if_modified_by(modified_by)
    resp = _request("PATCH", f"/maintenance-requests/{request_id}", json=fields)
    _raise_for_api_error(resp)
    return resp.json()


def verify_request(request_id, modified_by=None):
    """Either the tenant or admin/staff can verify — whichever confirms
    first. Separate from update_request so this narrower action doesn't
    also allow reassigning/rescheduling in the same call."""
    _warn_if_modified_by(modified_by)
    resp = _request("POST", f"/maintenance-requests/{request_id}/verify")
    _raise_for_api_error(resp)
    return resp.json()


def delete_request(request_id, modified_by=None):
    _warn_if_modified_by(modified_by)
    resp = _request("DELETE", f"/maintenance-requests/{request_id}")
    _raise_for_api_error(resp)
    return None


def restore_request(request_id, modified_by=None):
    _warn_if_modified_by(modified_by)
    resp = _request("POST", f"/maintenance-requests/{request_id}/restore")
    _raise_for_api_error(resp)
    return resp.json()


# ============================================================
# Follow-up log (new table — didn't exist until this migration)
# ============================================================

def add_log_entry(request_id, entry_text, modified_by=None):
    _warn_if_modified_by(modified_by)
    resp = _request("POST", f"/maintenance-requests/{request_id}/log", json={"entry_text": entry_text})
    _raise_for_api_error(resp)
    return resp.json()


def list_log_entries(request_id):
    resp = _request("GET", f"/maintenance-requests/{request_id}/log")
    _raise_for_api_error(resp)
    return resp.json()


# ============================================================
# Contractor-trade matching (client-side — pit-crew-crud not migrated
# yet, but the `trade` field already exists on contractors)
# ============================================================

def suggest_contractors_for_trade(trade):
    """Filters client-side since there's no server-side trade filter
    yet. Fine for current data volume."""
    resp = _request("GET", "/contractors")
    _raise_for_api_error(resp)
    return [c for c in resp.json() if (c.get("trade") or "").lower() == trade.lower()]


def _cli():
    p = argparse.ArgumentParser(description="maintenance-crud CLI (now an API client)")
    sub = p.add_subparsers(dest="command", required=True)

    ins = sub.add_parser("insert")
    ins.add_argument("--unit-reference", required=True)
    ins.add_argument("--problem-description", required=True)
    ins.add_argument("--location-detail")
    ins.add_argument("--priority", default="normal")
    ins.add_argument("--reported-by-tenant-id")
    ins.add_argument("--tenant-availability")
    ins.add_argument("--modified-by")

    get = sub.add_parser("get")
    get.add_argument("--request-id", required=True)

    ls = sub.add_parser("list")
    ls.add_argument("--unit-reference")
    ls.add_argument("--status")
    ls.add_argument("--assigned-contractor-id")

    upd = sub.add_parser("update")
    upd.add_argument("--request-id", required=True)
    upd.add_argument("--description")
    upd.add_argument("--location-detail")
    upd.add_argument("--tenant-availability")
    upd.add_argument("--priority")
    upd.add_argument("--status")
    upd.add_argument("--assigned-contractor-id")
    upd.add_argument("--scheduled-date")
    upd.add_argument("--modified-by")

    ver = sub.add_parser("verify")
    ver.add_argument("--request-id", required=True)

    dele = sub.add_parser("delete")
    dele.add_argument("--request-id", required=True)

    res = sub.add_parser("restore")
    res.add_argument("--request-id", required=True)

    log = sub.add_parser("log")
    log.add_argument("--request-id", required=True)
    log.add_argument("--entry-text", required=True)

    log_ls = sub.add_parser("log-list")
    log_ls.add_argument("--request-id", required=True)

    sug = sub.add_parser("suggest-contractors")
    sug.add_argument("--trade", required=True)

    args = p.parse_args()

    if args.command == "insert":
        print(insert_request(args.unit_reference, args.problem_description,
                              args.location_detail, args.priority,
                              args.reported_by_tenant_id, args.tenant_availability,
                              args.modified_by))
    elif args.command == "get":
        print(get_request(args.request_id))
    elif args.command == "list":
        for r in list_requests(args.unit_reference, args.status, args.assigned_contractor_id):
            print(r)
    elif args.command == "update":
        fields = {k: v for k, v in {
            "description": args.description, "location_detail": args.location_detail,
            "tenant_availability": args.tenant_availability, "priority": args.priority,
            "status": args.status, "assigned_contractor_id": args.assigned_contractor_id,
            "scheduled_date": args.scheduled_date,
        }.items() if v is not None}
        print(update_request(args.request_id, args.modified_by, **fields))
    elif args.command == "verify":
        print(verify_request(args.request_id))
    elif args.command == "delete":
        delete_request(args.request_id)
        print("Deleted.")
    elif args.command == "restore":
        print(restore_request(args.request_id))
    elif args.command == "log":
        print(add_log_entry(args.request_id, args.entry_text))
    elif args.command == "log-list":
        for entry in list_log_entries(args.request_id):
            print(entry)
    elif args.command == "suggest-contractors":
        for c in suggest_contractors_for_trade(args.trade):
            print(c)


if __name__ == "__main__":
    _cli()
