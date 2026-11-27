"""
The tools EMMA's chat can use. Each one is a thin wrapper around one of
this API's own endpoints, and every call runs with the signed-in
person's own token. So the chat can never see or change more than that
person could through the website: the role checks and row-level
security on each endpoint still decide.

Reads run straight away. Writes are never run by the AI: they come back
to the person as a proposal, and only happen when they click Confirm
(see router.py).

Parameter schemas are taken from the API's own OpenAPI document, so they
stay in step with the endpoints automatically.
"""
import copy
import re
from dataclasses import dataclass

from ..scoping import ADMIN_ROLES, STAFF_AND_TENANT_ROLES, STAFF_ROLES

WRITE = ("company_admin", "staff")
DASH = ("company_admin", "staff")
TENANT_OK = ("company_admin", "staff", "tenant")
ALL = ("super_admin", "company_admin", "staff", "tenant", "contractor")


@dataclass(frozen=True)
class Tool:
    name: str
    method: str
    path: str
    roles: tuple
    description: str
    # Fields the API fills in itself for a tenant (they always act as
    # themselves). Hidden so the model can't get them wrong.
    tenant_hidden: tuple = ()

    @property
    def is_write(self) -> bool:
        return self.method != "GET"


TOOLS = [
    Tool("who_am_i", "GET", "/auth/me", ALL, "The signed-in person's own account: username, role, company."),

    # overview
    Tool("dashboard_summary", "GET", "/dashboard/summary", DASH, "Company overview: unit, lease, rent and maintenance counts."),
    Tool("overdue_rent", "GET", "/dashboard/overdue-rent", DASH, "Leases that haven't paid THIS month's rent yet (this month only). For how much someone owes in total, also call arrears for each lease."),

    # units
    Tool("list_units", "GET", "/rental-units", STAFF_AND_TENANT_ROLES, "List rental units (a tenant sees only their own)."),
    Tool("get_unit", "GET", "/rental-units/{unit_id}", STAFF_AND_TENANT_ROLES, "One rental unit by id."),
    Tool("add_unit", "POST", "/rental-units", WRITE, "Add a rental unit."),
    Tool("update_unit", "PATCH", "/rental-units/{unit_id}", WRITE, "Change a rental unit's details."),
    Tool("delete_unit", "DELETE", "/rental-units/{unit_id}", ADMIN_ROLES, "Remove a rental unit (it can be restored)."),

    # tenants
    Tool("list_tenants", "GET", "/tenants", STAFF_AND_TENANT_ROLES, "List tenants (a tenant sees only themselves)."),
    Tool("get_tenant", "GET", "/tenants/{tenant_id}", STAFF_AND_TENANT_ROLES, "One tenant by id."),
    Tool("add_tenant", "POST", "/tenants", WRITE, "Add a tenant (the person: name, email, phone)."),
    Tool("update_tenant", "PATCH", "/tenants/{tenant_id}", WRITE, "Change a tenant's details."),
    Tool("delete_tenant", "DELETE", "/tenants/{tenant_id}", ADMIN_ROLES, "Remove a tenant (it can be restored)."),

    # leases and rent
    Tool("list_leases", "GET", "/leases", STAFF_AND_TENANT_ROLES, "List leases: unit, tenants, rent, dates, status. status_filter: active or ended."),
    Tool("get_lease", "GET", "/leases/{lease_id}", STAFF_AND_TENANT_ROLES, "One lease by id."),
    Tool("create_lease", "POST", "/leases", WRITE, "Create a lease linking a unit, its tenants, the rent and dates."),
    Tool("update_lease", "PATCH", "/leases/{lease_id}", WRITE, "Change a lease (dates, status, due day...)."),
    Tool("change_rent", "POST", "/leases/{lease_id}/rent-changes", WRITE, "Record a new rent amount for a lease from a given date."),
    Tool("rent_history", "GET", "/leases/{lease_id}/rent-history", STAFF_AND_TENANT_ROLES, "A lease's rent amounts over time."),
    Tool("rent_status", "GET", "/leases/{lease_id}/rent-status", STAFF_AND_TENANT_ROLES, "Has this month's rent been paid for a lease?"),
    Tool("arrears", "GET", "/leases/{lease_id}/arrears", STAFF_AND_TENANT_ROLES, "Total rent owed on a lease across all months: the real balance. Use this when asked who owes what or how much."),

    # payments and deposits
    Tool("list_rent_payments", "GET", "/rent-receipts", STAFF_AND_TENANT_ROLES, "List rent payments received."),
    Tool("record_rent_payment", "POST", "/rent-receipts", WRITE, "Record a rent payment received for a lease. method: check, cash, zelle, venmo, bank_transfer, card, money_order or other (put the check number or what 'other' was in method_detail). Set paid_by_tenant_id when a tenant on the lease paid (look them up), or paid_by_name for anyone else. for_month = which month's rent (YYYY-MM-01)."),
    Tool("update_rent_payment", "PATCH", "/rent-receipts/{receipt_id}", WRITE, "Correct a recorded rent payment (amount, date, method, who paid, which month...)."),
    Tool("delete_rent_payment", "DELETE", "/rent-receipts/{receipt_id}", ADMIN_ROLES, "Remove a recorded rent payment (it can be restored)."),
    Tool("list_deposits", "GET", "/security-deposits", STAFF_AND_TENANT_ROLES, "List security deposits."),
    Tool("record_deposit", "POST", "/security-deposits", WRITE, "Record a security deposit for a lease."),
    Tool("update_deposit", "PATCH", "/security-deposits/{deposit_id}", WRITE, "Change a security deposit. status: collected, held, returned or deducted."),

    # maintenance
    Tool("list_maintenance", "GET", "/maintenance-requests", STAFF_AND_TENANT_ROLES, "List maintenance requests (a tenant sees only their own). status_filter takes ONE exact status: Submitted, Scheduled, In Progress, On Hold, Completed, Verified, Cancelled. To find unfinished ones, list without a filter."),
    Tool("get_maintenance", "GET", "/maintenance-requests/{request_id}", STAFF_AND_TENANT_ROLES, "One maintenance request by id."),
    Tool("report_maintenance", "POST", "/maintenance-requests", TENANT_OK, "Report a new repair / maintenance problem. priority: emergency, high, normal or low.",
         tenant_hidden=("reported_by_tenant_id",)),
    Tool("update_maintenance", "PATCH", "/maintenance-requests/{request_id}", WRITE, "Update a request: status (Submitted, Scheduled, In Progress, On Hold, Completed, Verified, Cancelled), priority, contractor, scheduled date."),
    Tool("verify_maintenance", "POST", "/maintenance-requests/{request_id}/verify", TENANT_OK, "Confirm a completed repair really is fixed."),
    Tool("maintenance_log", "GET", "/maintenance-requests/{request_id}/log", STAFF_AND_TENANT_ROLES, "Follow-up notes on a maintenance request."),
    Tool("add_maintenance_note", "POST", "/maintenance-requests/{request_id}/log", WRITE, "Add a follow-up note to a maintenance request."),
    Tool("delete_maintenance", "DELETE", "/maintenance-requests/{request_id}", ADMIN_ROLES, "Remove a maintenance request (it can be restored)."),

    # contractors
    Tool("list_contractors", "GET", "/contractors", STAFF_ROLES, "List contractors (the pit crew)."),
    Tool("get_contractor", "GET", "/contractors/{contractor_id}", STAFF_ROLES, "One contractor by id."),
    Tool("add_contractor", "POST", "/contractors", WRITE, "Add a contractor."),
    Tool("update_contractor", "PATCH", "/contractors/{contractor_id}", WRITE, "Change a contractor's details."),
    Tool("list_contractor_payments", "GET", "/contractor-payments", STAFF_ROLES, "List payments made to contractors."),
    Tool("record_contractor_payment", "POST", "/contractor-payments", WRITE, "Record a payment made to a contractor."),

    # annual check-ins
    Tool("list_checkins", "GET", "/annual-checkins", STAFF_AND_TENANT_ROLES, "List annual tenant check-ins."),
    Tool("acknowledge_checkin", "POST", "/annual-checkins/{checkin_id}/acknowledge", TENANT_OK, "Acknowledge an annual check-in."),

    # contractor's own jobs
    Tool("my_jobs", "GET", "/my-jobs", ("contractor",), "The jobs assigned to me, across every company I work for."),
    Tool("update_my_job", "PATCH", "/my-jobs/{job_id}", ("contractor",), "Mark one of my jobs In Progress, On Hold or Completed."),
    Tool("my_job_notes", "GET", "/my-jobs/{job_id}/log", ("contractor",), "Notes on one of my jobs."),
    Tool("add_my_job_note", "POST", "/my-jobs/{job_id}/log", ("contractor",), "Add a note to one of my jobs."),

    # platform
    Tool("list_companies", "GET", "/companies", ("super_admin",), "Every company on the platform."),
]
BY_NAME = {t.name: t for t in TOOLS}

_PATH_PARAM = re.compile(r"\{(\w+)\}")


def _resolve(node, components, depth=0):
    """Inline $refs and drop noise (titles) so each tool schema stands alone."""
    if depth > 20:
        return {}
    if isinstance(node, dict):
        if "$ref" in node:
            target = components[node["$ref"].rsplit("/", 1)[-1]]
            return _resolve(target, components, depth + 1)
        return {k: _resolve(v, components, depth + 1) for k, v in node.items() if k != "title"}
    if isinstance(node, list):
        return [_resolve(v, components, depth + 1) for v in node]
    return node


@dataclass
class Spec:
    tool: Tool
    parameters: dict          # JSON schema for the model
    path_params: tuple
    query_params: tuple
    body_params: tuple


def build_specs(openapi: dict) -> dict:
    components = openapi.get("components", {}).get("schemas", {})
    specs = {}
    for tool in TOOLS:
        op = openapi["paths"][tool.path][tool.method.lower()]
        props, required = {}, []
        path_p, query_p, body_p = [], [], []
        for p in op.get("parameters", []):
            if p["in"] not in ("path", "query"):
                continue          # headers (X-Actor-Type) are set by us
            schema = _resolve(p.get("schema", {}), components)
            if p.get("description"):
                schema["description"] = p["description"]
            props[p["name"]] = schema
            (path_p if p["in"] == "path" else query_p).append(p["name"])
            if p.get("required"):
                required.append(p["name"])
        body = op.get("requestBody", {}).get("content", {}).get("application/json", {}).get("schema")
        if body:
            body = _resolve(body, components)
            for name, schema in body.get("properties", {}).items():
                assert name not in props, f"{tool.name}: {name} is both a parameter and a body field"
                props[name] = schema
                body_p.append(name)
            required += body.get("required", [])
        specs[tool.name] = Spec(
            tool=tool,
            parameters={"type": "object", "properties": props, "required": required},
            path_params=tuple(path_p), query_params=tuple(query_p), body_params=tuple(body_p),
        )
        assert set(_PATH_PARAM.findall(tool.path)) == set(path_p), tool.name
    return specs


def tools_for_role(specs: dict, role: str) -> list:
    out = []
    for s in specs.values():
        if role not in s.tool.roles:
            continue
        hidden = s.tool.tenant_hidden if role == "tenant" else ()
        if hidden:
            params = copy.deepcopy(s.parameters)
            for h in hidden:
                params["properties"].pop(h, None)
            params["required"] = [x for x in params["required"] if x not in hidden]
            s = Spec(tool=s.tool, parameters=params, path_params=s.path_params,
                     query_params=tuple(q for q in s.query_params if q not in hidden),
                     body_params=tuple(b for b in s.body_params if b not in hidden))
        out.append(s)
    return out


def split_args(spec: Spec, args: dict):
    """Model arguments -> (path, query, body). Unknown keys are dropped."""
    path = spec.tool.path
    for name in spec.path_params:
        value = str(args.get(name, ""))
        if not re.fullmatch(r"[A-Za-z0-9-]{1,64}", value):
            raise ValueError(f"{name} must be an id")
        path = path.replace("{" + name + "}", value)
    query = {k: args[k] for k in spec.query_params if args.get(k) is not None}
    body = {k: copy.deepcopy(args[k]) for k in spec.body_params if k in args} if spec.body_params else None
    if spec.tool.is_write and spec.tool.method in ("POST", "PATCH") and body is None:
        body = {}
    return path, query, body
