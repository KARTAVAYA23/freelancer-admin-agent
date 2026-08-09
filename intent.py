"""Intent detection: keyword prefilter, then LLM classification.

The prefilter exists because a bare "yes" or "$600" answering a pending question
should not cost an API call to classify — and because an LLM asked to classify
"yes" with no context will invent an intent for it.
"""

import json
import re

from agents import build_system_prompt, complete

INTENTS = {"PROPOSAL", "INVOICE", "REMINDER", "QUERY", "STATUS_UPDATE", "CHITCHAT"}

REQUIRED_SLOTS = {
    "PROPOSAL": ["client_name", "project_title", "project_description",
                 "deliverables", "timeline"],
    "INVOICE": ["client_name", "project_name", "work_items"],
    "REMINDER": ["client_name"],
    "QUERY": [],
    "STATUS_UPDATE": ["invoice_number", "new_status"],
    "CHITCHAT": [],
}

SLOT_QUESTIONS = {
    "client_name": "Who's the client?",
    "project_title": "What should I call this project?",
    "project_description": "What does the project involve?",
    "deliverables": "What are you delivering?",
    "timeline": "What's the timeline?",
    "project_name": "Which project is this for?",
    "work_items": "How many hours did you log, and at what rate?",
    "invoice_number": "Which invoice number?",
    "new_status": "What status should it be set to?",
}

# Unambiguous phrasings that never need the model.
FAST_PATTERNS = [
    (r"\bmark\s+(?:invoice\s*)?#?(\d{3,6})\s+as\s+(paid|unpaid|cancelled|canceled)\b",
     "STATUS_UPDATE"),
    (r"\bwhat(?:'s| is)?\s+(?:still\s+)?(?:unpaid|outstanding|owed|due)\b", "QUERY"),
    (r"\b(?:show|list)\s+(?:me\s+)?(?:all\s+)?(?:my\s+)?(?:unpaid|outstanding|overdue)\b",
     "QUERY"),
    (r"^\s*(?:hi|hey|hello|thanks|thank you|ok|okay|cool|nice|great)[!.\s]*$", "CHITCHAT"),
]


def fast_classify(message: str):
    text = (message or "").strip().lower()
    for pattern, intent in FAST_PATTERNS:
        match = re.search(pattern, text)
        if match:
            slots = {}
            if intent == "STATUS_UPDATE" and match.groups():
                slots["invoice_number"] = int(match.group(1))
                status = match.group(2)
                slots["new_status"] = "cancelled" if status.startswith("cancel") else status
            elif intent == "QUERY":
                slots["query_filter"] = "unpaid"
            return {"intent": intent, "confidence": 0.95, "slots": slots,
                    "reasoning": "keyword prefilter"}
    return None


def coerce_slots(slots: dict) -> dict:
    """Models emit '$1,800' and '18 hours' despite the schema asking for numbers."""
    if not isinstance(slots, dict):
        return {}
    out = {}

    for key, value in slots.items():
        if value in (None, "", [], {}):
            continue

        if key in ("budget", "rate", "hours", "tax_rate"):
            if isinstance(value, str):
                cleaned = re.sub(r"[^\d.]", "", value)
                if not cleaned:
                    continue
                try:
                    value = float(cleaned)
                except ValueError:
                    continue
            try:
                value = float(value)
            except (TypeError, ValueError):
                continue

        elif key in ("invoice_number", "days_overdue"):
            if isinstance(value, str):
                digits = re.sub(r"[^\d]", "", value)
                if not digits:
                    continue
                value = digits
            try:
                value = int(value)
            except (TypeError, ValueError):
                continue

        elif key == "deliverables" and isinstance(value, str):
            value = [p.strip() for p in re.split(r",|;|\band\b", value) if p.strip()]

        elif key == "new_status" and isinstance(value, str):
            low = value.strip().lower()
            value = "cancelled" if low.startswith("cancel") else low
            if value not in ("paid", "unpaid", "cancelled"):
                continue

        out[key] = value

    return out


def detect(message: str, history=None, pending_intent: str = "", pending_slot: str = ""):
    """Returns a dict: intent, confidence, slots, reasoning.

    A message answering a pending question inherits the open intent — a bare
    'BrightLeaf' replying to 'who's the client?' is never CHITCHAT.
    """
    history = history or []

    fast = fast_classify(message)
    if fast and not pending_intent:
        return fast

    context = ""
    if pending_intent:
        context = (f"An intent is already open: {pending_intent}. "
                   f"The previous bot turn asked for: {pending_slot or 'a missing detail'}. "
                   f"If this message answers that question, keep intent={pending_intent} and "
                   f"extract the answer into the matching slot. Only switch intent if the "
                   f"freelancer has clearly changed subject.")

    recent = [m for m in history[-6:] if m.get("role") in ("user", "assistant")]
    payload = [{"role": m["role"], "content": str(m.get("content", ""))[:1200]} for m in recent]
    payload.append({"role": "user", "content": message})

    try:
        raw = complete(build_system_prompt("router", context), payload,
                       temperature=0.0, max_tokens=420, json_mode=True)
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError, ValueError):
        return {"intent": pending_intent or "CHITCHAT", "confidence": 0.3, "slots": {},
                "reasoning": "router returned unparseable output"}
    except Exception as exc:
        return {"intent": pending_intent or "CHITCHAT", "confidence": 0.0, "slots": {},
                "reasoning": f"router error: {exc}"}

    intent = str(parsed.get("intent", "")).upper().strip()
    if intent not in INTENTS:
        intent = pending_intent or "CHITCHAT"

    try:
        confidence = max(0.0, min(1.0, float(parsed.get("confidence", 0.5))))
    except (TypeError, ValueError):
        confidence = 0.5

    return {
        "intent": intent,
        "confidence": confidence,
        "slots": coerce_slots(parsed.get("slots", {})),
        "reasoning": str(parsed.get("reasoning", ""))[:200],
    }


def missing_slots(intent: str, collected: dict) -> list:
    """Which required slots are still empty."""
    required = REQUIRED_SLOTS.get(intent, [])
    return [s for s in required if not collected.get(s)]


def merge_slots(existing: dict, new: dict) -> dict:
    """New values win, but a new blank never erases a collected value."""
    merged = dict(existing or {})
    for key, value in (new or {}).items():
        if value not in (None, "", [], {}):
            merged[key] = value
    return merged


def build_work_items(slots: dict):
    """Normalise the several shapes freelancers describe work in.

    A flat fee with no hours becomes one line at hours=1 — forcing fixed-price
    work into an hourly breakdown misrepresents the engagement.
    """
    items = slots.get("work_items")
    if isinstance(items, list) and items:
        normalised = []
        for item in items:
            if not isinstance(item, dict):
                continue
            hours = item.get("hours")
            rate = item.get("rate")
            if rate in (None, ""):
                continue
            normalised.append({
                "description": (item.get("description")
                                or slots.get("project_name")
                                or "Professional services"),
                "hours": float(hours) if hours not in (None, "") else 1.0,
                "rate": float(rate),
            })
        if normalised:
            return normalised

    hours = slots.get("hours")
    rate = slots.get("rate")
    if hours and rate:
        return [{
            "description": slots.get("project_name") or slots.get("project_title")
                           or "Professional services",
            "hours": float(hours),
            "rate": float(rate),
        }]

    budget = slots.get("budget")
    if budget and not rate:
        return [{
            "description": slots.get("project_name") or slots.get("project_title")
                           or "Professional services",
            "hours": 1.0,
            "rate": float(budget),
        }]

    return []
