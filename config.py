"""Configuration loading and validation.

Reads .env once at import. Every other module imports its settings from here so
there is exactly one place where credentials enter the process.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).parent.resolve()

load_dotenv(ROOT / ".env")

SKILLS_DIR = ROOT / "skills"
STORAGE_DIR = ROOT / "storage"
EXPORTS_DIR = ROOT / "exports"
DATA_FILE = STORAGE_DIR / "data.json"

for _d in (STORAGE_DIR, EXPORTS_DIR):
    _d.mkdir(exist_ok=True)


def _clean(name: str, default: str = "") -> str:
    """Read an env var, stripping whitespace and stray quote marks.

    People paste keys with trailing newlines and wrap them in quotes out of
    habit. Both produce authentication failures that look like bad keys.
    """
    value = (os.getenv(name) or default).strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        value = value[1:-1].strip()
    return value


OPENAI_API_KEY = _clean("OPENAI_API_KEY")
OPENAI_MODEL = _clean("OPENAI_MODEL", "gpt-4o")

# Gmail strips the display spaces from app passwords; users copy them verbatim.
GMAIL_SENDER = _clean("GMAIL_SENDER")
GMAIL_APP_PASS = _clean("GMAIL_APP_PASS").replace(" ", "")

FREELANCER_NAME = _clean("FREELANCER_NAME")
FREELANCER_EMAIL = _clean("FREELANCER_EMAIL")
FREELANCER_PHONE = _clean("FREELANCER_PHONE")

CURRENCY_SYMBOL = _clean("CURRENCY_SYMBOL", "$")


def _int_setting(name: str, default: int) -> int:
    raw = _clean(name)
    try:
        return int(raw) if raw else default
    except ValueError:
        return default


INVOICE_DUE_DAYS = _int_setting("INVOICE_DUE_DAYS", 15)
INVOICE_START_NUMBER = _int_setting("INVOICE_START_NUMBER", 1001)

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587


def openai_ready() -> bool:
    return bool(OPENAI_API_KEY)


def gmail_ready() -> bool:
    """Gmail is checked lazily — only reminders need it."""
    return bool(GMAIL_SENDER and GMAIL_APP_PASS)


def missing_gmail_fields() -> list:
    missing = []
    if not GMAIL_SENDER:
        missing.append("GMAIL_SENDER")
    if not GMAIL_APP_PASS:
        missing.append("GMAIL_APP_PASS")
    return missing
