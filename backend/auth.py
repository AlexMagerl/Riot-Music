"""
Authentifizierung für Riot Music – ohne externe Abhängigkeiten.

  * Passwort-Hashing via PBKDF2-HMAC-SHA256 (Standardbibliothek).
  * Sitzungs-Token: stateless, HMAC-signiert (überlebt Server-Reloads),
    wird als HttpOnly-Cookie gesetzt.

Hinweis: Für einen Prototyp ausreichend. Für Produktion zusätzlich HTTPS,
Secure-Cookie-Flag, Rate-Limiting und ggf. bcrypt/argon2 erwägen.
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

ITERATIONS = 200_000
TOKEN_TTL = 60 * 60 * 24 * 14  # 14 Tage
COOKIE_NAME = "rm_session"


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


# ---------------------------------------------------------------------------
# Token (signiert, stateless)
# ---------------------------------------------------------------------------
def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64d(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def make_token(email: str) -> str:
    payload = {"email": email, "exp": int(time.time()) + TOKEN_TTL}
    body = _b64e(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    sig = _b64e(hmac.new(_SECRET, body.encode("ascii"), hashlib.sha256).digest())
    return f"{body}.{sig}"


def read_token(token: str | None) -> str | None:
    """Gibt die E-Mail aus einem gültigen, nicht abgelaufenen Token zurück, sonst None."""
    if not token or "." not in token:
        return None
    try:
        body, sig = token.split(".", 1)
        expected = _b64e(hmac.new(_SECRET, body.encode("ascii"), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, expected):
            return None
        payload = json.loads(_b64d(body))
        if int(payload.get("exp", 0)) < time.time():
            return None
        return payload.get("email")
    except (ValueError, json.JSONDecodeError):
        return None


# ---------------------------------------------------------------------------
# Zweckgebundene Aktions-Token (z. B. E-Mail-Bestätigung) – ebenfalls stateless
# ---------------------------------------------------------------------------
def make_action_token(email: str, purpose: str, ttl_seconds: int) -> str:
    payload = {"email": (email or "").strip().lower(),
               "purpose": purpose,
               "exp": int(time.time()) + int(ttl_seconds)}
    body = _b64e(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    sig = _b64e(hmac.new(_SECRET, body.encode("ascii"), hashlib.sha256).digest())
    return f"{body}.{sig}"


def read_action_token(token: str | None, purpose: str) -> str | None:
    """E-Mail aus einem gültigen Aktions-Token mit passendem Zweck, sonst None."""
    if not token or "." not in token:
        return None
    try:
        body, sig = token.split(".", 1)
        expected = _b64e(hmac.new(_SECRET, body.encode("ascii"), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, expected):
            return None
        payload = json.loads(_b64d(body))
        if payload.get("purpose") != purpose:
            return None
        if int(payload.get("exp", 0)) < time.time():
            return None
        return payload.get("email")
    except (ValueError, json.JSONDecodeError):
        return None
