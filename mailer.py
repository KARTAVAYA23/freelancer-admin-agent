"""Gmail sending over SMTP with an App Password.

Never called without an explicit button press in the UI. Every failure path
returns (False, human_readable_message) rather than raising into Streamlit,
because a traceback in the chat panel tells the freelancer nothing actionable.
"""

import re
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid

from config import (
    GMAIL_APP_PASS, GMAIL_SENDER, SMTP_HOST, SMTP_PORT,
    gmail_ready, missing_gmail_fields,
)

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def valid_email(address: str) -> bool:
    return bool(EMAIL_RE.match((address or "").strip()))


def preflight():
    """Check config before composing anything. Returns (ok, message)."""
    if not gmail_ready():
        missing = ", ".join(missing_gmail_fields())
        return False, (
            f"Gmail is not configured — {missing} is blank in your .env file. "
            "Add your Gmail address and a 16-character App Password, then restart the app."
        )
    if not valid_email(GMAIL_SENDER):
        return False, f"GMAIL_SENDER in .env is not a valid email address: {GMAIL_SENDER!r}"
    if len(GMAIL_APP_PASS) != 16:
        return False, (
            f"GMAIL_APP_PASS is {len(GMAIL_APP_PASS)} characters — a Gmail App Password is "
            "exactly 16. This is not your normal Google password; generate one at "
            "Google Account → Security → App Passwords."
        )
    return True, "Gmail configured."


def send_email(to_address: str, subject: str, body: str, sender_name: str = "",
               reply_to: str = ""):
    """Send one plain-text email. Returns (ok, message).

    Returns False on every failure rather than raising — a false 'sent'
    confirmation is worse than an error, because the freelancer stops waiting
    for a payment that will never arrive.
    """
    ok, message = preflight()
    if not ok:
        return False, message

    to_address = (to_address or "").strip()
    if not valid_email(to_address):
        return False, f"'{to_address}' is not a valid email address. Nothing was sent."

    if not (subject or "").strip():
        return False, "Refusing to send an email with an empty subject line."
    if not (body or "").strip():
        return False, "Refusing to send an email with an empty body."

    msg = EmailMessage()
    msg["Subject"] = subject.strip()
    msg["From"] = formataddr((sender_name or "", GMAIL_SENDER)) if sender_name else GMAIL_SENDER
    msg["To"] = to_address
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid()
    if reply_to and valid_email(reply_to):
        msg["Reply-To"] = reply_to
    msg.set_content(body)

    context = ssl.create_default_context()

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as server:
            server.ehlo()
            server.starttls(context=context)
            server.ehlo()
            server.login(GMAIL_SENDER, GMAIL_APP_PASS)
            server.send_message(msg)
        return True, f"Reminder sent to {to_address}."

    except smtplib.SMTPAuthenticationError:
        return False, (
            "Gmail rejected the login. The App Password in .env is wrong, expired, or "
            "was generated for a different account. Generate a fresh one at "
            "Google Account → Security → App Passwords and paste all 16 characters."
        )
    except smtplib.SMTPRecipientsRefused:
        return False, f"Gmail refused the recipient address '{to_address}'. Nothing was sent."
    except smtplib.SMTPSenderRefused:
        return False, f"Gmail refused to send from '{GMAIL_SENDER}'. Check GMAIL_SENDER in .env."
    except smtplib.SMTPConnectError:
        return False, ("Could not connect to smtp.gmail.com:587. Check your internet "
                       "connection, or whether a firewall is blocking outbound port 587.")
    except smtplib.SMTPServerDisconnected:
        return False, "Gmail closed the connection mid-send. Try again in a moment."
    except smtplib.SMTPException as exc:
        return False, f"SMTP error: {exc}"
    except (OSError, ssl.SSLError) as exc:
        return False, f"Network error while sending: {exc}"


def test_connection():
    """Verify credentials without sending anything. Used by the sidebar button."""
    ok, message = preflight()
    if not ok:
        return False, message
    try:
        context = ssl.create_default_context()
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as server:
            server.ehlo()
            server.starttls(context=context)
            server.ehlo()
            server.login(GMAIL_SENDER, GMAIL_APP_PASS)
        return True, f"Connected to Gmail as {GMAIL_SENDER}."
    except smtplib.SMTPAuthenticationError:
        return False, ("Gmail rejected the App Password. Generate a new one at "
                       "Google Account → Security → App Passwords.")
    except Exception as exc:
        return False, f"Could not connect: {exc}"
