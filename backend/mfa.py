"""
Zwei-Faktor-Authentifizierung (2FA) für Riot Music – ohne externe Abhängigkeiten.

  * TOTP nach RFC 6238 (6 Ziffern, 30 Sekunden, SHA-1) – kompatibel mit
    Google Authenticator, Aegis, 2FAS, Bitwarden, 1Password usw.
  * Wiederherstellungscodes: 10 Einmal-Codes, gespeichert nur als SHA-256-Hash.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time
import urllib.parse

ISSUER = "Riot Music"
STEP = 30
DIGITS = 6
RECOVERY_COUNT = 10
_RECOVERY_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"   # ohne verwechselbare Zeichen


def new_secret() -> str:
    """Neues Base32-Geheimnis (160 Bit), wie es Authenticator-Apps erwarten."""
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def _code_at(secret: str, counter: int) -> str:
    key = base64.b32decode(secret.upper() + "=" * (-len(secret) % 8))
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    number = (struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF) % 10 ** DIGITS
    return f"{number:0{DIGITS}d}"


def verify(secret: str, code: str, last_step: int = 0, window: int = 1,
           now: float | None = None) -> int | None:
    """
    Prüft einen 6-stelligen Code (±1 Zeitfenster gegen Uhrabweichung).
    Gibt den verwendeten Zeitschritt zurück – der Aufrufer speichert ihn, damit
    derselbe Code nicht ein zweites Mal funktioniert. Sonst None.
    """
    code = "".join(ch for ch in (code or "") if ch.isdigit())
    if len(code) != DIGITS or not secret:
        return None
    current = int((time.time() if now is None else now) // STEP)
    for step in range(current - window, current + window + 1):
        if step > last_step and hmac.compare_digest(_code_at(secret, step), code):
            return step
    return None


def otpauth_uri(secret: str, account: str) -> str:
    """Inhalt des QR-Codes für die Authenticator-App."""
    label = urllib.parse.quote(f"{ISSUER}:{account}")
    issuer = urllib.parse.quote(ISSUER)
    return (f"otpauth://totp/{label}?secret={secret}&issuer={issuer}"
            f"&algorithm=SHA1&digits={DIGITS}&period={STEP}")


# ---------------------------------------------------------------------------
# Wiederherstellungscodes
# ---------------------------------------------------------------------------
def _normalize(code: str) -> str:
    return "".join(ch for ch in (code or "").lower() if ch.isalnum())


def hash_recovery_code(code: str) -> str:
    return hashlib.sha256(_normalize(code).encode("ascii", "ignore")).hexdigest()


def new_recovery_codes() -> tuple[list[str], list[str]]:
    """(Klartext-Codes zum einmaligen Anzeigen, Hashes zum Speichern)."""
    plain = []
    for _ in range(RECOVERY_COUNT):
        raw = "".join(secrets.choice(_RECOVERY_ALPHABET) for _ in range(10))
        plain.append(f"{raw[:5]}-{raw[5:]}")
    return plain, [hash_recovery_code(c) for c in plain]


def looks_like_recovery_code(code: str) -> bool:
    return len(_normalize(code)) == 10 and not _normalize(code).isdigit()


def consume_recovery_code(hashes: list[str], code: str) -> list[str] | None:
    """Gibt die Liste ohne den benutzten Code zurück – oder None, falls ungültig."""
    h = hash_recovery_code(code)
    match = next((x for x in hashes if hmac.compare_digest(x, h)), None)
    if match is None:
        return None
    return [x for x in hashes if x != match]
