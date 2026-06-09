"""
Einfaches Mathe-Captcha für die Registrierung — gegen Bot-Schwemme.

Stateless aus Sicht der Clients (ID + Antwort), serverseitig in einem In-Memory-Store
mit kurzer Lebensdauer. Challenges sind single-use: einmal verifiziert (egal ob
korrekt oder falsch) wird sie entfernt.
"""
from __future__ import annotations

import random
import secrets
import threading
import time

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
