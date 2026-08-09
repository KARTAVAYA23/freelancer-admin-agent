# Architecture

Covers the seven documentation points required by the project brief.

---

## 1. System architecture overview

```
                        ┌──────────────────────────┐
   freelancer types ──► │  app.py — Streamlit UI   │
                        │  session state, handlers │
                        └────────────┬─────────────┘
                                     │
                        ┌────────────▼─────────────┐
                        │  intent.py               │
                        │  prefilter → LLM router  │
                        │  → {intent, slots}       │
                        └────────────┬─────────────┘
                                     │
             ┌───────────────┬───────┴───────┬───────────────┐
             ▼               ▼               ▼               ▼
        PROPOSAL         INVOICE         REMINDER      QUERY / STATUS
             │               │               │               │
             ▼               ▼               ▼               ▼
      ┌──────────────────────────────────────────────────────────┐
      │  agents.py — loads skills/*.md FRESH, builds prompt,      │
      │  calls OpenAI, computes tone_tier()                       │
      └───────┬──────────────────┬─────────────────┬─────────────┘
              │                  │                 │
      ┌───────▼──────┐  ┌────────▼───────┐  ┌──────▼──────┐
      │ documents.py │  │   mailer.py    │  │  storage.py │
      │ Decimal math │  │  Gmail SMTP    │  │ atomic JSON │
      │ PDF / DOCX   │  │  (button-gated)│  │             │
      └──────────────┘  └────────────────┘  └─────────────┘
```

**Layer responsibilities**

| Layer | Owns | Never does |
|---|---|---|
| `app.py` | UI, session state, orchestration | Arithmetic, prompt text, SMTP |
| `intent.py` | Classification, slot extraction | Document generation |
| `agents.py` | Prompt assembly, LLM calls, tone tier | Currency math, file I/O for data |
| `documents.py` | All arithmetic, PDF/DOCX rendering | LLM calls |
| `storage.py` | Persistence, numbering, status derivation | LLM calls, rendering |
| `mailer.py` | SMTP only | Deciding *whether* to send |
| `skills/*.md` | All agent behaviour and voice | — |

The load-bearing separation is that **`documents.py` and `agents.py` never call each other for numbers**. Arithmetic and language generation are kept apart so a model that drifts cannot alter a figure on a client-facing document.

---

## 2. Intent detection and routing

Two stages, cheapest first.

### Stage 1 — keyword prefilter (`intent.fast_classify`)

Regex patterns match unambiguous phrasings and return immediately with confidence 0.95:

```python
r"\bmark\s+(?:invoice\s*)?#?(\d{3,6})\s+as\s+(paid|unpaid|cancelled)\b"  → STATUS_UPDATE
r"\bwhat(?:'s| is)?\s+(?:still\s+)?(?:unpaid|outstanding|owed)\b"        → QUERY
r"^\s*(?:hi|hey|thanks|ok)[!.\s]*$"                                     → CHITCHAT
```

This exists for two reasons: "mark invoice #1042 as paid" is fully determined and shouldn't cost an API call, and an LLM asked to classify a bare "thanks" with no context will invent an intent for it.

The prefilter is **skipped when an intent is already open**, because "ok" mid-conversation may be answering a pending question.

### Stage 2 — LLM classification (`intent.detect`)

`skills/intent-router-skill.md` is injected as the system prompt, the last six turns plus the new message as history, called at `temperature=0.0` in JSON mode:

```json
{"intent": "INVOICE", "confidence": 0.97,
 "slots": {"client_name": "PeakForm", "hours": 18, "rate": 100},
 "reasoning": "Past-tense completed work with explicit hours and rate."}
```

### Disambiguation rules that carry weight

| Rule | Example |
|---|---|
| Tense separates PROPOSAL from INVOICE | "I'm going to do 20 hours" → PROPOSAL · "I did 20 hours" → INVOICE |
| The object of "send" decides | "send them the invoice" → INVOICE · "send them a reminder" → REMINDER |
| Overdue framing beats invoice vocabulary | "the invoice is three weeks late" → REMINDER |
| Read vs. write separates QUERY from STATUS_UPDATE | "is #1042 paid?" → QUERY · "#1042 is paid" → STATUS_UPDATE |
| Follow-up answers inherit the open intent | "BrightLeaf" after "who's the client?" → PROPOSAL, not CHITCHAT |

### Routing and slot merging

`app.py` maps intent → handler. Before dispatch, new slots merge into the session buffer:

```python
merged = dict(existing)
for k, v in new.items():
    if v not in (None, "", [], {}):   # a blank never erases a collected value
        merged[k] = v
```

If the detected intent differs from the open one, the buffer is **cleared** — carrying proposal slots into an invoice would silently mis-bill.

`missing_slots()` compares the buffer against `REQUIRED_SLOTS`. Non-empty → ask one question, store `pending_intent` and `pending_slot`, return. Empty → generate.

---

## 3. Proposal generation

### Prompt assembly

Three parts, assembled fresh on every turn in `agents.build_system_prompt("proposal", context)`:

1. `skills/agent-rules.md` — grounding, tone, output discipline
2. `skills/proposal-agent-skill.md` — eight sections, register table, length, constraints
3. A context block of the collected slots, as facts

YAML frontmatter is stripped before injection — it's metadata for tooling, not instruction, and it would cost tokens on every turn.

### The context block

```
Client name: PeakForm
Project title: Social Media Campaign
Deliverables: 12 posts, 4 reels, content calendar
Timeline: 3 weeks
Pricing: $1,800.00
Freelancer background: NOT PROVIDED — do not invent experience, credentials, or past
clients. Write the Introduction around understanding of the project instead.
```

Absent optional slots carry an **explicit instruction not to invent**. A silent omission invites the model to fill the gap with plausible-sounding credentials; a stated prohibition does not.

### Structure

Eight sections, fixed order, every time. Pricing renders as "Pricing to be discussed based on final scope" when no budget exists — the section never disappears, because a client scanning for price and finding no heading assumes the proposal is incomplete.

### Register matching

The register table in the role card maps project type → vocabulary and rhythm. Brand work gets *direction, identity, mark, refine*; technical work gets *architecture, integration, staging, handover*. One house voice across every discipline is the single biggest quality failure in generated proposals, and it's detectable in a paragraph.

`temperature=0.75` — high enough for varied prose, low enough to stay on-brief.

---

## 4. Invoice calculation and numbering

### The arithmetic rule

**No number on an invoice comes from the LLM.** The model writes the notes field and nothing else. `documents.compute_invoice()` is the only arithmetic path:

```python
for item in line_items:
    hours      = D(item["hours"])
    rate       = money(item["rate"])          # quantize to 2 places
    line_total = money(hours * rate)          # quantize again
    subtotal  += line_total

subtotal   = money(subtotal)
tax_amount = money(subtotal * (D(tax_rate) / Decimal("100")))
total      = money(subtotal + tax_amount)
```

`Decimal` throughout, `ROUND_HALF_UP`, quantized **at every step** rather than once at the end — rounding once at the end lets error accumulate across many line items and produces a total that disagrees with the visible column.

Floats are never used for currency anywhere in the system. `0.1 + 0.2 != 0.3`, and a client with a spreadsheet will find the cent.

Verified: `12.5h × $85 + 3.25h × $85 + 1h × $120` at `7.5%` = subtotal **$1,458.75**, tax **$109.41**, total **$1,568.16**.

### Numbering

`storage.next_invoice_number()` returns one past the highest number found, scanning both `meta.last_invoice_number` **and every stored invoice**. Scanning the invoices too means a hand-edited `data.json` cannot produce a duplicate.

Starts at 1001. Increments only on successful save — a failed generation doesn't burn a number and leave a gap that looks like a deleted invoice.

Custom overrides allowed. `invoice_number_exists()` refuses collisions and shows the conflicting invoice:

> Invoice #1042 already exists for TechStart, issued 12 March. Give me a different number.

### Defaults

Issue date = today. Due date = issue + `INVOICE_DUE_DAYS` (15). Status = `unpaid`, always — even if the freelancer says they were paid up front, that's a status update *after* creation, so the record shows both events.

---

## 5. Reminder tone determination

### Computed, not judged

```python
TONE_TIERS = [(1, 7, "gentle"), (8, 21, "firm"), (22, 10_000, "urgent")]

def tone_tier(days: int) -> str:
    if days <= 0:
        return "gentle"
    for low, high, name in TONE_TIERS:
        if low <= days <= high:
            return name
    return "urgent"
```

`days = (today - due_date).days`, computed in `storage.days_overdue()`. Paid and cancelled invoices always return 0.

The tier is passed to the model as a fact:

```
TONE TIER: FIRM  ← computed from days overdue. Use this tier. Do not reassess it.
```

**Why the model doesn't decide:** a model given latitude drifts toward severity, because "overdue invoice" reads as conflict in the training distribution. That drift sends urgent letters over three-day slips, which costs freelancers relationships over what was usually an unopened email.

An explicit freelancer instruction — "make it softer, they're a good client" — overrides the computed tier. Their read on the relationship beats the calendar.

### Temperature per tier

| Tier | Temp | Why |
|---|---|---|
| gentle | 0.65 | Warmth benefits from variation |
| firm | 0.55 | Balanced |
| urgent | 0.40 | Consequences must be stated precisely, not creatively |

### Escalation awareness

`storage.reminders_for_invoice()` returns prior reminders, and the count and dates go into the context block. A second reminder written as though it were the first tells the client their non-response went unnoticed.

---

## 6. Gmail integration

### Setup

Credentials live in `.env`, loaded once by `config.py`:

```
GMAIL_SENDER=yourname@gmail.com
GMAIL_APP_PASS=abcdefghijklmnop
```

An App Password — not the account password — requires 2-Step Verification, then Google Account → Security → App Passwords → Mail.

`config._clean()` strips whitespace and stray quote marks, because keys pasted with a trailing newline or wrapped in quotes produce auth failures that look like bad keys. Display spaces in App Passwords are stripped too.

### Preflight

`mailer.preflight()` checks before composing anything:

- Both fields present
- `GMAIL_SENDER` is a valid address
- `GMAIL_APP_PASS` is exactly 16 characters — a length mismatch means the account password was pasted, which is worth saying explicitly

### Sending

```python
with smtplib.SMTP("smtp.gmail.com", 587, timeout=30) as server:
    server.ehlo()
    server.starttls(context=ssl.create_default_context())
    server.ehlo()
    server.login(GMAIL_SENDER, GMAIL_APP_PASS)
    server.send_message(msg)
```

STARTTLS on 587 with a default-verified SSL context. `EmailMessage` with plain-text body — markdown emphasis arrives as literal asterisks in most email clients, so `parse_reminder()` strips it.

### Error handling

Every exception maps to an actionable message; nothing raises into Streamlit:

| Exception | Message |
|---|---|
| `SMTPAuthenticationError` | App Password wrong/expired → link to App Passwords page |
| `SMTPRecipientsRefused` | Address refused, nothing sent |
| `SMTPConnectError` | Check connection or firewall on port 587 |
| `SMTPServerDisconnected` | Connection dropped mid-send, retry |

`send_email()` returns `(False, message)` on every failure. **A false "sent" confirmation is worse than an error** — the freelancer stops waiting for a payment that will never arrive.

### Send gating

The UI renders the draft, offers an edit expander, and disables the button entirely when Gmail is unconfigured. Only `st.button("Send via Gmail")` reaches `mailer.send_email()`. On success: `storage.log_reminder()` writes tier, timestamp, recipient, subject, and body, and the client's email is backfilled if it was blank.

---

## 7. Data storage and retrieval

### Structure

One JSON file, `storage/data.json`, keyed by slugified client name:

```json
{
  "clients": {
    "peakform": {
      "name": "PeakForm", "email": "contact@peakform.com",
      "company": "PeakForm Fitness", "phone": "",
      "projects": [], "proposals": [], "invoices": [], "reminders": []
    }
  },
  "meta": {
    "last_invoice_number": 1043,
    "freelancer": {"name": "", "email": "", "phone": "", "payment_details": ""}
  }
}
```

Keyed by client because that matches how the freelancer asks — "show me everything for BrightLeaf" is one dictionary lookup, not a scan across four flat tables.

### Slugs

```python
slugify("Acme Corp.") == slugify("acme corp") == "acmecorp"
```

The freelancer's inconsistent capitalisation never forks one client into three records.

`find_client_fuzzy()` tries exact slug, then substring, and returns `(None, None)` on multiple matches rather than guessing. Marking the wrong client's invoice paid is a silent error that surfaces weeks later.

### Atomic writes

```python
fd, tmp = tempfile.mkstemp(dir=DATA_FILE.parent)
json.dump(data, fh); fh.flush(); os.fsync(fh.fileno())
os.replace(tmp, DATA_FILE)
```

Temp file in the **same directory** so `os.replace` is atomic on the same filesystem. A crash mid-write leaves the previous file intact rather than truncated — a half-written `data.json` loses every client record.

A corrupt file on load is moved to `data.corrupt.json` rather than overwritten, so it can be recovered by hand.

### Derived status

```python
def effective_status(invoice):
    if invoice["status"] == "unpaid" and days_overdue(invoice) > 0:
        return "overdue"
    return invoice["status"]
```

`overdue` is **never stored**. Stored state goes stale at midnight and would need a nightly job to stay honest — until that job ran, every morning's data would be quietly wrong.

Cancelled invoices are excluded from totals but never deleted. Gaps in the numbering sequence look like destroyed records to anyone auditing later.

### Retrieval

| Function | Returns |
|---|---|
| `list_invoices(filter, client)` | Rows sorted most-overdue-first — the order the freelancer cares about |
| `outstanding_total(client)` | `Decimal` sum of unpaid; paid and cancelled excluded |
| `client_history(name)` | Proposals, invoices, reminders for one client |
| `reminders_for_invoice(number)` | Prior reminders, chronological, for escalation awareness |
| `find_invoice(number)` | `(client_key, client, invoice)` |

Loaded once into `st.session_state.data` at session start, mutated in memory, and persisted with `persist()` after every write. Reads never hit disk mid-session, so a query costs nothing.
