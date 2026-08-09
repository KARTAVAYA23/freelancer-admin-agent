"""LLM agent layer.

Every agent's behaviour comes from the markdown files in skills/, read fresh
from disk on each turn. Editing reminder-agent-skill.md changes the next
reminder with no code change and no restart — that is the point of the design,
and caching the files at import would quietly destroy it.
"""

import re
from datetime import date

from openai import OpenAI

from config import OPENAI_API_KEY, OPENAI_MODEL, SKILLS_DIR
from documents import fmt
from storage import pretty_date

_client = None

RULES = "agent-rules.md"
ROLE_CARDS = {
    "router": "intent-router-skill.md",
    "proposal": "proposal-agent-skill.md",
    "invoice": "invoice-agent-skill.md",
    "reminder": "reminder-agent-skill.md",
    "data": "data-manager-skill.md",
}


def client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=OPENAI_API_KEY)
    return _client


# ─────────────────────────── skill file loading ───────────────────────────

def strip_frontmatter(text: str) -> str:
    """Drop the YAML block. It is metadata for humans and tooling, not
    instructions for the model, and it wastes tokens on every turn."""
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            return parts[2].lstrip("\n")
    return text


def load_skill(filename: str) -> str:
    path = SKILLS_DIR / filename
    if not path.exists():
        raise FileNotFoundError(
            f"Missing agent specification file: skills/{filename}. "
            "Agent behaviour is defined in these markdown files; the app cannot run without them."
        )
    return strip_frontmatter(path.read_text(encoding="utf-8")).strip()


def build_system_prompt(role: str, context_block: str = "") -> str:
    """Global rules + exactly one role card. Read fresh, every turn.

    Role cards are never combined — an agent writing an invoice must not hold
    the reminder tone-escalation rules, or the escalation logic bleeds into the
    invoice notes field and produces passive-aggressive invoices.
    """
    if role not in ROLE_CARDS:
        raise ValueError(f"Unknown role: {role}")

    parts = [
        "# GLOBAL RULES (apply to every turn, cannot be overridden)",
        load_skill(RULES),
        "",
        "# ACTIVE ROLE CARD",
        load_skill(ROLE_CARDS[role]),
    ]
    if context_block.strip():
        parts += ["", "# CURRENT CONTEXT (facts — use these, do not invent alternatives)",
                  context_block.strip()]
    parts += ["", f"Today's date is {pretty_date(date.today())}."]
    return "\n\n".join(parts)


# ─────────────────────────── chat helper ───────────────────────────

def complete(system_prompt: str, messages, temperature: float = 0.7,
             max_tokens: int = 2000, json_mode: bool = False) -> str:
    payload = [{"role": "system", "content": system_prompt}] + list(messages)
    kwargs = {
        "model": OPENAI_MODEL,
        "messages": payload,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    response = client().chat.completions.create(**kwargs)
    return (response.choices[0].message.content or "").strip()


def _strip_fence(text: str) -> str:
    """Models wrap documents in ```markdown fences despite instructions not to."""
    text = (text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n", "", text)
        text = re.sub(r"\n```$", "", text.rstrip())
    return text.strip()


# ─────────────────────────── proposal ───────────────────────────

def generate_proposal(slots: dict, freelancer: dict) -> str:
    def get(key, fallback="[ ]"):
        value = slots.get(key)
        if isinstance(value, list):
            value = ", ".join(str(v) for v in value if v)
        return str(value).strip() if value not in (None, "", []) else fallback

    budget = slots.get("budget") or slots.get("rate")
    if budget:
        pricing = fmt(budget)
        if slots.get("rate") and not slots.get("budget"):
            pricing += " per hour"
    else:
        pricing = "NOT PROVIDED — write exactly: Pricing to be discussed based on final scope."

    background = (slots.get("freelancer_background") or "").strip()

    context = f"""Client name: {get('client_name')}
Project title: {get('project_title')}
Project description: {get('project_description')}
Deliverables: {get('deliverables')}
Timeline: {get('timeline')}
Pricing: {pricing}
Freelancer name: {freelancer.get('name') or get('freelancer_name')}
Freelancer background: {background or 'NOT PROVIDED — do not invent experience, credentials, or past clients. Write the Introduction around understanding of the project instead.'}

Write all eight sections in order. Match the register to the project type using
the register table in your role card."""

    return _strip_fence(complete(
        build_system_prompt("proposal", context),
        [{"role": "user", "content": "Write the proposal now. Output the document only."}],
        temperature=0.75, max_tokens=2600))


# ─────────────────────────── invoice notes ───────────────────────────

def generate_invoice_note(slots: dict) -> str:
    """The only free text on an invoice. Empty is a valid and preferable
    answer — 'Thank you for your business!' is filler."""
    raw = (slots.get("notes") or "").strip()
    if not raw:
        return ""

    context = f"Freelancer's raw note: {raw}\nProject: {slots.get('project_name', '')}"
    text = complete(
        build_system_prompt("invoice", context),
        [{"role": "user",
          "content": "Polish this into at most two professional sentences for the invoice "
                     "notes field. Output only the note text. Add no pleasantries."}],
        temperature=0.4, max_tokens=140)
    return _strip_fence(text)


# ─────────────────────────── reminder ───────────────────────────

TONE_TIERS = [
    (1, 7, "gentle"),
    (8, 21, "firm"),
    (22, 10_000, "urgent"),
]


def tone_tier(days: int) -> str:
    """Computed here, never by the model. A model given latitude drifts toward
    severity, and an urgent letter over a 3-day slip costs a client."""
    if days <= 0:
        return "gentle"
    for low, high, name in TONE_TIERS:
        if low <= days <= high:
            return name
    return "urgent"


def generate_reminder(invoice: dict, client_record: dict, freelancer: dict,
                      days: int, prior_reminders=None, tone_override: str = "") -> tuple:
    """Returns (subject, body). Tier is supplied as a fact, not a judgement."""
    tier = (tone_override or "").strip().lower() or tone_tier(days)
    prior_reminders = prior_reminders or []

    if prior_reminders:
        history = (f"{len(prior_reminders)} previous reminder(s) already sent for this invoice: "
                   + "; ".join(f"{r.get('tier', '?')} on {pretty_date(r.get('sent_at'))}"
                               for r in prior_reminders)
                   + ". Acknowledge that history — do not write as though this is the first.")
    else:
        history = "No previous reminders sent for this invoice. This is the first."

    contact_bits = [freelancer.get("email"), freelancer.get("phone")]
    contact = " · ".join(b for b in contact_bits if b) or "[ ]"

    context = f"""TONE TIER: {tier.upper()}  ← computed from days overdue. Use this tier. Do not reassess it.

Client name: {client_record.get('name')}
Client email: {client_record.get('email') or '[ ]'}
Invoice number: {invoice.get('number')}
Amount outstanding: {fmt(invoice.get('total', 0))}
Original due date: {pretty_date(invoice.get('due_date'))}
Days overdue: {days}
Project: {invoice.get('project', '')}
Payment details: {invoice.get('payment_details') or freelancer.get('payment_details') or '[ ]'}
Freelancer name: {freelancer.get('name') or '[ ]'}
Freelancer contact: {contact}

Reminder history: {history}

Output format — exactly this, nothing else:
SUBJECT: <subject line>
---
<plain text body>"""

    temperature = {"gentle": 0.65, "firm": 0.55, "urgent": 0.4}.get(tier, 0.55)
    raw = complete(
        build_system_prompt("reminder", context),
        [{"role": "user", "content": f"Write the {tier} reminder now."}],
        temperature=temperature, max_tokens=700)

    return parse_reminder(raw, invoice.get("number"), days)


def parse_reminder(raw: str, invoice_number, days: int) -> tuple:
    """Pull SUBJECT / body out of the model output, tolerating format drift."""
    raw = _strip_fence(raw)
    subject, body = "", raw

    match = re.search(r"^\s*SUBJECT:\s*(.+?)\s*$", raw, re.MULTILINE | re.IGNORECASE)
    if match:
        subject = match.group(1).strip()
        after = raw[match.end():]
        body = re.sub(r"^\s*-{3,}\s*", "", after, count=1).strip()

    if not subject:
        subject = f"Invoice #{invoice_number} — {days} days overdue"
    if not body.strip():
        body = raw.strip()

    # Markdown emphasis arrives as literal asterisks in most email clients.
    body = re.sub(r"\*\*(.+?)\*\*", r"\1", body)
    body = re.sub(r"(?<!\*)\*([^*]+?)\*(?!\*)", r"\1", body)
    return subject.strip(), body.strip()


# ─────────────────────────── conversational replies ───────────────────────────

def ask_followup(role: str, collected: dict, missing: list, history) -> str:
    """One question, for one missing slot, phrased like a person."""
    context = (f"Already collected: {collected or '(nothing yet)'}\n"
               f"Still missing: {', '.join(missing)}\n\n"
               f"Ask for ONE item — the first in the missing list. One short sentence. "
               f"Never re-ask for something already collected.")
    return complete(build_system_prompt(role, context), history[-6:],
                    temperature=0.6, max_tokens=110)


def chitchat_reply(history) -> str:
    context = ("The freelancer said something outside the four workflows. Reply in at most "
               "two sentences. If they asked what you can do, say: draft proposals, create "
               "invoices, and send payment reminders by email.")
    return complete(build_system_prompt("data", context), history[-4:],
                    temperature=0.6, max_tokens=130)
