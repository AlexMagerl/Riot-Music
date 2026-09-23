"""
Captcha für Registrierung und Kontaktformular — gegen Bot-Schwemme.

Sind im Admin-Bereich Sitekey und API-Key von Friendly Captcha hinterlegt,
wird dessen Proof-of-Work-Widget genutzt (serverseitige Prüfung über die
siteverify-API). Andernfalls greift das eingebaute Mathe-Captcha.

Mathe-Captcha: Stateless aus Sicht der Clients (ID + Antwort), serverseitig in
einem In-Memory-Store mit kurzer Lebensdauer. Challenges sind single-use:
einmal verifiziert (egal ob korrekt oder falsch) wird sie entfernt.
"""
from __future__ import annotations

import json
import logging
import random
import secrets
import threading
import time
import urllib.error
import urllib.request

import config

log = logging.getLogger("riotmusic.captcha")

FRC_VERIFY_URL = "https://global.frcapi.com/api/v2/captcha/siteverify"
FRC_ID = "frc"               # captchaId, mit dem das Frontend Friendly-Antworten markiert

TTL_SECONDS = 600           # 10 Minuten
MAX_STORED = 10_000         # Schutz gegen unbegrenztes Wachstum

_lock = threading.Lock()
_store: dict[str, tuple[int, float]] = {}   # id -> (answer, expires_at)


def _gc_locked() -> None:
    """Abgelaufene Challenges entfernen. Muss innerhalb des Locks aufgerufen werden."""
    now = time.time()
    expired = [k for k, (_, exp) in _store.items() if exp < now]
    for k in expired:
        _store.pop(k, None)
    # Falls trotzdem zu viele: die ältesten rauswerfen.
    if len(_store) > MAX_STORED:
        oldest = sorted(_store.items(), key=lambda kv: kv[1][1])[: len(_store) - MAX_STORED]
        for k, _ in oldest:
            _store.pop(k, None)


def create_challenge() -> dict:
    """Erzeugt eine neue Challenge und gibt {id, question} zurück."""
    a = random.randint(1, 9)
    b = random.randint(1, 9)
    op = random.choice(["+", "-"])
    if op == "-" and b > a:
        a, b = b, a   # negative Ergebnisse vermeiden
    answer = a + b if op == "+" else a - b
    cid = secrets.token_urlsafe(12)
    with _lock:
        _gc_locked()
        _store[cid] = (answer, time.time() + TTL_SECONDS)
    return {"id": cid, "question": f"Wie viel ist {a} {op} {b}?"}


def verify(cid: str | None, answer: str | None) -> bool:
    """Prüft eine Antwort. Die Challenge wird in jedem Fall verbraucht (single-use)."""
    if not cid or answer is None:
        return False
    with _lock:
        entry = _store.pop(cid, None)
    if not entry:
        return False
    expected, exp = entry
    if exp < time.time():
        return False
    try:
        return int(str(answer).strip()) == expected
    except (TypeError, ValueError):
        return False


# ---------------------------------------------------------------------------
# Friendly Captcha
# ---------------------------------------------------------------------------
def _friendly_keys() -> tuple[str, str] | None:
    cfg = config.load()
    sitekey = (cfg.get("frc_sitekey") or "").strip()
    api_key = (cfg.get("frc_api_key") or "").strip()
    return (sitekey, api_key) if sitekey and api_key else None


def public_challenge() -> dict:
    """Was das Frontend zum Anzeigen braucht: Friendly-Sitekey oder Mathe-Frage."""
    keys = _friendly_keys()
    if keys:
        return {"provider": "friendly", "sitekey": keys[0]}
    return {"provider": "math", **create_challenge()}


def _verify_friendly(response: str, sitekey: str, api_key: str) -> bool:
    body = json.dumps({"response": response, "sitekey": sitekey}).encode("utf-8")
    req = urllib.request.Request(
        FRC_VERIFY_URL, data=body, method="POST",
        headers={"Content-Type": "application/json", "X-API-Key": api_key},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as res:
            return bool(json.loads(res.read().decode("utf-8")).get("success"))
    except urllib.error.HTTPError as exc:
        if exc.code >= 500:
            # Friendly-API gestört: nicht alle Menschen aussperren.
            # E-Mail-Bestätigung und Admin-Freigabe greifen trotzdem.
            log.warning("Friendly Captcha nicht erreichbar (%s) – Anfrage zugelassen.", exc.code)
            return True
        # 4xx: ungültige Antwort oder falscher API-Key/Sitekey.
        log.warning("Friendly Captcha abgelehnt (%s): %s", exc.code,
                    exc.read()[:300].decode("utf-8", "replace"))
        return False
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        log.warning("Friendly Captcha nicht erreichbar (%s) – Anfrage zugelassen.", exc)
        return True


def check(cid: str | None, answer: str | None) -> bool:
    """Prüft eine Captcha-Antwort mit dem aktuell aktiven Verfahren."""
    keys = _friendly_keys()
    if keys:
        # Mathe-Antworten werden dann nicht mehr akzeptiert – sonst könnten Bots
        # das stärkere Captcha einfach umgehen.
        if cid != FRC_ID or not (answer or "").strip():
            return False
        return _verify_friendly(answer.strip(), *keys)
    return verify(cid, answer)
