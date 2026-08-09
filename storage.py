"""JSON persistence, keyed by client.

Every write is atomic: serialize to a temp file in the same directory, then
os.replace. A half-written data.json loses every client record, so a crash
mid-write must leave the previous file untouched rather than truncated.
"""

import json
import os
import re
import tempfile
from datetime import date, datetime, timedelta
from decimal import Decimal

from config import DATA_FILE, INVOICE_START_NUMBER, INVOICE_DUE_DAYS

_EMPTY = {
    "clients": {},
    "meta": {
        "last_invoice_number": INVOICE_START_NUMBER - 1,
        "freelancer": {"name": "", "email": "", "phone": "", "payment_details": ""},
    },
}


# ─────────────────────────── slugs & helpers ───────────────────────────

def slugify(name: str) -> str:
    """'Acme Corp.' -> 'acmecorp'. Inconsistent capitalisation must not fork
    one client into three records."""
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


def today() -> date:
    return date.today()


def parse_date(value):
    """Accept ISO strings or date objects; return a date or None."""
    if isinstance(value, date):
        return value
    if isinstance(value, datetime):
        return value.date()
    if not value:
        return None
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def iso(d) -> str:
    d = parse_date(d) or today()
    return d.isoformat()


def pretty_date(value) -> str:
    """'2026-08-08' -> '8 August 2026'. Unambiguous across regions, unlike
    03/15/26 which reads as two different days depending on the reader."""
    d = parse_date(value)
    if not d:
        return "—"
    return f"{d.day} {d.strftime('%B')} {d.year}"


# ─────────────────────────── load / save ───────────────────────────

def load() -> dict:
    if not DATA_FILE.exists():
        return json.loads(json.dumps(_EMPTY))
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (json.JSONDecodeError, OSError):
        # Corrupt file: preserve it for inspection rather than overwriting.
        if DATA_FILE.exists():
            DATA_FILE.replace(DATA_FILE.with_suffix(".corrupt.json"))
        return json.loads(json.dumps(_EMPTY))

    data.setdefault("clients", {})
    meta = data.setdefault("meta", {})
    meta.setdefault("last_invoice_number", INVOICE_START_NUMBER - 1)
    meta.setdefault("freelancer", {"name": "", "email": "", "phone": "", "payment_details": ""})
    return data


def save(data: dict) -> None:
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=str(DATA_FILE.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False, default=str)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_path, DATA_FILE)
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


# ─────────────────────────── clients ───────────────────────────

def get_client(data: dict, name: str):
    return data["clients"].get(slugify(name))


def ensure_client(data: dict, name: str, email: str = "", company: str = "", phone: str = "") -> dict:
    key = slugify(name)
    if not key:
        raise ValueError("Client name cannot be empty.")
    client = data["clients"].get(key)
    if client is None:
        client = {
            "name": name.strip(),
            "email": email.strip(),
            "company": company.strip(),
            "phone": phone.strip(),
            "projects": [],
            "proposals": [],
            "invoices": [],
            "reminders": [],
        }
        data["clients"][key] = client
    else:
        # Fill blanks without overwriting what is already known.
        if email and not client.get("email"):
            client["email"] = email.strip()
        if company and not client.get("company"):
            client["company"] = company.strip()
        if phone and not client.get("phone"):
            client["phone"] = phone.strip()
    for field in ("projects", "proposals", "invoices", "reminders"):
        client.setdefault(field, [])
    return client


def find_client_fuzzy(data: dict, name: str):
    """Exact slug match, then substring. Returns (client_key, client) or
    (None, None). Never silently resolves to a 'close enough' match — marking
    the wrong client's invoice paid surfaces weeks later."""
    key = slugify(name)
    if key in data["clients"]:
        return key, data["clients"][key]
    if not key:
        return None, None
    hits = [k for k in data["clients"] if key in k or k in key]
    if len(hits) == 1:
        return hits[0], data["clients"][hits[0]]
    return None, None


def client_names(data: dict) -> list:
    return [c.get("name", k) for k, c in data["clients"].items()]


def set_client_email(data: dict, name: str, email: str) -> bool:
    client = get_client(data, name)
    if client is None:
        return False
    client["email"] = email.strip()
    return True


# ─────────────────────────── invoices ───────────────────────────

def next_invoice_number(data: dict) -> int:
    """One past the highest number ever issued. Scans existing invoices too,
    so a hand-edited data.json cannot produce a duplicate."""
    highest = int(data["meta"].get("last_invoice_number", INVOICE_START_NUMBER - 1))
    for client in data["clients"].values():
        for inv in client.get("invoices", []):
            try:
                highest = max(highest, int(inv.get("number", 0)))
            except (TypeError, ValueError):
                continue
    return max(highest + 1, INVOICE_START_NUMBER)


def invoice_number_exists(data: dict, number: int):
    """Returns (client_name, invoice) if the number is taken, else (None, None)."""
    for client in data["clients"].values():
        for inv in client.get("invoices", []):
            if int(inv.get("number", -1)) == int(number):
                return client.get("name"), inv
    return None, None


def default_due_date(issue=None) -> date:
    return (parse_date(issue) or today()) + timedelta(days=INVOICE_DUE_DAYS)


def add_invoice(data: dict, client_name: str, invoice: dict) -> dict:
    client = ensure_client(data, client_name)
    client["invoices"].append(invoice)
    try:
        data["meta"]["last_invoice_number"] = max(
            int(data["meta"].get("last_invoice_number", 0)), int(invoice["number"])
        )
    except (TypeError, ValueError, KeyError):
        pass

    project = (invoice.get("project") or "").strip()
    if project and not any(p.get("name") == project for p in client["projects"]):
        client["projects"].append({"name": project, "description": "", "status": "active"})
    return invoice


def find_invoice(data: dict, number):
    """Returns (client_key, client, invoice) or (None, None, None)."""
    try:
        number = int(number)
    except (TypeError, ValueError):
        return None, None, None
    for key, client in data["clients"].items():
        for inv in client.get("invoices", []):
            if int(inv.get("number", -1)) == number:
                return key, client, inv
    return None, None, None


def days_overdue(invoice: dict) -> int:
    """Positive only when unpaid and past due. Paid and cancelled invoices are
    never overdue regardless of date."""
    if invoice.get("status") != "unpaid":
        return 0
    due = parse_date(invoice.get("due_date"))
    if not due:
        return 0
    return max(0, (today() - due).days)


def effective_status(invoice: dict) -> str:
    """'overdue' is derived at read time, never stored — stored state goes
    stale at midnight and nothing runs a nightly job to correct it."""
    status = invoice.get("status", "unpaid")
    if status == "unpaid" and days_overdue(invoice) > 0:
        return "overdue"
    return status


def set_invoice_status(data: dict, number, new_status: str):
    """Returns (ok, message, invoice)."""
    valid = {"paid", "unpaid", "cancelled"}
    if new_status not in valid:
        return False, f"Status must be one of: {', '.join(sorted(valid))}.", None

    _key, client, invoice = find_invoice(data, number)
    if invoice is None:
        return False, f"No invoice #{number} found.", None

    if invoice.get("status") == new_status:
        return False, f"Invoice #{number} is already marked {new_status}.", invoice

    invoice["status"] = new_status
    if new_status == "paid":
        invoice["paid_date"] = iso(today())
    else:
        invoice.pop("paid_date", None)

    return True, f"Invoice #{number} ({client['name']}) marked {new_status}.", invoice


def list_invoices(data: dict, status_filter: str = "all", client_name: str = ""):
    """status_filter: all | unpaid | overdue | paid | cancelled.
    Sorted most-overdue first, since that is the order the freelancer cares about."""
    rows = []
    target = slugify(client_name) if client_name else None

    for key, client in data["clients"].items():
        if target and key != target:
            continue
        for inv in client.get("invoices", []):
            eff = effective_status(inv)
            if status_filter == "unpaid" and eff not in ("unpaid", "overdue"):
                continue
            if status_filter == "overdue" and eff != "overdue":
                continue
            if status_filter in ("paid", "cancelled") and eff != status_filter:
                continue
            rows.append(
                {
                    "number": inv.get("number"),
                    "client": client.get("name"),
                    "client_email": client.get("email", ""),
                    "project": inv.get("project", ""),
                    "total": inv.get("total", 0),
                    "due_date": inv.get("due_date"),
                    "status": eff,
                    "days_overdue": days_overdue(inv),
                    "invoice": inv,
                }
            )

    rows.sort(key=lambda r: (-r["days_overdue"], -(r["number"] or 0)))
    return rows


def outstanding_total(data: dict, client_name: str = "") -> Decimal:
    """Cancelled and paid excluded."""
    total = Decimal("0.00")
    for row in list_invoices(data, "unpaid", client_name):
        total += Decimal(str(row["total"] or 0))
    return total


# ─────────────────────────── proposals & reminders ───────────────────────────

def add_proposal(data: dict, client_name: str, project: str, body: str) -> dict:
    client = ensure_client(data, client_name)
    record = {
        "id": f"prop-{len(client['proposals']) + 1}-{int(datetime.now().timestamp())}",
        "project": project,
        "body": body,
        "created": datetime.now().isoformat(timespec="seconds"),
    }
    client["proposals"].append(record)
    if project and not any(p.get("name") == project for p in client["projects"]):
        client["projects"].append({"name": project, "description": "", "status": "active"})
    return record


def log_reminder(data: dict, client_name: str, invoice_number, tier: str,
                 to_address: str, subject: str, body: str) -> dict:
    client = ensure_client(data, client_name)
    record = {
        "invoice": invoice_number,
        "tier": tier,
        "sent_at": datetime.now().isoformat(timespec="seconds"),
        "to": to_address,
        "subject": subject,
        "body": body,
    }
    client["reminders"].append(record)
    return record


def reminders_for_invoice(data: dict, invoice_number) -> list:
    """Prior reminders on this invoice. A second reminder written as though it
    were the first tells the client their non-response went unnoticed."""
    out = []
    try:
        invoice_number = int(invoice_number)
    except (TypeError, ValueError):
        return out
    for client in data["clients"].values():
        for rem in client.get("reminders", []):
            if int(rem.get("invoice", -1) or -1) == invoice_number:
                out.append(rem)
    out.sort(key=lambda r: r.get("sent_at", ""))
    return out


def client_history(data: dict, name: str):
    key, client = find_client_fuzzy(data, name)
    if client is None:
        return None
    return {
        "name": client.get("name"),
        "email": client.get("email", ""),
        "proposals": client.get("proposals", []),
        "invoices": [
            {**inv, "effective_status": effective_status(inv), "days_overdue": days_overdue(inv)}
            for inv in client.get("invoices", [])
        ],
        "reminders": client.get("reminders", []),
    }


# ─────────────────────────── freelancer profile ───────────────────────────

def get_freelancer(data: dict) -> dict:
    return data["meta"].setdefault(
        "freelancer", {"name": "", "email": "", "phone": "", "payment_details": ""}
    )


def update_freelancer(data: dict, **fields) -> dict:
    profile = get_freelancer(data)
    for key, value in fields.items():
        if value:
            profile[key] = value
    return profile
