"""
Authentifizierung für Riot Music – ohne externe Abhängigkeiten.

  * Passwort-Hashing via PBKDF2-HMAC-SHA256 (Standardbibliothek). Ältere Hashes
    mit weniger Runden werden beim nächsten Login automatisch erneuert.
  * Sitzungs-Token: stateless, HMAC-signiert, als HttpOnly-Cookie gesetzt.
    Enthält die „Sitzungsversion“ des Kontos – wird sie erhöht (Passwort
    geändert, „überall abmelden“), sind alle bisherigen Sitzungen ungültig.
  * Zweckgebundene Aktions-Token (E-Mail-Bestätigung, Passwort-Reset, 2FA-
    Zwischenschritt, „Gerät merken“). Sie werden nie als Sitzung akzeptiert.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
SECRET_PATH = BASE_DIR / "data" / "secret.key"

ITERATIONS = 600_000            # OWASP-Empfehlung für PBKDF2-HMAC-SHA256 (2023+)
TOKEN_TTL = 60 * 60 * 24 * 14   # 14 Tage
COOKIE_NAME = "rm_session"
TRUST_COOKIE = "rm_trust"       # „Dieses Gerät 30 Tage merken“ (2FA)
TRUST_TTL = 60 * 60 * 24 * 30


def _load_secret() -> bytes:
    if SECRET_PATH.exists():
        return SECRET_PATH.read_bytes()
    SECRET_PATH.parent.mkdir(parents=True, exist_ok=True)
    s = secrets.token_bytes(32)
    SECRET_PATH.write_bytes(s)
    return s


_SECRET = _load_secret()


# ---------------------------------------------------------------------------
# Passwörter
# ---------------------------------------------------------------------------
def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, ITERATIONS)
    return f"pbkdf2_sha256${ITERATIONS}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iters, salt_hex, hash_hex = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"),
                                 bytes.fromhex(salt_hex), int(iters))
        return hmac.compare_digest(dk.hex(), hash_hex)
    except (ValueError, AttributeError):
        return False


def needs_rehash(stored: str) -> bool:
    """True, wenn der Hash mit weniger Runden als heute üblich erstellt wurde."""
    try:
        return int(stored.split("$")[1]) < ITERATIONS
    except (IndexError, ValueError, AttributeError):
        return False


# ---------------------------------------------------------------------------
# Signierte Token (stateless)
# ---------------------------------------------------------------------------
def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64d(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _sign(payload: dict) -> str:
    body = _b64e(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    sig = _b64e(hmac.new(_SECRET, body.encode("ascii"), hashlib.sha256).digest())
    return f"{body}.{sig}"


def _unsign(token: str | None) -> dict | None:
    """Payload eines gültig signierten, nicht abgelaufenen Tokens – sonst None."""
    if not token or "." not in token:
        return None
    try:
        body, sig = token.split(".", 1)
        expected = _b64e(hmac.new(_SECRET, body.encode("ascii"), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, expected):
            return None
        payload = json.loads(_b64d(body))
        if not isinstance(payload, dict) or int(payload.get("exp", 0)) < time.time():
            return None
        return payload
    except (ValueError, json.JSONDecodeError):
        return None


# ---------------------------------------------------------------------------
# Sitzungen
# ---------------------------------------------------------------------------
def make_token(email: str, session_version: int = 0) -> str:
    return _sign({"purpose": "session", "email": email, "sv": int(session_version),
                  "exp": int(time.time()) + TOKEN_TTL})


def read_session(token: str | None) -> dict | None:
    """
    {"email", "sv"} aus einem Sitzungs-Token, sonst None.
    Ältere Sitzungs-Token haben kein "purpose"-Feld und bleiben bis zum Ablauf
    gültig; jedes andere Token (z. B. ein Bestätigungslink) wird abgelehnt.
    """
    payload = _unsign(token)
    if not payload or payload.get("purpose", "session") != "session":
        return None
    if not payload.get("email"):
        return None
    return {"email": payload["email"], "sv": int(payload.get("sv", 0))}


def read_token(token: str | None) -> str | None:
    """E-Mail aus einem gültigen Sitzungs-Token (Kompatibilität)."""
    session = read_session(token)
    return session["email"] if session else None


# ---------------------------------------------------------------------------
# Zweckgebundene Aktions-Token
# ---------------------------------------------------------------------------
def make_action_token(email: str, purpose: str, ttl_seconds: int, **extra) -> str:
    if purpose == "session":
        raise ValueError("Aktions-Token dürfen keine Sitzung sein.")
    payload = {"email": (email or "").strip().lower(), "purpose": purpose,
               "exp": int(time.time()) + int(ttl_seconds), **extra}
    return _sign(payload)


def read_action_payload(token: str | None, purpose: str) -> dict | None:
    """Payload eines gültigen Aktions-Tokens mit passendem Zweck, sonst None."""
    payload = _unsign(token)
    if not payload or payload.get("purpose") != purpose or not payload.get("email"):
        return None
    return payload


def read_action_token(token: str | None, purpose: str) -> str | None:
    """E-Mail aus einem gültigen Aktions-Token mit passendem Zweck, sonst None."""
    payload = read_action_payload(token, purpose)
    return payload["email"] if payload else None
