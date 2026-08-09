---
name: "freelancer-admin-agent"
description: "Conversational admin assistant for freelancers. Drafts client proposals from a plain-language brief, generates numbered invoices with tax and line-item math, writes overdue-payment reminders whose tone escalates with how late the invoice is, and sends those reminders to the client via Gmail SMTP. Use when the user says: 'write a proposal for', 'create an invoice for', 'remind <client> about', 'what's still unpaid', 'mark invoice #N as paid', or describes freelance client admin work in natural language. Requires: OpenAI API key and a Gmail App Password in .env."
license: MIT
metadata:
  version: 1.0.0
  category: business-automation
  entrypoint: streamlit run app.py
---

# Freelancer Admin Agent

A single conversational surface that absorbs the three unpaid tasks eating a freelancer's week: writing proposals, cutting invoices, and chasing late payments.

The freelancer never navigates to a "proposals page." They type what they need. The router picks the agent, the agent asks for whatever is missing, and the output lands as a downloadable document or a sent email.

---

## How This Skill Is Organized

```
freelancer-admin-agent/
  SKILL.md                       ← you are here (dispatch table + contracts)
  skills/
    agent-rules.md               ← global rules — loaded on EVERY turn, all agents
    intent-router-skill.md       ← classifies the message, extracts slots
    proposal-agent-skill.md      ← role card: proposal writing
    invoice-agent-skill.md       ← role card: invoice construction
    reminder-agent-skill.md      ← role card: overdue reminders + tone tiers
    data-manager-skill.md        ← role card: storage queries and status changes
  app.py  agents.py  intent.py  storage.py  documents.py  mailer.py
  .env                           ← blank — your keys go here
```

### Loading order for every turn

1. `skills/agent-rules.md` — always, no exceptions
2. `skills/intent-router-skill.md` — to classify the incoming message
3. Exactly **one** role card from the dispatch table below

Three files per turn. Never more. Role cards are mutually exclusive — an agent that is writing an invoice must not also be holding the reminder tone rules in context, because tone escalation logic bleeds into invoice notes and produces passive-aggressive invoices.

Files are read **fresh from disk on every turn**, not cached at import. Behavior lives in markdown, not in Python string literals. Editing `reminder-agent-skill.md` changes how the bot writes reminders on the very next message, with no code change and no restart.

---

## Dispatch Table

| Detected intent | Role card to load | Terminal output |
|---|---|---|
| `PROPOSAL` | `skills/proposal-agent-skill.md` | 8-section proposal → PDF + DOCX |
| `INVOICE` | `skills/invoice-agent-skill.md` | Numbered invoice → PDF, status `unpaid` |
| `REMINDER` | `skills/reminder-agent-skill.md` | Draft → freelancer confirms → Gmail send |
| `QUERY` | `skills/data-manager-skill.md` | Table of matching records |
| `STATUS_UPDATE` | `skills/data-manager-skill.md` | Confirmation + updated record |
| `CHITCHAT` | none — reply directly, ≤2 sentences | Plain text |

### Trigger phrases

**PROPOSAL** — "write a proposal", "I need a proposal for", "new client wants", "pitch for", "quote for a project", "draft a proposal"

**INVOICE** — "create an invoice", "bill <client>", "I worked N hours", "invoice for the <project> project", "generate invoice"

**REMINDER** — "send a reminder", "they haven't paid", "follow up on invoice", "chase <client>", "second reminder", "they're N weeks late"

**QUERY** — "what's unpaid", "show me everything for <client>", "list my invoices", "how much is outstanding", "what did I send to"

**STATUS_UPDATE** — "mark invoice #N as paid", "<client> paid", "cancel invoice", "mark as overdue"

---

## The Three Agents

### 1. Proposal Agent

Takes a one-line brief and returns a document a freelancer can send without editing.

**Required slots:** client name, project title, project description, deliverables, timeline, freelancer name
**Optional slots:** budget/rate, freelancer skills and background

**Non-negotiable:** the eight sections — Introduction, Project Understanding, Proposed Approach, Deliverables, Timeline, Pricing, Terms, Closing — appear in that order, every time. Pricing renders as "Pricing to be discussed" when no budget was given; the section is never dropped.

**Register-matching is the whole job.** A logo identity proposal and a payment-gateway integration proposal must not read like the same document with nouns swapped. See the role card for the register table.

### 2. Invoice Agent

Deterministic math, LLM-free arithmetic.

**Required slots:** client name, project name, work items, hours per item, rate per item, payment details
**Auto-filled:** invoice number (sequential), invoice date (today), due date (+15 days)
**Optional slots:** tax percentage, notes to client

**The arithmetic never touches the model.** Line subtotals, tax, and grand total are computed in `documents.py` with `Decimal` and `ROUND_HALF_UP` at 2 places. The LLM writes the notes field and nothing else numeric. An LLM that "helps" with a total is a bug — a freelancer who sends a client an invoice that does not add up loses the client, not the argument.

**Numbering** is sequential from the highest number in storage, starting at 1001. The freelancer may override with a custom number; collisions are rejected with the conflicting invoice shown.

### 3. Reminder Agent

Tone escalates with days overdue. Three tiers, hard cutoffs:

| Days overdue | Tier | Posture |
|---|---|---|
| 1–7 | **Gentle** | Assumes it slipped their mind. Warm, no pressure, no deadline. |
| 8–21 | **Firm** | Polite but unambiguous. Names the overdue status, requests a date. |
| 22+ | **Urgent** | Professional, not hostile. States consequences — work pause, late fees. |

Tier is computed in Python from `(today − due_date).days`, then passed to the model as a fact. **The model does not decide the tier.** Letting it "read the room" produces urgent letters for 3-day slips, which costs freelancers relationships.

**Every reminder must contain:** personalised greeting with the client's name, invoice number, amount outstanding, original due date, exact days overdue, a payment request, payment details or a pointer to the original invoice, and the freelancer's sign-off with contact details.

**Send flow is confirm-gated.** Draft renders in chat → freelancer reads it → freelancer clicks **Send via Gmail** → SMTP send → timestamp logged to the client record. The system never sends on inference. "Yes, send it" typed in chat is not a click; the button is the only send path.

---

## Data Contract

Storage is a single JSON file, `storage/data.json`, keyed by client. Every write is atomic — serialize to a temp file in the same directory, then `os.replace`. A half-written invoice file is worse than a missing one.

```json
{
  "clients": {
    "peakform": {
      "name": "PeakForm",
      "email": "contact@peakform.com",
      "company": "PeakForm Fitness",
      "phone": "",
      "projects":  [{ "name": "...", "description": "...", "status": "active" }],
      "proposals": [{ "id": "...", "project": "...", "body": "...", "created": "ISO8601" }],
      "invoices":  [{
        "number": 1043, "project": "...", "issue_date": "...", "due_date": "...",
        "line_items": [{ "description": "...", "hours": 18.0, "rate": 100.00, "subtotal": 1800.00 }],
        "subtotal": 1800.00, "tax_rate": 0.0, "tax_amount": 0.0, "total": 1800.00,
        "status": "unpaid", "notes": "", "payment_details": "..."
      }],
      "reminders": [{ "invoice": 1043, "tier": "firm", "sent_at": "ISO8601",
                      "to": "contact@peakform.com", "subject": "...", "body": "..." }]
    }
  },
  "meta": { "last_invoice_number": 1043, "freelancer": { "name": "", "email": "", "phone": "" } }
}
```

Client keys are slugified names — lowercase, non-alphanumerics collapsed to nothing. "Acme Corp", "acme corp", and "ACME Corp." all resolve to `acmecorp`, so the freelancer's inconsistent capitalisation never forks a client into three records.

**Status values:** `unpaid`, `paid`, `overdue`. `overdue` is derived at read time, never stored — an invoice is overdue when `status == "unpaid" and due_date < today`. Storing it would require a cron job to stay honest.

---

## Slot Filling

When a required slot is missing, ask for **one** thing per turn, in plain language, and remember every slot already collected.

The failure mode to avoid:

> ❌ "Please provide: client name, project title, description, deliverables, and timeline."

That is a form with a chat skin. Ask one question, use what they said to shape the next:

> ✅ **Freelancer:** I need a proposal for a logo design project
> ✅ **Bot:** Sure — who's the client?
> ✅ **Freelancer:** A startup called BrightLeaf
> ✅ **Bot:** Got it. Just the logo, or brand guidelines and identity materials too?

Never re-ask for a slot already in the buffer. Never ask for optional slots when every required slot is filled — generate, and let the freelancer refine after seeing output.

---

## Grounding Rules

Invented facts on a client-facing document are the highest-severity failure this system can produce.

- Never invent a client's company details, industry, team size, or history.
- Never invent the freelancer's credentials, past clients, or years of experience. If background was not supplied, write the proposal without it.
- Never invent amounts, dates, or invoice numbers — every number on an invoice traces to a slot the freelancer filled or a computed field.
- When a proposal needs a detail that was never provided, write around it or leave a clearly-marked `[ ]` placeholder. Never fabricate to fill the gap.

---

## Setup

1. Open `.env` and paste your key after `OPENAI_API_KEY=` — the field is blank and waiting.
2. Add `GMAIL_SENDER` (your Gmail address) and `GMAIL_APP_PASS` (16-character App Password, **not** your account password).
3. `pip install -r requirements.txt`
4. `streamlit run app.py`

Generating a Gmail App Password: enable 2-Step Verification on your Google account → Google Account → Security → App Passwords → create one for "Mail" → copy the 16 characters into `.env`.

The app refuses to start with a clear on-screen message if `OPENAI_API_KEY` is blank. Gmail credentials are checked lazily — proposals and invoices work without them; only sending a reminder requires them.
