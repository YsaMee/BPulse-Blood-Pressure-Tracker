# export_utils.py
import re

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def safe_filename(text, fallback="patient"):
    cleaned = re.sub(r"[^\w\-]+", "_", str(text or "").strip(), flags=re.UNICODE).strip("_")
    return cleaned or fallback


def csv_safe(value):
    text = "" if value is None else str(value)
    if text and text[0] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + text
    return text


def is_valid_email(address):
    return bool(address and EMAIL_RE.match(address.strip()))
