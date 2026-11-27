"""
pit_crew_crud.py — API CLIENT for contractor (pit crew) records and
contractor payments. Migrated 2026-08 from direct Postgres access.

STRUCTURAL CHANGES — read before assuming old behavior applies:

  - contractor_id is now a UUID string, not an integer.
  - first_name/last_name -> single `name` field, same pattern as
    tenant-crud: this file still accepts them separately on insert/update
    and concatenates, but reads return one `name` string.
  - `primary_trade` -> `trade`. Same fixed vocabulary, still enforced —
    this file found and fixed a real bug during migration: an earlier
    version of maintenance-crud's trade-matching doc used "plumbing"
    where the actual enum value is "plumber". Fixed in both places.
  - The warn-then-force delete pattern is preserved, but the ACTIVE-
    ASSIGNMENT CHECK now happens SERVER-SIDE (the API queries
    maintenance_requests itself), not client-side like tenant-crud's
    rent-history check had to be. Calling delete_pit_crew() without
    force=True on someone with active assignments returns the same
    warning shape as before; the API also automatically CLEARS
    assigned_contractor_id on those requests when the delete actually
    goes through — you don't need to unassign manually first, unlike the
    old system's session workflow.
  - modified_by is gone — replaced by the audit log, same as every
    migrated skill.
  - NEW: record_payment() — contractor payment recording didn't exist as
    a pit-crew-crud function before (cost lived directly on
    maintenance_requests in the old system). It's a genuinely separate
    entity now, linked to a maintenance request via
    maintenance_request_id — see maintenance-crud's procedures/complete.md
    for how the two skills hand off to each other.

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

VALID_TRADES = {
    "plumber", "electrician", "hvac", "handyman", "roofer",
    "appliance", "locksmith", "pest_control", "landscaping",
    "general", "other",
}


class PitCrewCrudError(ValueError):
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
    raise PitCrewCrudError(f"API error {resp.status_code}: {detail}")


def _warn_if_modified_by(modified_by):
    if modified_by is not None:
        warnings.warn(
            "modified_by is no longer used — tracked automatically via the audit log now.",
            stacklevel=3,
        )


def insert_pit_crew(first_name, primary_trade, last_name=None,
                     preferred_payment_method=None, phone=None, email=None,
                     notes=None, modified_by=None):
    _warn_if_modified_by(modified_by)
    if primary_trade not in VALID_TRADES:
        raise PitCrewCrudError(f"primary_trade '{primary_trade}' is invalid — must be one of {VALID_TRADES}")
    name = f"{first_name} {last_name}".strip() if last_name else first_name
    body = {
        "name": name,
        "trade": primary_trade,
        "contact_phone": phone,
        "contact_email": email,
        "preferred_payment_method": preferred_payment_method,
        "notes": notes,
    }
    resp = _request("POST", "/contractors", json=body)
    _raise_for_api_error(resp)
    return resp.json()


def get_pit_crew(contractor_id):
    resp = _request("GET", f"/contractors/{contractor_id}")
    if resp.status_code == 404:
        return None
    _raise_for_api_error(resp)
    return resp.json()


def list_pit_crew(primary_trade=None, include_deleted=False):
    if include_deleted:
        warnings.warn(
            "include_deleted is not supported server-side — only "
            "non-deleted contractors are ever returned.",
            stacklevel=2,
        )
    params = {}
    if primary_trade:
        params["trade"] = primary_trade
    resp = _request("GET", "/contractors", params=params)
    _raise_for_api_error(resp)
    return resp.json()


def update_pit_crew(contractor_id, modified_by=None, **fields):
    """fields: any of first_name, last_name, primary_trade,
    preferred_payment_method, phone, email, notes"""
    _warn_if_modified_by(modified_by)
    allowed = {"first_name", "last_name", "primary_trade",
               "preferred_payment_method", "phone", "email", "notes"}
    bad = set(fields) - allowed
    if bad:
        raise PitCrewCrudError(f"Unknown fields: {bad}")
    if not fields:
        raise PitCrewCrudError("No fields to update")
    if "primary_trade" in fields and fields["primary_trade"] not in VALID_TRADES:
        raise PitCrewCrudError(f"primary_trade '{fields['primary_trade']}' is invalid — must be one of {VALID_TRADES}")

    body = {}
    if "first_name" in fields or "last_name" in fields:
        current = get_pit_crew(contractor_id)
        if current is None:
            raise PitCrewCrudError(f"No contractor with id={contractor_id}")
        current_parts = (current["name"] or "").split(" ", 1)
        first = fields.get("first_name", current_parts[0] if current_parts else "")
        last = fields.get("last_name", current_parts[1] if len(current_parts) > 1 else None)
        body["name"] = f"{first} {last}".strip() if last else first
    if "primary_trade" in fields:
        body["trade"] = fields["primary_trade"]
    if "preferred_payment_method" in fields:
        body["preferred_payment_method"] = fields["preferred_payment_method"]
    if "phone" in fields:
        body["contact_phone"] = fields["phone"]
    if "email" in fields:
        body["contact_email"] = fields["email"]
    if "notes" in fields:
        body["notes"] = fields["notes"]

    resp = _request("PATCH", f"/contractors/{contractor_id}", json=body)
    _raise_for_api_error(resp)
    return resp.json()


def delete_pit_crew(contractor_id, modified_by=None, force=False):
    """
    Returns a warning dict (same shape as the old version) if this
    contractor has active maintenance-request assignments and
    force=False — the check itself now happens server-side. On an actual
    delete, the API also clears assigned_contractor_id on those requests
    automatically; you don't need a separate unassign step first.
    """
    _warn_if_modified_by(modified_by)
    resp = _request("DELETE", f"/contractors/{contractor_id}", params={"force": force})
    _raise_for_api_error(resp)
    result = resp.json()
    if result.get("warning"):
        return {
            "warning": result["warning"],
            "contractor_id": result["contractor_id"],
            "pit_crew_id": result["contractor_id"],
            "active_requests": result["active_requests"],
        }
    return None


def restore_pit_crew(contractor_id, modified_by=None):
    _warn_if_modified_by(modified_by)
    resp = _request("POST", f"/contractors/{contractor_id}/restore")
    _raise_for_api_error(resp)
    return resp.json()


# ============================================================
# Contractor payments — NEW, no old-system equivalent (cost used to
# live directly on maintenance_requests; now its own entity)
# ============================================================

def record_payment(contractor_id, amount, date_paid, maintenance_request_id=None,
                    invoice_file=None, modified_by=None):
    _warn_if_modified_by(modified_by)
    body = {
        "contractor_id": contractor_id,
        "amount": amount,
        "date_paid": date_paid,
        "maintenance_request_id": maintenance_request_id,
        "invoice_file": invoice_file,
    }
    resp = _request("POST", "/contractor-payments", json=body)
    _raise_for_api_error(resp)
    return resp.json()


def list_payments(contractor_id=None):
    params = {}
    if contractor_id:
        params["contractor_id"] = contractor_id
    resp = _request("GET", "/contractor-payments", params=params)
    _raise_for_api_error(resp)
    return resp.json()


def _cli():
    p = argparse.ArgumentParser(description="pit-crew-crud CLI (now an API client)")
    sub = p.add_subparsers(dest="command", required=True)

    ins = sub.add_parser("insert")
    ins.add_argument("--first-name", required=True)
    ins.add_argument("--last-name")
    ins.add_argument("--primary-trade", required=True)
    ins.add_argument("--preferred-payment-method")
    ins.add_argument("--phone")
    ins.add_argument("--email")
    ins.add_argument("--notes")
    ins.add_argument("--modified-by")

    ls = sub.add_parser("list")
    ls.add_argument("--primary-trade")

    get = sub.add_parser("get")
    get.add_argument("--pit-crew-id", "--contractor-id", required=True, dest="contractor_id")

    upd = sub.add_parser("update")
    upd.add_argument("--pit-crew-id", "--contractor-id", required=True, dest="contractor_id")
    upd.add_argument("--first-name")
    upd.add_argument("--last-name")
    upd.add_argument("--primary-trade")
    upd.add_argument("--preferred-payment-method")
    upd.add_argument("--phone")
    upd.add_argument("--email")
    upd.add_argument("--notes")
    upd.add_argument("--modified-by")

    dele = sub.add_parser("delete")
    dele.add_argument("--pit-crew-id", "--contractor-id", required=True, dest="contractor_id")
    dele.add_argument("--force", action="store_true")
    dele.add_argument("--modified-by")

    res = sub.add_parser("restore")
    res.add_argument("--pit-crew-id", "--contractor-id", required=True, dest="contractor_id")
    res.add_argument("--modified-by")

    pay = sub.add_parser("record-payment")
    pay.add_argument("--contractor-id", required=True)
    pay.add_argument("--amount", type=float, required=True)
    pay.add_argument("--date-paid", required=True)
    pay.add_argument("--maintenance-request-id")
    pay.add_argument("--invoice-file")

    pay_ls = sub.add_parser("list-payments")
    pay_ls.add_argument("--contractor-id")

    args = p.parse_args()

    if args.command == "insert":
        print(insert_pit_crew(args.first_name, args.primary_trade, args.last_name,
                               args.preferred_payment_method, args.phone, args.email,
                               args.notes, args.modified_by))
    elif args.command == "list":
        for m in list_pit_crew(args.primary_trade):
            print(m)
    elif args.command == "get":
        print(get_pit_crew(args.contractor_id))
    elif args.command == "update":
        fields = {k: v for k, v in {
            "first_name": args.first_name, "last_name": args.last_name,
            "primary_trade": args.primary_trade,
            "preferred_payment_method": args.preferred_payment_method,
            "phone": args.phone, "email": args.email, "notes": args.notes,
        }.items() if v is not None}
        print(update_pit_crew(args.contractor_id, args.modified_by, **fields))
    elif args.command == "delete":
        result = delete_pit_crew(args.contractor_id, args.modified_by, args.force)
        print(result if result else "Deleted.")
    elif args.command == "restore":
        print(restore_pit_crew(args.contractor_id, args.modified_by))
    elif args.command == "record-payment":
        print(record_payment(args.contractor_id, args.amount, args.date_paid,
                              args.maintenance_request_id, args.invoice_file))
    elif args.command == "list-payments":
        for pmt in list_payments(args.contractor_id):
            print(pmt)


if __name__ == "__main__":
    _cli()
