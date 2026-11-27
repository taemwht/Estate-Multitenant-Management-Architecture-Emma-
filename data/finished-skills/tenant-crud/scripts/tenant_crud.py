"""
tenant_crud.py — API CLIENT for tenants. Migrated 2026-08 from direct
Postgres access to calling the property-platform FastAPI backend.

STRUCTURAL CHANGES from the old version — read before assuming old
behavior still applies. This is a bigger shift than house-crud's
migration was:

  - tenant_id is now a UUID STRING, not an integer.
  - first_name/last_name are GONE server-side — the new Tenant entity has
    ONE `name` field. insert_tenant/update_tenant still take first_name/
    last_name as separate parameters (so the calling convention doesn't
    change more than necessary) and concatenate them into `name`
    internally — but READING a tenant back gives you `name` as one
    string, not separated first_name/last_name. There's no reliable way
    to split "Jane Mary Smith" back into parts, so this file doesn't
    pretend to.
  - house_id, unit_label, lease_id, move_in_date, move_out_date, and
    status (active/past/evicted) are ALL GONE from the tenant record
    itself. A tenant in the new system is just a person — name, email,
    phone. Everything about WHERE they live and WHEN is now a property of
    the LEASE they're attached to (rent-crud's territory), not the
    tenant:
      - "which house/unit" -> the lease's rental_unit_id
      - "unit_label" (e.g. "#A") -> no separate free-text tag anymore;
        the new system distinguishes units by having separate rental_unit
        + lease records instead (see house-crud's own migration notes)
      - move_in_date / move_out_date -> lease.start_date / lease.end_date
      - status active/past/evicted -> lease.status (active/ended) PLUS
        lease.end_reason (free text, e.g. "eviction" — added specifically
        because eviction tracking mattered and had no home otherwise)
    This file CANNOT create or manage leases — that's rent_crud.py. A
    tenant created here exists standalone until rent-crud attaches them
    to a lease via that lease's tenant_ids.
  - Calling insert_tenant/update_tenant with the OLD parameter names
    (house_id, unit_label, lease_id, move_in_date, status) will raise a
    normal Python error rather than silently doing nothing — deliberate,
    since silently swallowing those risked a value landing in the wrong
    field instead of erroring loudly. If you hit this, the calling code
    (procedures/insert.md's instructions to hermes-agent) needs updating,
    not this file.
  - `force` on delete is now a CLIENT-SIDE check, not server-enforced:
    this file queries whether the tenant has rent-payment history across
    any of their leases before deleting, and returns a warning dict
    (same shape as before) if force=False and history exists. Calling
    the API directly instead of through this file skips that check
    entirely — it's not a server-side guarantee.
  - modified_by no longer exists server-side — replaced by the API's
    audit log (actor_id + X-Actor-Type: hermes), same as house_crud.py.
    Still accepted here for backward compatibility, ignored with a
    warning.

Reuses the SAME API_BASE_URL / API_EMAIL / API_PASSWORD environment
variables already configured for house-crud — nothing new to set up.
Requires `requests`, already confirmed installed during that migration.
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


class TenantCrudError(ValueError):
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
    return {
        "Authorization": f"Bearer {_access_token}",
        "X-Actor-Type": "hermes",
    }


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
    raise TenantCrudError(f"API error {resp.status_code}: {detail}")


def _warn_if_modified_by(modified_by):
    if modified_by is not None:
        warnings.warn(
            "modified_by is no longer used — the API's audit log tracks "
            "this automatically now. This value was silently ignored.",
            stacklevel=3,
        )


def _to_tenant_dict(t):
    """
    Old-shape-ish dict for callers used to the previous version. Fields
    that no longer exist AT ALL on a tenant are explicitly set to None
    (not omitted) so old code checking `tenant.get("status")` gets a
    clear absence rather than a confusing KeyError.
    """
    return {
        "tenant_id": t["id"],
        "name": t["name"],
        "email": t.get("email"),
        "phone": t.get("phone"),
        "is_deleted": 1 if t.get("is_deleted") else 0,
        "house_id": None,
        "unit_label": None,
        "lease_id": None,
        "move_in_date": None,
        "move_out_date": None,
        "status": None,
    }


def insert_tenant(first_name, last_name=None, phone=None, email=None, modified_by=None):
    _warn_if_modified_by(modified_by)
    name = f"{first_name} {last_name}".strip() if last_name else first_name
    resp = _request("POST", "/tenants", json={"name": name, "email": email, "phone": phone})
    _raise_for_api_error(resp)
    return _to_tenant_dict(resp.json())


def get_tenant(tenant_id):
    resp = _request("GET", f"/tenants/{tenant_id}")
    if resp.status_code == 404:
        return None
    _raise_for_api_error(resp)
    return _to_tenant_dict(resp.json())


def list_tenants(name=None, include_deleted=False):
    if include_deleted:
        warnings.warn(
            "include_deleted is not supported server-side — only "
            "non-deleted tenants are ever returned.",
            stacklevel=2,
        )
    params = {}
    if name:
        params["name"] = name
    resp = _request("GET", "/tenants", params=params)
    _raise_for_api_error(resp)
    return [_to_tenant_dict(t) for t in resp.json()]


def list_tenants_for_unit(unit_reference, active_only=True):
    """
    Replaces the old list_tenants_for_house. Composed across multiple API
    calls since there's no direct "tenants for this house" query anymore
    — that relationship only exists via leases now:
      1. resolve the unit by its nickname/unit_reference
      2. find its lease(s) (active only by default; pass active_only=False
         for full history, including past/ended leases)
      3. fetch each attached tenant's details

    Returns a list of dicts, one per (lease, tenant) pair:
    {lease_id, lease_status, start_date, end_date, end_reason, tenant}
    """
    resp = _request("GET", "/rental-units", params={"unit_reference": unit_reference})
    _raise_for_api_error(resp)
    units = resp.json()
    if not units:
        return []
    unit_id = units[0]["id"]

    params = {"rental_unit_id": unit_id}
    if active_only:
        params["status_filter"] = "active"
    resp = _request("GET", "/leases", params=params)
    _raise_for_api_error(resp)
    leases = resp.json()

    results = []
    for lease in leases:
        for tenant_id in lease.get("tenant_ids", []):
            t_resp = _request("GET", f"/tenants/{tenant_id}")
            if not t_resp.ok:
                continue
            results.append({
                "lease_id": lease["id"],
                "lease_status": lease["status"],
                "start_date": lease["start_date"],
                "end_date": lease.get("end_date"),
                "end_reason": lease.get("end_reason"),
                "tenant": _to_tenant_dict(t_resp.json()),
            })
    return results


def get_leases_for_tenant(tenant_id):
    """
    No server-side filter exists yet for "leases this tenant is on" —
    this fetches every lease in the company and filters client-side.
    Fine for current data volume; would need a real API addition (a
    tenant_id query param on GET /leases) if this ever needs to scale.
    """
    resp = _request("GET", "/leases")
    _raise_for_api_error(resp)
    return [l for l in resp.json() if tenant_id in l.get("tenant_ids", [])]


def list_tenants_by_lease(lease_id):
    resp = _request("GET", f"/leases/{lease_id}")
    _raise_for_api_error(resp)
    lease = resp.json()
    results = []
    for tenant_id in lease.get("tenant_ids", []):
        t = get_tenant(tenant_id)
        if t:
            results.append(t)
    return results


def update_tenant(tenant_id, modified_by=None, **fields):
    _warn_if_modified_by(modified_by)
    allowed = {"first_name", "last_name", "phone", "email"}
    bad = set(fields) - allowed
    if bad:
        raise TenantCrudError(
            f"Unknown or no-longer-supported fields: {bad}. house_id / "
            f"unit_label / lease_id / move_in_date / move_out_date / status "
            f"now live on the LEASE, not the tenant — use rent_crud.py for those."
        )
    if not fields:
        raise TenantCrudError("No fields to update")

    body = {}
    if "first_name" in fields or "last_name" in fields:
        current = get_tenant(tenant_id)
        if current is None:
            raise TenantCrudError(f"No tenant with id={tenant_id}")
        current_parts = (current["name"] or "").split(" ", 1)
        first = fields.get("first_name", current_parts[0] if current_parts else "")
        last = fields.get("last_name", current_parts[1] if len(current_parts) > 1 else None)
        body["name"] = f"{first} {last}".strip() if last else first
    if "phone" in fields:
        body["phone"] = fields["phone"]
    if "email" in fields:
        body["email"] = fields["email"]

    resp = _request("PATCH", f"/tenants/{tenant_id}", json=body)
    _raise_for_api_error(resp)
    return _to_tenant_dict(resp.json())


def delete_tenant(tenant_id, modified_by=None, force=False):
    """
    Client-side history check (the API itself doesn't warn — see module
    docstring). Returns a warning dict, same shape as the old version,
    if rent-payment history exists across any of this tenant's leases
    and force=False, instead of deleting.
    """
    _warn_if_modified_by(modified_by)
    if not force:
        leases = get_leases_for_tenant(tenant_id)
        total_payments = 0
        for lease in leases:
            r = _request("GET", "/rent-receipts", params={"lease_id": lease["id"]})
            if r.ok:
                total_payments += len(r.json())
        if total_payments:
            return {
                "warning": "rent_history_attached",
                "tenant_id": tenant_id,
                "lease_count": len(leases),
                "payment_count": total_payments,
            }

    resp = _request("DELETE", f"/tenants/{tenant_id}")
    _raise_for_api_error(resp)
    return None


def restore_tenant(tenant_id, modified_by=None):
    _warn_if_modified_by(modified_by)
    resp = _request("POST", f"/tenants/{tenant_id}/restore")
    _raise_for_api_error(resp)
    return _to_tenant_dict(resp.json())


def _cli():
    p = argparse.ArgumentParser(description="tenant-crud CLI (now an API client)")
    sub = p.add_subparsers(dest="command", required=True)

    ins = sub.add_parser("insert")
    ins.add_argument("--first-name", required=True)
    ins.add_argument("--last-name")
    ins.add_argument("--phone")
    ins.add_argument("--email")
    ins.add_argument("--modified-by")

    get = sub.add_parser("get")
    get.add_argument("--tenant-id", required=True)

    lst = sub.add_parser("list")
    lst.add_argument("--name")

    lu = sub.add_parser("list-unit")
    lu.add_argument("--unit-reference", required=True)
    lu.add_argument("--include-history", action="store_true")

    ll = sub.add_parser("list-lease")
    ll.add_argument("--lease-id", required=True)

    upd = sub.add_parser("update")
    upd.add_argument("--tenant-id", required=True)
    upd.add_argument("--first-name")
    upd.add_argument("--last-name")
    upd.add_argument("--phone")
    upd.add_argument("--email")
    upd.add_argument("--modified-by")

    dele = sub.add_parser("delete")
    dele.add_argument("--tenant-id", required=True)
    dele.add_argument("--force", action="store_true")
    dele.add_argument("--modified-by")

    res = sub.add_parser("restore")
    res.add_argument("--tenant-id", required=True)
    res.add_argument("--modified-by")

    args = p.parse_args()

    if args.command == "insert":
        print(insert_tenant(args.first_name, args.last_name, args.phone, args.email, args.modified_by))
    elif args.command == "get":
        print(get_tenant(args.tenant_id))
    elif args.command == "list":
        for t in list_tenants(args.name):
            print(t)
    elif args.command == "list-unit":
        for row in list_tenants_for_unit(args.unit_reference, active_only=not args.include_history):
            print(row)
    elif args.command == "list-lease":
        for t in list_tenants_by_lease(args.lease_id):
            print(t)
    elif args.command == "update":
        fields = {k: v for k, v in {
            "first_name": args.first_name, "last_name": args.last_name,
            "phone": args.phone, "email": args.email,
        }.items() if v is not None}
        print(update_tenant(args.tenant_id, args.modified_by, **fields))
    elif args.command == "delete":
        result = delete_tenant(args.tenant_id, args.modified_by, args.force)
        print(result if result else "Deleted.")
    elif args.command == "restore":
        print(restore_tenant(args.tenant_id, args.modified_by))


if __name__ == "__main__":
    _cli()
