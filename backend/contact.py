"""
Kontaktnachrichten-Speicher für Riot Music.

Speichert eingehende Kontaktanfragen persistent in data/contact_messages.json,
bis sie vom Admin gelesen/gelöscht oder per Mail versendet werden.

Threadsicher über RLock. Begrenzt die Anzahl gespeicherter Nachrichten gegen
Speicher-Überlauf bei Botspam-Wellen.
"""
from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
STORE_PATH = BASE_DIR / "data" / "contact_messages.json"

MAX_STORED = 1000              # Globales Limit gegen Spam-Flutung
MAX_NAME_LEN = 120
MAX_EMAIL_LEN = 200
MAX_SUBJECT_LEN = 200
MAX_BODY_LEN = 5000
MIN_BODY_LEN = 10

_lock = threading.RLock()


def _load() -> list[dict]:
    if not STORE_PATH.exists():
        return []
    try:
        return json.loads(STORE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def _save(messages: list[dict]) -> None:
    STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = STORE_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(messages, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, STORE_PATH)


def add_message(name: str, email: str, subject: str, body: str, ip: str) -> dict:
    """Fügt eine neue Nachricht hinzu. Wirft ValueError bei ungültigen Eingaben."""
    name = (name or "").strip()
    email = (email or "").strip().lower()
    subject = (subject or "").strip()
    body = (body or "").strip()

    if not name or len(name) > MAX_NAME_LEN:
        raise ValueError(f"Name muss 1–{MAX_NAME_LEN} Zeichen lang sein.")
    if not email or len(email) > MAX_EMAIL_LEN or "@" not in email or "." not in email:
        raise ValueError("Bitte eine gültige E-Mail-Adresse angeben.")
    if not subject or len(subject) > MAX_SUBJECT_LEN:
        raise ValueError(f"Betreff muss 1–{MAX_SUBJECT_LEN} Zeichen lang sein.")
    if len(body) < MIN_BODY_LEN or len(body) > MAX_BODY_LEN:
        raise ValueError(f"Nachricht muss {MIN_BODY_LEN}–{MAX_BODY_LEN} Zeichen lang sein.")

    msg = {
        "id": uuid.uuid4().hex,
        "name": name,
        "email": email,
        "subject": subject,
        "body": body,
        "ip": ip,
        "createdAt": datetime.now(tz=timezone.utc).isoformat(),
        "read": False,
    }

    with _lock:
        messages = _load()
        # Bei Erreichen des Limits älteste gelesene Nachrichten zuerst entfernen.
        if len(messages) >= MAX_STORED:
            messages.sort(key=lambda m: (not m.get("read", False), m.get("createdAt", "")))
            messages = messages[-(MAX_STORED - 1):]
        messages.append(msg)
        _save(messages)
    return msg


REPORT_REASONS = (
    "Urheberrechtsverletzung",
    "Pornografische / sexuelle Inhalte",
    "Gewalt / Verherrlichung",
    "Hassrede / Diskriminierung",
    "Spam / Betrug",
    "Sonstiges",
)


def add_report(reported_artist_id: str, reported_artist_name: str,
               reason: str, details: str, ip: str) -> dict:
    """
    Speichert eine Inhalts-Meldung (Notice-and-Action) im selben Posteingang.
    Wirft ValueError bei ungültigen Eingaben.
    """
    reason = (reason or "").strip()
    details = (details or "").strip()
    if reason not in REPORT_REASONS:
        raise ValueError("Bitte einen gültigen Meldegrund wählen.")
    if len(details) > MAX_BODY_LEN:
        raise ValueError(f"Begründung darf max. {MAX_BODY_LEN} Zeichen lang sein.")

    msg = {
        "id": uuid.uuid4().hex,
        "type": "report",
        "reportedArtistId": (reported_artist_id or "").strip(),
        "reportedArtistName": (reported_artist_name or "").strip(),
        "reason": reason,
        # In die Standardfelder spiegeln, damit die Meldung in der bestehenden
        # Posteingangs-Ansicht ohne Sonderbehandlung lesbar bleibt.
        "name": "Inhalts-Meldung",
        "email": "",
        "subject": f"⚠ Meldung: {reason}",
        "body": details or "(keine weitere Begründung angegeben)",
        "ip": ip,
        "createdAt": datetime.now(tz=timezone.utc).isoformat(),
        "read": False,
    }
    with _lock:
        messages = _load()
        if len(messages) >= MAX_STORED:
            messages.sort(key=lambda m: (not m.get("read", False), m.get("createdAt", "")))
            messages = messages[-(MAX_STORED - 1):]
        messages.append(msg)
        _save(messages)
    return msg


def list_messages() -> list[dict]:
    with _lock:
        msgs = _load()
    msgs.sort(key=lambda m: m.get("createdAt", ""), reverse=True)
    return msgs


def mark_read(msg_id: str, read: bool = True) -> bool:
    with _lock:
        messages = _load()
        for m in messages:
            if m["id"] == msg_id:
                m["read"] = bool(read)
                _save(messages)
                return True
    return False


def delete_message(msg_id: str) -> bool:
    with _lock:
        messages = _load()
        new = [m for m in messages if m["id"] != msg_id]
        if len(new) == len(messages):
            return False
        _save(new)
        return True


def count_unread() -> int:
    with _lock:
        return sum(1 for m in _load() if not m.get("read", False))


# ---------------------------------------------------------------------------
# Leichte heuristische Spam-Erkennung – ergänzt Captcha & Honeypot.
# ---------------------------------------------------------------------------
_SPAM_PATTERNS = (
    "http://", "https://", "www.",     # Links sind in Kontaktanfragen selten nötig
    "<a ", "</a>", "[url=", "[/url]",   # HTML/BBCode-Links
    "viagra", "cialis", "casino", "bitcoin", "crypto",
    "seo service", "buy followers", "free money",
)


def looks_like_spam(name: str, subject: str, body: str) -> bool:
    """Heuristische Prüfung: zu viele Links oder bekannte Spam-Begriffe → True."""
    blob = f"{name}\n{subject}\n{body}".lower()
    link_hits = blob.count("http://") + blob.count("https://") + blob.count("www.")
    if link_hits >= 3:
        return True
    for pat in _SPAM_PATTERNS:
        if pat in blob:
            return True
    # Auffällig: > 70% Großbuchstaben im Body bei Mindestlänge
    letters = [c for c in body if c.isalpha()]
    if len(letters) >= 40:
        upper = sum(1 for c in letters if c.isupper())
        if upper / len(letters) > 0.7:
            return True
    return False
