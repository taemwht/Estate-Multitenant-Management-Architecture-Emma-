"""
rent_crud.py — API CLIENT for lease lifecycle, rent-rate history, and
payments. Migrated 2026-08 from direct Postgres access (two tables:
rent_agreements, rent_payments) to calling the property-platform FastAPI
backend. This is the biggest structural change of the three skill
migrations — read carefully before assuming old behavior applies.

WHAT CHANGED, AND WHY

  - The old system had no first-class "lease" concept — a `lease_id` was
    just a shared text label generated when a tenant was inserted, and
    `rent_agreements` tracked rates against that label. The new system's
    LEASE is a real, rich entity (unit, dates, rent, due day, status,
    end_reason) — and CREATING one is now this file's job, not
    tenant-crud's. See `create_lease()` below — there's no equivalent
    old function, because the old system never had a distinct
    "lease creation" step separate from "tenant gets a lease_id."

  - `rent_agreements` -> `rent_rate_history`, functionally similar (an
    append-only ledger of every rate that's ever applied) but now lives
    ALONGSIDE the lease's own `monthly_rent`/`due_day_of_month` fields,
    which always reflect the CURRENT rate. record_rent_change() updates
    both together, atomically, so the rest of the system doesn't need to
    know history exists to use the current rate.

  - No more `status: active/superseded` on rate rows — "current" is
    simply whichever row has the latest effective_date. Avoids the same
    kind of status-field collision risk flagged during house-crud's
    migration.

  - `rent_payments` -> `rent_receipts`, same shape, PLUS a `late_fee`
    field that didn't exist in the new schema until this migration
    (added specifically to preserve this capability).

  - "Who owes what" is now TWO functions instead of one, because the old
    single `amount_owed_for_lease()` conflated two different questions:
      - rent_status(lease_id) — THIS MONTH only, quick snapshot
      - arrears(lease_id) — full multi-month history, correctly using
        whatever rate applied in each historical month (not just the
        current rate), with a total_owed figure — built specifically
        because "I'm lenient, I track total owed across months, not
        just flag one month overdue" mattered as a real requirement,
        not an assumption on my part.

  - lease_id / tenant resolution: there's no single-step "resolve by
    house/tenant name" query anymore — `resolve_lease_for_unit()` and
    `resolve_lease_for_tenant_name()` do the chained lookups themselves
    (unit -> active lease, or tenant name -> tenant -> their lease(s)).

  - modified_by is gone — replaced by the API's audit log, same as the
    other two migrated skills.

Reuses the SAME API_BASE_URL / API_EMAIL / API_PASSWORD environment
variables already configured. Requires `requests`, already confirmed
installed.
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


class RentCrudError(ValueError):
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
    raise RentCrudError(f"API error {resp.status_code}: {detail}")


def _warn_if_modified_by(modified_by):
    if modified_by is not None:
        warnings.warn(
            "modified_by is no longer used — tracked automatically via the audit log now.",
            stacklevel=3,
        )


# ============================================================
# Lease lifecycle
# ============================================================

def create_lease(unit_reference, tenant_ids, start_date, monthly_rent,
                  due_day_of_month, security_deposit_amount=0, end_date=None,
                  modified_by=None):
    """
    NEW — no direct old-system equivalent (see module docstring). This
    is the step that comes after tenant-crud creates the tenant(s):
    resolves the unit by its nickname/reference, then creates the lease
    itself, attaching the given tenant_ids. Fails with a clear error if
    the unit already has an active lease (one-active-lease-per-unit is
    enforced server-side) or if any tenant_id doesn't exist.
    """
    _warn_if_modified_by(modified_by)
    resp = _request("GET", "/rental-units", params={"unit_reference": unit_reference})
    _raise_for_api_error(resp)
    units = resp.json()
    if not units:
        raise RentCrudError(f"No rental unit found with reference '{unit_reference}'")
    unit_id = units[0]["id"]

    body = {
        "rental_unit_id": unit_id,
        "tenant_ids": tenant_ids,
        "start_date": start_date,
        "end_date": end_date,
        "monthly_rent": monthly_rent,
        "due_day_of_month": due_day_of_month,
        "security_deposit_amount": security_deposit_amount,
    }
    resp = _request("POST", "/leases", json=body)
    _raise_for_api_error(resp)
    return resp.json()


def get_lease(lease_id):
    resp = _request("GET", f"/leases/{lease_id}")
    if resp.status_code == 404:
        return None
    _raise_for_api_error(resp)
    return resp.json()


def end_lease(lease_id, end_date, end_reason=None, modified_by=None):
    """end_reason: free text, e.g. "normal", "eviction" — added
    specifically to preserve eviction tracking."""
    _warn_if_modified_by(modified_by)
    body = {"end_date": end_date, "status": "ended"}
    if end_reason is not None:
        body["end_reason"] = end_reason
    resp = _request("PATCH", f"/leases/{lease_id}", json=body)
    _raise_for_api_error(resp)
    return resp.json()


def update_lease(lease_id, modified_by=None, **fields):
    """For correcting data-entry errors (deposit amount, etc.) — NOT
    for recording a genuine rent change, use record_rent_change() for
    that, or it won't be reflected in rent history."""
    _warn_if_modified_by(modified_by)
    resp = _request("PATCH", f"/leases/{lease_id}", json=fields)
    _raise_for_api_error(resp)
    return resp.json()


# ============================================================
# Rent rate history (was: rent_agreements)
# ============================================================

def record_rent_change(lease_id, monthly_rent, due_day_of_month, effective_date, modified_by=None):
    """A GENUINE rent change over time. Writes a permanent history entry
    AND updates the lease's current rate together — see module docstring."""
    _warn_if_modified_by(modified_by)
    resp = _request("POST", f"/leases/{lease_id}/rent-changes", json={
        "monthly_rent": monthly_rent,
        "due_day_of_month": due_day_of_month,
        "effective_date": effective_date,
    })
    _raise_for_api_error(resp)
    return resp.json()


def get_rent_history(lease_id):
    resp = _request("GET", f"/leases/{lease_id}/rent-history")
    _raise_for_api_error(resp)
    return resp.json()


def current_rent(lease_id):
    lease = get_lease(lease_id)
    if lease is None:
        return None
    return {"monthly_rent": lease["monthly_rent"], "due_day_of_month": lease["due_day_of_month"]}


def get_rent_agreement(lease_id, history_id):
    """NOTE: signature changed — now needs lease_id too (old version
    took agreement_id alone). No single-item endpoint exists server-side
    for this, so this filters the full history list client-side."""
    for row in get_rent_history(lease_id):
        if row["id"] == history_id:
            return row
    return None


def update_rent_agreement(lease_id, history_id, modified_by=None, **fields):
    """For correcting a data-entry error on a historical rate record —
    NOT for an actual rent change, use record_rent_change() for that."""
    _warn_if_modified_by(modified_by)
    resp = _request("PATCH", f"/leases/{lease_id}/rent-changes/{history_id}", json=fields)
    _raise_for_api_error(resp)
    return resp.json()


def delete_rent_agreement(lease_id, history_id, modified_by=None):
    _warn_if_modified_by(modified_by)
    resp = _request("DELETE", f"/leases/{lease_id}/rent-changes/{history_id}")
    _raise_for_api_error(resp)
    return None


def restore_rent_agreement(lease_id, history_id, modified_by=None):
    _warn_if_modified_by(modified_by)
    resp = _request("POST", f"/leases/{lease_id}/rent-changes/{history_id}/restore")
    _raise_for_api_error(resp)
    return resp.json()


# ============================================================
# Payments (was: rent_payments)
# ============================================================

def insert_rent_payment(lease_id, amount_paid, date_paid, payment_method=None,
                         late_fee=0, notes=None, modified_by=None):
    _warn_if_modified_by(modified_by)
    resp = _request("POST", "/rent-receipts", json={
        "lease_id": lease_id,
        "amount": amount_paid,
        "date_received": date_paid,
        "method": payment_method or "other",
        "late_fee": late_fee,
        "notes": notes,
    })
    _raise_for_api_error(resp)
    return resp.json()


def get_rent_payment(payment_id):
    resp = _request("GET", f"/rent-receipts/{payment_id}")
    if resp.status_code == 404:
        return None
    _raise_for_api_error(resp)
    return resp.json()


def list_payments_for_lease(lease_id):
    resp = _request("GET", "/rent-receipts", params={"lease_id": lease_id})
    _raise_for_api_error(resp)
    return resp.json()


def update_rent_payment(payment_id, modified_by=None, **fields):
    _warn_if_modified_by(modified_by)
    resp = _request("PATCH", f"/rent-receipts/{payment_id}", json=fields)
    _raise_for_api_error(resp)
    return resp.json()


def delete_rent_payment(payment_id, modified_by=None):
    _warn_if_modified_by(modified_by)
    resp = _request("DELETE", f"/rent-receipts/{payment_id}")
    _raise_for_api_error(resp)
    return None


def restore_rent_payment(payment_id, modified_by=None):
    _warn_if_modified_by(modified_by)
    resp = _request("POST", f"/rent-receipts/{payment_id}/restore")
    _raise_for_api_error(resp)
    return resp.json()


# ============================================================
# Who owes what
# ============================================================

def rent_status(lease_id):
    """THIS MONTH ONLY — quick snapshot. For the full multi-month
    picture (total owed, month-by-month), use arrears() instead."""
    resp = _request("GET", f"/leases/{lease_id}/rent-status")
    _raise_for_api_error(resp)
    return resp.json()


def arrears(lease_id):
    """Full multi-month arrears: total_owed plus a month-by-month
    breakdown (expected/paid/outstanding), correctly using whatever rate
    applied in each historical month. This is what answers "how much
    total, and how much was last month vs. this month" — not rent_status(),
    which only looks at the current month."""
    resp = _request("GET", f"/leases/{lease_id}/arrears")
    _raise_for_api_error(resp)
    return resp.json()


# ============================================================
# Resolution helpers
# ============================================================

def resolve_lease_for_unit(unit_reference, active_only=True):
    resp = _request("GET", "/rental-units", params={"unit_reference": unit_reference})
    _raise_for_api_error(resp)
    units = resp.json()
    if not units:
        return []
    params = {"rental_unit_id": units[0]["id"]}
    if active_only:
        params["status_filter"] = "active"
    resp = _request("GET", "/leases", params=params)
    _raise_for_api_error(resp)
    return resp.json()


def resolve_lease_for_tenant_name(name):
    resp = _request("GET", "/tenants", params={"name": name})
    _raise_for_api_error(resp)
    tenants = resp.json()
    if not tenants:
        return []
    tenant_ids = {t["id"] for t in tenants}
    resp = _request("GET", "/leases")
    _raise_for_api_error(resp)
    return [l for l in resp.json() if tenant_ids & set(l.get("tenant_ids", []))]


def _cli():
    p = argparse.ArgumentParser(description="rent-crud CLI (now an API client)")
    sub = p.add_subparsers(dest="command", required=True)

    cl = sub.add_parser("create-lease")
    cl.add_argument("--unit-reference", required=True)
    cl.add_argument("--tenant-id", action="append", required=True, dest="tenant_ids")
    cl.add_argument("--start-date", required=True)
    cl.add_argument("--monthly-rent", type=float, required=True)
    cl.add_argument("--due-day", type=int, required=True)
    cl.add_argument("--security-deposit", type=float, default=0)
    cl.add_argument("--end-date")

    gl = sub.add_parser("get-lease")
    gl.add_argument("--lease-id", required=True)

    el = sub.add_parser("end-lease")
    el.add_argument("--lease-id", required=True)
    el.add_argument("--end-date", required=True)
    el.add_argument("--end-reason")

    rc = sub.add_parser("record-rent-change")
    rc.add_argument("--lease-id", required=True)
    rc.add_argument("--monthly-rent", type=float, required=True)
    rc.add_argument("--due-day", type=int, required=True)
    rc.add_argument("--effective-date", required=True)

    rh = sub.add_parser("rent-history")
    rh.add_argument("--lease-id", required=True)

    ip = sub.add_parser("insert-payment")
    ip.add_argument("--lease-id", required=True)
    ip.add_argument("--amount-paid", type=float, required=True)
    ip.add_argument("--date-paid", required=True)
    ip.add_argument("--payment-method")
    ip.add_argument("--late-fee", type=float, default=0)
    ip.add_argument("--notes")

    lp = sub.add_parser("list-payments")
    lp.add_argument("--lease-id", required=True)

    st = sub.add_parser("rent-status")
    st.add_argument("--lease-id", required=True)

    ar = sub.add_parser("arrears")
    ar.add_argument("--lease-id", required=True)

    ru = sub.add_parser("resolve-unit")
    ru.add_argument("--unit-reference", required=True)
    ru.add_argument("--include-history", action="store_true")

    rt = sub.add_parser("resolve-tenant")
    rt.add_argument("--name", required=True)

    args = p.parse_args()

    if args.command == "create-lease":
        print(create_lease(args.unit_reference, args.tenant_ids, args.start_date,
                            args.monthly_rent, args.due_day, args.security_deposit, args.end_date))
    elif args.command == "get-lease":
        print(get_lease(args.lease_id))
    elif args.command == "end-lease":
        print(end_lease(args.lease_id, args.end_date, args.end_reason))
    elif args.command == "record-rent-change":
        print(record_rent_change(args.lease_id, args.monthly_rent, args.due_day, args.effective_date))
    elif args.command == "rent-history":
        for row in get_rent_history(args.lease_id):
            print(row)
    elif args.command == "insert-payment":
        print(insert_rent_payment(args.lease_id, args.amount_paid, args.date_paid,
                                   args.payment_method, args.late_fee, args.notes))
    elif args.command == "list-payments":
        for pmt in list_payments_for_lease(args.lease_id):
            print(pmt)
    elif args.command == "rent-status":
        print(rent_status(args.lease_id))
    elif args.command == "arrears":
        print(arrears(args.lease_id))
    elif args.command == "resolve-unit":
        for lease in resolve_lease_for_unit(args.unit_reference, active_only=not args.include_history):
            print(lease)
    elif args.command == "resolve-tenant":
        for lease in resolve_lease_for_tenant_name(args.name):
            print(lease)


if __name__ == "__main__":
    _cli()
