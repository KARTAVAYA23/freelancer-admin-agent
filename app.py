"""Freelancer Admin Agent — Streamlit chat interface.

Single entry point:  streamlit run app.py

One conversational surface. The router picks an agent, the agent fills slots by
asking, and output lands as a downloadable document or a confirm-gated email.
"""
import base64
import html
import re
from datetime import date, timedelta
from pathlib import Path

import streamlit as st

AUDIO_FILE = Path(__file__).parent / "ma-ka-bhosda-aag.mp3"
SHOCKED_AUDIO_FILE = Path(__file__).parent / "shocked-sound-effect.mp3"


def play_first_audio():
    if not st.session_state.get("audio_played", False):
        st.session_state.audio_played = True
        if AUDIO_FILE.exists():
            try:
                st.audio(str(AUDIO_FILE), autoplay=True)
                with open(AUDIO_FILE, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode()
                st.markdown(
                    f'<audio autoplay style="display:none">'
                    f'<source src="data:audio/mp3;base64,{b64}" type="audio/mp3">'
                    f'</audio>',
                    unsafe_allow_html=True
                )
            except Exception:
                pass


def play_output_sound():
    if SHOCKED_AUDIO_FILE.exists():
        try:
            st.audio(str(SHOCKED_AUDIO_FILE), autoplay=True)
            with open(SHOCKED_AUDIO_FILE, "rb") as f:
                b64 = base64.b64encode(f.read()).decode()
            st.markdown(
                f'<audio autoplay style="display:none">'
                f'<source src="data:audio/mp3;base64,{b64}" type="audio/mp3">'
                f'</audio>',
                unsafe_allow_html=True
            )
        except Exception:
            pass


import agents
import config
import intent as intent_mod
import mailer
import storage
from documents import (
    D, compute_invoice, fmt, invoice_pdf, invoice_preview_text,
    proposal_docx, proposal_pdf,
)
from storage import pretty_date
import importlib
import theme
importlib.reload(theme)
from theme import CSS, masthead, stat_strip

st.set_page_config(page_title="Freelance Admin Desk", page_icon="🖋", layout="centered")
st.markdown(theme.CSS, unsafe_allow_html=True)


# ─────────────────────────── startup gate ───────────────────────────

if not config.openai_ready():
    st.markdown(masthead(), unsafe_allow_html=True)
    st.markdown(
        '<div class="notice"><b>No API key found.</b><br><br>'
        'Open the <code>.env</code> file in this folder and paste your key after '
        '<code>OPENAI_API_KEY=</code> — the field is blank and waiting for it.<br><br>'
        'Save the file, then restart with <code>streamlit run app.py</code>.</div>',
        unsafe_allow_html=True)
    st.stop()

missing_specs = [f for f in [agents.RULES] + list(agents.ROLE_CARDS.values())
                 if not (config.SKILLS_DIR / f).exists()]
if missing_specs:
    st.markdown(masthead(), unsafe_allow_html=True)
    st.markdown(
        '<div class="notice"><b>Agent specification files are missing.</b><br><br>'
        + "<br>".join(f"<code>skills/{f}</code>" for f in missing_specs)
        + '<br><br>Agent behaviour is defined in these markdown files. '
          'Restore them from the package and restart.</div>',
        unsafe_allow_html=True)
    st.stop()


# ─────────────────────────── session state ───────────────────────────

def init_state():
    defaults = {
        "messages": [],
        "data": storage.load(),
        "pending_intent": "",
        "pending_slot": "",
        "slots": {},
        "artifacts": {},        # message index -> artifact dict
        "artifact_seq": 0,
        "greeted": False,
        "audio_played": False,
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


init_state()
data = st.session_state.data
freelancer = storage.get_freelancer(data)

# .env identity fills blanks in the stored profile, without clobbering edits.
for field, env_value in (("name", config.FREELANCER_NAME),
                         ("email", config.FREELANCER_EMAIL),
                         ("phone", config.FREELANCER_PHONE)):
    if env_value and not freelancer.get(field):
        freelancer[field] = env_value


def persist():
    storage.save(st.session_state.data)


def say(role: str, content: str, artifact: dict = None):
    st.session_state.messages.append({"role": role, "content": content})
    if artifact:
        st.session_state.artifacts[len(st.session_state.messages) - 1] = artifact


def reset_flow():
    st.session_state.pending_intent = ""
    st.session_state.pending_slot = ""
    st.session_state.slots = {}


def esc(text) -> str:
    return html.escape(str(text or ""))


def md_to_html(text: str) -> str:
    """Minimal markdown for the document card — headings, bullets, bold."""
    out, in_list = [], False
    for raw in (text or "").split("\n"):
        line = raw.strip()
        if not line:
            if in_list:
                out.append("</ul>")
                in_list = False
            continue
        line_html = esc(line)
        line_html = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", line_html)
        line_html = re.sub(r"(?<!\*)\*([^*]+?)\*(?!\*)", r"<em>\1</em>", line_html)

        if line.startswith("#"):
            if in_list:
                out.append("</ul>")
                in_list = False
            out.append(f"<h3>{line_html.lstrip('#').strip()}</h3>")
        elif line.startswith(("- ", "* ", "• ")):
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{line_html[2:].strip()}</li>")
        else:
            if in_list:
                out.append("</ul>")
                in_list = False
            out.append(f"<p>{line_html}</p>")
    if in_list:
        out.append("</ul>")
    return "".join(out)


# ─────────────────────────── sidebar ───────────────────────────

with st.sidebar:
    st.markdown("## Your details")
    freelancer["name"] = st.text_input("Name", freelancer.get("name", ""),
                                       placeholder="Riya Sharma")
    freelancer["email"] = st.text_input("Email", freelancer.get("email", ""),
                                        placeholder="you@example.com")
    freelancer["phone"] = st.text_input("Phone", freelancer.get("phone", ""),
                                        placeholder="+91 98765 43210")
    freelancer["payment_details"] = st.text_area(
        "Payment details", freelancer.get("payment_details", ""), height=88,
        placeholder="Bank: HDFC · A/C 000123456789\nIFSC: HDFC0001234\nUPI: riya@okhdfcbank")
    if st.button("Save details", use_container_width=True):
        persist()
        st.toast("Saved.")

    st.markdown('<div class="side-label">Gmail</div>', unsafe_allow_html=True)
    if config.gmail_ready():
        st.markdown(f'<span class="pill pill-ok">READY</span> '
                    f'<span style="font-size:.72rem;color:var(--ink-soft)">'
                    f'{esc(config.GMAIL_SENDER)}</span>', unsafe_allow_html=True)
        if st.button("Test connection", use_container_width=True):
            with st.spinner("Connecting…"):
                ok, message = mailer.test_connection()
            (st.success if ok else st.error)(message)
    else:
        st.markdown('<span class="pill pill-warn">NOT SET</span>', unsafe_allow_html=True)
        st.caption("Add GMAIL_SENDER and GMAIL_APP_PASS to `.env` to send reminders. "
                   "Proposals and invoices work without it.")

    st.markdown('<div class="side-label">Outstanding</div>', unsafe_allow_html=True)
    unpaid_rows = storage.list_invoices(data, "unpaid")
    if unpaid_rows:
        for row in unpaid_rows[:8]:
            late = "late" if row["days_overdue"] > 0 else ""
            suffix = f" · {row['days_overdue']}d" if row["days_overdue"] > 0 else ""
            st.markdown(
                f'<div class="side-row"><span class="n">#{row["number"]} '
                f'{esc(row["client"])[:15]}</span>'
                f'<span class="a {late}">{fmt(row["total"])}{suffix}</span></div>',
                unsafe_allow_html=True)
        st.markdown(f'<div class="side-row" style="border:0;margin-top:.3rem">'
                    f'<span class="n"><b>TOTAL</b></span>'
                    f'<span class="a late">{fmt(storage.outstanding_total(data))}</span></div>',
                    unsafe_allow_html=True)
    else:
        st.caption("Nothing outstanding.")

    st.markdown('<div class="side-label">Session</div>', unsafe_allow_html=True)
    if st.button("Clear chat", use_container_width=True):
        st.session_state.messages = []
        st.session_state.artifacts = {}
        st.session_state.greeted = False
        reset_flow()
        st.rerun()


# ─────────────────────────── header ───────────────────────────

st.markdown(masthead(freelancer.get("name", "")), unsafe_allow_html=True)

all_invoices = storage.list_invoices(data, "all")
st.markdown(stat_strip(
    clients=len(data["clients"]),
    outstanding=fmt(storage.outstanding_total(data)),
    overdue_count=sum(1 for r in all_invoices if r["status"] == "overdue"),
    paid_count=sum(1 for r in all_invoices if r["status"] == "paid"),
), unsafe_allow_html=True)

if not st.session_state.greeted and not st.session_state.messages:
    say("assistant",
        "What do you need? Tell me about a project and I'll draft a proposal, "
        "give me your hours and I'll cut an invoice, or name a client who hasn't paid.")
    st.session_state.greeted = True


# ─────────────────────────── artifact rendering ───────────────────────────

def render_artifact(artifact: dict, key: str):
    kind = artifact.get("kind")

    if kind == "proposal":
        st.markdown(f'<div class="doc-card">{md_to_html(artifact["body"])}</div>',
                    unsafe_allow_html=True)
        col1, col2 = st.columns(2)
        stem = re.sub(r"[^A-Za-z0-9]+", "-",
                      f"Proposal {artifact['client']} {artifact['project']}").strip("-")
        with col1:
            st.download_button("Download PDF", artifact["pdf"], f"{stem}.pdf",
                               "application/pdf", key=f"pp{key}", use_container_width=True)
        with col2:
            st.download_button(
                "Download Word", artifact["docx"], f"{stem}.docx",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                key=f"pd{key}", use_container_width=True)

    elif kind == "invoice":
        st.markdown(f'<div class="ledger-block"><pre>{esc(artifact["preview"])}</pre></div>',
                    unsafe_allow_html=True)
        st.download_button("Download Invoice PDF", artifact["pdf"],
                           f"Invoice-{artifact['number']}.pdf", "application/pdf",
                           key=f"ip{key}", use_container_width=True)

    elif kind == "reminder":
        st.markdown(
            f'<div class="email-card">'
            f'<span class="tier-chip tier-{artifact["tier"]}">{artifact["tier"]} · '
            f'{artifact["days"]} days overdue</span>'
            f'<div class="email-head"><b>To</b> {esc(artifact["to"] or "— no address on file —")}'
            f'<br><b>Subject</b> {esc(artifact["subject"])}</div>'
            f'<div class="email-body">{esc(artifact["body"])}</div></div>',
            unsafe_allow_html=True)

        if artifact.get("sent"):
            st.markdown(f'<div class="notice ok">Sent to {esc(artifact["to"])} · '
                        f'{esc(artifact.get("sent_at", ""))}</div>', unsafe_allow_html=True)
            return

        with st.expander("Edit before sending"):
            new_subject = st.text_input("Subject", artifact["subject"], key=f"rs{key}")
            new_body = st.text_area("Body", artifact["body"], height=230, key=f"rb{key}")
            if st.button("Apply edits", key=f"ra{key}"):
                artifact["subject"] = new_subject
                artifact["body"] = new_body
                st.rerun()

        recipient = artifact.get("to", "")
        if not recipient:
            recipient = st.text_input("Client email address — none on file", "",
                                      key=f"re{key}", placeholder="client@company.com")

        col1, col2 = st.columns([1, 1])
        with col1:
            send_clicked = st.button("Send via Gmail", key=f"rsend{key}",
                                     type="primary", use_container_width=True,
                                     disabled=not config.gmail_ready())
        with col2:
            if st.button("Discard", key=f"rd{key}", use_container_width=True):
                artifact["kind"] = "discarded"
                st.rerun()

        if not config.gmail_ready():
            st.caption("Gmail not configured — add GMAIL_SENDER and GMAIL_APP_PASS to `.env`.")

        if send_clicked:
            if not mailer.valid_email(recipient):
                st.error("That email address doesn't look valid. Nothing was sent.")
            else:
                with st.spinner("Sending…"):
                    ok, message = mailer.send_email(
                        recipient, artifact["subject"], artifact["body"],
                        sender_name=freelancer.get("name", ""),
                        reply_to=freelancer.get("email", ""))
                if ok:
                    artifact["sent"] = True
                    artifact["to"] = recipient
                    record = storage.log_reminder(
                        st.session_state.data, artifact["client"], artifact["number"],
                        artifact["tier"], recipient, artifact["subject"], artifact["body"])
                    artifact["sent_at"] = pretty_date(record["sent_at"])
                    storage.set_client_email(st.session_state.data, artifact["client"], recipient)
                    persist()
                    st.rerun()
                else:
                    st.error(message)

    elif kind == "table":
        st.markdown(f'<div class="ledger-block"><pre>{esc(artifact["text"])}</pre></div>',
                    unsafe_allow_html=True)


for index, message in enumerate(st.session_state.messages):
    with st.chat_message(message["role"]):
        if message.get("content"):
            st.markdown(message["content"])
        artifact = st.session_state.artifacts.get(index)
        if artifact and artifact.get("kind") != "discarded":
            render_artifact(artifact, str(index))

if st.session_state.get("play_shocked", False):
    play_output_sound()
    st.session_state.play_shocked = False


# ─────────────────────────── handlers ───────────────────────────

def handle_proposal(slots):
    missing = intent_mod.missing_slots("PROPOSAL", slots)
    if missing:
        st.session_state.pending_intent = "PROPOSAL"
        st.session_state.pending_slot = missing[0]
        question = agents.ask_followup("proposal", slots, missing,
                                       st.session_state.messages)
        say("assistant", question or intent_mod.SLOT_QUESTIONS.get(missing[0], "Tell me more."))
        return

    if not freelancer.get("name"):
        say("assistant", "Add your name in the sidebar first — it goes on the proposal.")
        return

    body = agents.generate_proposal(slots, freelancer)
    client_name = slots["client_name"]
    project = slots.get("project_title") or "Project Proposal"

    storage.ensure_client(st.session_state.data, client_name)
    storage.add_proposal(st.session_state.data, client_name, project, body)
    persist()

    say("assistant", f"Proposal for **{client_name}** — {project}.", {
        "kind": "proposal", "body": body, "client": client_name, "project": project,
        "pdf": proposal_pdf(body, client_name, project, freelancer),
        "docx": proposal_docx(body, client_name, project, freelancer),
    })
    reset_flow()


def handle_invoice(slots):
    slots.setdefault("project_name", slots.get("project_title", ""))
    work_items = intent_mod.build_work_items(slots)
    if work_items:
        slots["work_items"] = work_items

    missing = intent_mod.missing_slots("INVOICE", slots)
    if missing:
        st.session_state.pending_intent = "INVOICE"
        st.session_state.pending_slot = missing[0]
        question = agents.ask_followup("invoice", slots, missing, st.session_state.messages)
        say("assistant", question or intent_mod.SLOT_QUESTIONS.get(missing[0], "Tell me more."))
        return

    if not freelancer.get("payment_details"):
        say("assistant", "Add your payment details in the sidebar — the client needs to "
                         "know how to pay you.")
        return

    number = slots.get("invoice_number") or storage.next_invoice_number(st.session_state.data)
    owner, existing = storage.invoice_number_exists(st.session_state.data, number)
    if existing:
        say("assistant", f"Invoice #{number} already exists for {owner}, issued "
                         f"{pretty_date(existing.get('issue_date'))}. Give me a different number.")
        return

    items, subtotal, tax_amount, total = compute_invoice(work_items, slots.get("tax_rate", 0))
    issue = date.today()
    due = issue + timedelta(days=config.INVOICE_DUE_DAYS)
    client_name = slots["client_name"]

    invoice = {
        "number": int(number),
        "project": slots.get("project_name", ""),
        "issue_date": storage.iso(issue),
        "due_date": storage.iso(due),
        "line_items": [{k: (float(v) if k in ("hours", "rate", "subtotal") else v)
                        for k, v in item.items()} for item in items],
        "subtotal": float(subtotal),
        "tax_rate": float(D(slots.get("tax_rate", 0))),
        "tax_amount": float(tax_amount),
        "total": float(total),
        "status": "unpaid",
        "notes": agents.generate_invoice_note(slots),
        "payment_details": freelancer.get("payment_details", ""),
    }

    client_record = storage.ensure_client(st.session_state.data, client_name)
    storage.add_invoice(st.session_state.data, client_name, invoice)
    persist()

    preview = invoice_preview_text({**invoice, "client_name": client_name})
    say("assistant",
        f"Invoice **#{invoice['number']}** for {client_name} — {fmt(total)}, "
        f"due {pretty_date(due)}.", {
            "kind": "invoice", "number": invoice["number"], "preview": preview,
            "pdf": invoice_pdf(invoice, client_record, freelancer),
        })
    reset_flow()


def handle_reminder(slots):
    if not slots.get("client_name") and not slots.get("invoice_number"):
        st.session_state.pending_intent = "REMINDER"
        st.session_state.pending_slot = "client_name"
        say("assistant", "Which client?")
        return

    invoice, client_record = None, None
    if slots.get("invoice_number"):
        _key, client_record, invoice = storage.find_invoice(
            st.session_state.data, slots["invoice_number"])
        if invoice is None:
            say("assistant", f"No invoice #{slots['invoice_number']} in storage.")
            reset_flow()
            return
    else:
        name = slots["client_name"]
        _key, client_record = storage.find_client_fuzzy(st.session_state.data, name)
        if client_record is None:
            known = storage.client_names(st.session_state.data)
            listing = ", ".join(f"**{n}**" for n in known) if known else "none yet"
            say("assistant", f"No client called “{name}”. On file: {listing}.")
            reset_flow()
            return
        unpaid = [i for i in client_record.get("invoices", []) if i.get("status") == "unpaid"]
        if not unpaid:
            say("assistant", f"Nothing unpaid for {client_record['name']}.")
            reset_flow()
            return
        if len(unpaid) > 1:
            listing = "\n".join(
                f"- **#{i['number']}** · {fmt(i['total'])} · due {pretty_date(i['due_date'])}"
                for i in unpaid)
            say("assistant", f"{client_record['name']} has {len(unpaid)} unpaid invoices — "
                             f"which one?\n\n{listing}")
            st.session_state.pending_intent = "REMINDER"
            st.session_state.pending_slot = "invoice_number"
            return
        invoice = unpaid[0]

    days = storage.days_overdue(invoice)
    if days <= 0:
        due = pretty_date(invoice.get("due_date"))
        say("assistant", f"Invoice #{invoice['number']} isn't overdue yet — due {due}. "
                         f"Say “remind anyway” if you want to nudge them regardless.")
        if "anyway" not in " ".join(
                m["content"].lower() for m in st.session_state.messages[-2:]
                if m["role"] == "user"):
            reset_flow()
            return
        days = 1

    tier = agents.tone_tier(days)
    prior = storage.reminders_for_invoice(st.session_state.data, invoice["number"])
    subject, body = agents.generate_reminder(
        invoice, client_record, freelancer, days, prior)

    note = (f"{tier.title()} reminder for **#{invoice['number']}** — "
            f"{days} days overdue. Read it, then send.")
    if prior:
        note += f" ({len(prior)} already sent.)"

    say("assistant", note, {
        "kind": "reminder", "tier": tier, "days": days,
        "subject": subject, "body": body,
        "to": client_record.get("email", ""), "client": client_record["name"],
        "number": invoice["number"], "sent": False,
    })
    reset_flow()


def handle_query(slots):
    filt = slots.get("query_filter", "unpaid")
    name = slots.get("client_name", "")

    if name:
        history = storage.client_history(st.session_state.data, name)
        if history is None:
            known = storage.client_names(st.session_state.data)
            listing = ", ".join(f"**{n}**" for n in known) if known else "none yet"
            say("assistant", f"No client called “{name}”. On file: {listing}.")
            return
        lines = [f"{history['name']}  ·  {history['email'] or 'no email on file'}", ""]
        lines.append(f"Proposals  {len(history['proposals'])}")
        for prop in history["proposals"][-4:]:
            lines.append(f"    {prop['project'][:44]:<44} {pretty_date(prop['created'])}")
        lines.append("")
        lines.append(f"Invoices   {len(history['invoices'])}")
        for inv in history["invoices"][-6:]:
            lines.append(f"    #{inv['number']:<6} {fmt(inv['total']):>11}   "
                         f"{inv['effective_status']:<9} due {pretty_date(inv['due_date'])}")
        lines.append("")
        lines.append(f"Reminders  {len(history['reminders'])}")
        for rem in history["reminders"][-4:]:
            lines.append(f"    #{rem['invoice']:<6} {rem['tier']:<8} "
                         f"{pretty_date(rem['sent_at'])}")
        say("assistant", f"Everything on file for **{history['name']}**.",
            {"kind": "table", "text": "\n".join(lines)})
        return

    rows = storage.list_invoices(st.session_state.data, filt)
    if not rows:
        say("assistant", "Nothing outstanding — every invoice is settled.")
        return

    lines = []
    for row in rows:
        state = (f"overdue {row['days_overdue']}d" if row["days_overdue"] > 0
                 else row["status"])
        lines.append(f"  #{row['number']:<6} {esc(row['client'])[:20]:<20} "
                     f"{fmt(row['total']):>11}   {state}")
    total = sum(D(r["total"]) for r in rows)
    lines.append("")
    lines.append(f"  {'TOTAL':<27}{fmt(total):>11}")

    label = {"unpaid": "unpaid", "overdue": "overdue", "paid": "paid"}.get(filt, "")
    say("assistant", f"{len(rows)} {label} invoice{'s' if len(rows) != 1 else ''} — "
                     f"{fmt(total)} outstanding.",
        {"kind": "table", "text": "\n".join(lines)})


def handle_status(slots):
    number = slots.get("invoice_number")
    new_status = slots.get("new_status")

    if not number and slots.get("client_name"):
        _key, client_record = storage.find_client_fuzzy(
            st.session_state.data, slots["client_name"])
        if client_record:
            unpaid = [i for i in client_record.get("invoices", [])
                      if i.get("status") == "unpaid"]
            if len(unpaid) == 1:
                number = unpaid[0]["number"]
            elif len(unpaid) > 1:
                listing = "\n".join(f"- **#{i['number']}** · {fmt(i['total'])}" for i in unpaid)
                say("assistant", f"{client_record['name']} has several unpaid invoices — "
                                 f"which one?\n\n{listing}")
                st.session_state.pending_intent = "STATUS_UPDATE"
                st.session_state.pending_slot = "invoice_number"
                return

    if not number:
        st.session_state.pending_intent = "STATUS_UPDATE"
        st.session_state.pending_slot = "invoice_number"
        say("assistant", "Which invoice number?")
        return
    if not new_status:
        st.session_state.pending_intent = "STATUS_UPDATE"
        st.session_state.pending_slot = "new_status"
        say("assistant", "Set it to paid, unpaid, or cancelled?")
        return

    ok, message, _invoice = storage.set_invoice_status(
        st.session_state.data, number, new_status)
    if ok:
        persist()
    say("assistant", message)
    reset_flow()


# ─────────────────────────── input loop ───────────────────────────

prompt = st.chat_input("Describe what you need…")

if prompt:
    play_first_audio()
    say("user", prompt)

    with st.spinner("Reading…"):
        result = intent_mod.detect(
            prompt, st.session_state.messages[:-1],
            st.session_state.pending_intent, st.session_state.pending_slot)

    detected = result["intent"]
    if st.session_state.pending_intent and detected == "CHITCHAT":
        detected = st.session_state.pending_intent

    st.session_state.slots = intent_mod.merge_slots(st.session_state.slots, result["slots"])
    if st.session_state.pending_intent and detected != st.session_state.pending_intent:
        st.session_state.slots = result["slots"]

    slots = st.session_state.slots

    try:
        if detected == "PROPOSAL":
            with st.spinner("Writing the proposal…"):
                handle_proposal(slots)
        elif detected == "INVOICE":
            with st.spinner("Building the invoice…"):
                handle_invoice(slots)
        elif detected == "REMINDER":
            with st.spinner("Drafting the reminder…"):
                handle_reminder(slots)
        elif detected == "QUERY":
            handle_query(slots)
            reset_flow()
        elif detected == "STATUS_UPDATE":
            handle_status(slots)
        else:
            say("assistant", agents.chitchat_reply(st.session_state.messages))
            reset_flow()
    except Exception as exc:
        say("assistant", f"That didn't work: `{exc}`")
        reset_flow()

    st.session_state.play_shocked = True
    st.rerun()
