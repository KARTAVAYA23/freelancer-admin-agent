# Freelancer Admin Agent

A conversational admin assistant for freelancers. Drafts proposals, cuts invoices, and chases late payments over Gmail — through one chat box.

---

## Setup in four steps

**1. Put your keys in `.env`**

Open `.env` in the project root. The fields are blank and waiting:

```
OPENAI_API_KEY=      ← paste your key here
GMAIL_SENDER=        ← your Gmail address
GMAIL_APP_PASS=      ← 16-character App Password
FREELANCER_NAME=
FREELANCER_EMAIL=
FREELANCER_PHONE=
```

No quotes, no spaces around the `=`.

**2. Generate a Gmail App Password**

This is not your Google account password. Your account password will not work and should never be in a file.

1. Turn on 2-Step Verification for your Google account
2. Go to **Google Account → Security → App Passwords**
3. Create one for "Mail" — name it anything
4. Copy the 16 characters into `GMAIL_APP_PASS`

**3. Install**

```bash
pip install -r requirements.txt
```

**4. Run**

```bash
streamlit run app.py
```

Opens at `http://localhost:8501`. Add your name and payment details in the sidebar before generating anything — they appear on every document.

---

## What it does

Type what you need. No menus, no forms.

| You type | What happens |
|---|---|
| "I need a proposal for a 3-week social campaign for PeakForm" | Asks for whatever's missing, then writes an 8-section proposal → PDF + Word |
| "Create an invoice for 18 hours at $100/hr for PeakForm" | Numbered invoice, math done in Python → PDF |
| "PeakForm still hasn't paid" | Picks the tone by how late it is, drafts the email, waits for you to press send |
| "What's still unpaid?" | Every outstanding invoice, most-overdue first, with a total |
| "Mark invoice #1043 as paid" | Updates the record, names the invoice back so you can catch a wrong guess |

### Proposals

Eight sections every time: Introduction, Project Understanding, Proposed Approach, Deliverables, Timeline, Pricing, Terms, Closing.

The register changes with the work. A logo identity proposal and a payment-gateway integration proposal are written differently — different vocabulary, different rhythm — because a client in either field can tell within a paragraph when they've been sent a template.

No budget given? Pricing reads "Pricing to be discussed based on final scope." The section never disappears and a number is never invented.

### Invoices

**The LLM never touches the arithmetic.** Line subtotals, tax, and grand total are computed in `documents.py` with `Decimal` and `ROUND_HALF_UP`, quantized at every step.

Language models produce arithmetic that is usually right, and "usually" is the wrong reliability class for a document a client checks against their bank transfer. A freelancer who sends an invoice where 18 × 100 came out as $1,750 doesn't get a correction — they get a client who quietly stops replying.

Numbers run sequentially from 1001, derived from the highest number in storage so a hand-edited data file can't produce a duplicate. Override with your own number if you prefer; collisions are refused with the conflicting invoice shown.

### Payment reminders

Tone escalates with how late the invoice is. The tier is **computed in Python**, not chosen by the model:

| Days overdue | Tier | Posture |
|---|---|---|
| 1–7 | Gentle | Assumes it slipped their mind. Warm, no deadline. |
| 8–21 | Firm | Direct. Names the overdue status, asks for a payment date. |
| 22+ | Urgent | Professional. States one consequence, gives a deadline. |

A model given latitude on tone drifts toward severity, because "overdue invoice" reads as conflict. That drift sends urgent letters over three-day slips and costs freelancers clients.

**Nothing sends without a button press.** The draft renders in chat, you can edit it, and only then does the Send button do anything. Typing "yes, send it" doesn't send it.

---

## Behaviour lives in markdown, not Python

The six files in `skills/` define how every agent thinks. They're read **fresh from disk on every turn** — no caching, no restart needed.

```
skills/
  agent-rules.md             global rules — every turn, every agent
  intent-router-skill.md     classification + slot extraction
  proposal-agent-skill.md    proposal role card
  invoice-agent-skill.md     invoice role card
  reminder-agent-skill.md    reminder role card + tone tiers
  data-manager-skill.md      storage query role card
```

Exactly three files load per turn: global rules, the router, and one role card. Role cards are mutually exclusive — an agent writing an invoice must not be holding the reminder tone rules, or escalation logic bleeds into the invoice notes and produces passive-aggressive invoices.

**Try it:** open `skills/reminder-agent-skill.md`, change the Gentle tier to open with "Quick one —", save, and send your next reminder. The change lands immediately. No code edited, no restart.

---

## Files

| File | Does |
|---|---|
| `app.py` | Streamlit UI, session state, intent handlers, artifact rendering |
| `agents.py` | Loads skill files, assembles system prompts, calls the LLM, computes tone tier |
| `intent.py` | Keyword prefilter, LLM classification, slot coercion and merging |
| `storage.py` | Atomic JSON persistence, client slugs, invoice numbering, status derivation |
| `documents.py` | Decimal arithmetic, invoice PDF, proposal PDF + DOCX |
| `mailer.py` | Gmail SMTP with typed, actionable error messages |
| `config.py` | `.env` loading and validation |
| `theme.py` | CSS and layout fragments |
| `storage/data.json` | Your data — created on first save |

---

## Data

One JSON file, keyed by client. "Acme Corp", "acme corp", and "ACME Corp." all resolve to the same record, so inconsistent capitalisation never forks a client into three.

Statuses are `unpaid`, `paid`, and `cancelled`. **`overdue` is derived at read time**, never stored — an invoice is overdue when it's unpaid and past due. Storing it would need a nightly job to stay honest, and it would silently be wrong every morning until that job ran.

Cancelled invoices are excluded from totals but never deleted. Gaps in the numbering sequence look like destroyed records to anyone auditing later.

Every write is atomic: serialize to a temp file, then `os.replace`. A crash mid-write leaves the previous file intact rather than truncated.

---

## Troubleshooting

**"No API key found"** — `OPENAI_API_KEY` in `.env` is blank. Paste the key, save, restart.

**"Gmail rejected the login"** — the App Password is wrong, expired, or was made for a different account. Generate a fresh one at Google Account → Security → App Passwords. Don't disable security settings to work around this; it isn't the problem.

**"GMAIL_APP_PASS is 20 characters"** — you pasted your account password. App Passwords are exactly 16 characters and are generated separately.

**Reminders unavailable, everything else works** — Gmail is checked lazily by design. Proposals and invoices don't need it.

**Numbers look wrong** — they aren't coming from the model. Check the `hours` and `rate` you gave; `documents.compute_invoice()` is the only thing that does arithmetic.

---

## Requirements

Python 3.9+, plus `streamlit`, `openai`, `python-dotenv`, `reportlab`, `python-docx`. Storage is a local JSON file — no database, no cloud.
