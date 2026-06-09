"""
Einfaches In-Memory-Rate-Limiting für Riot Music.

Zählt fehlgeschlagene Login-Versuche pro IP und sperrt nach MAX_ATTEMPTS
für LOCKOUT_SECONDS. Kein externer Dienst nötig (Redis etc.).

Hinweis: Bei mehreren uvicorn-Workern hat jeder Worker seinen eigenen Zähler.
Für den Single-Worker-Betrieb (unser Fall) reicht das.
"""
from __future__ import annotations

import threading
import time

MAX_ATTEMPTS = 5        # Versuche pro Fenster
WINDOW_SECONDS = 60     # Zeitfenster
LOCKOUT_SECONDS = 900   # 15 Minuten Sperre nach zu vielen Versuchen

# Registrierungs-Limit (gegen Bot-Massen-Anlage)
REG_MAX_PER_HOUR = 3
REG_WINDOW_SECONDS = 3600

# Kontaktformular-Limit (gegen Mail-Spam-Wellen)
CONTACT_MAX_PER_HOUR = 5
CONTACT_WINDOW_SECONDS = 3600

_lock = threading.Lock()
_attempts: dict[str, list[float]] = {}   # IP → Liste von Zeitstempeln
_lockouts: dict[str, float] = {}         # IP → Entsperr-Zeitpunkt
_registrations: dict[str, list[float]] = {}   # IP → Zeitstempel der Registrierungen
_contacts: dict[str, list[float]] = {}        # IP → Zeitstempel der Kontaktanfragen


def _cleanup_old(ip: str) -> None:
    """Alte Einträge außerhalb des Fensters entfernen."""
    now = time.time()
    cutoff = now - WINDOW_SECONDS
    if ip in _attempts:
        _attempts[ip] = [t for t in _attempts[ip] if t > cutoff]
        if not _attempts[ip]:
            del _attempts[ip]


def is_locked(ip: str) -> bool:
    """Ist diese IP aktuell gesperrt?"""
    with _lock:
        until = _lockouts.get(ip, 0)
        if until > time.time():
            return True
        if ip in _lockouts:
            del _lockouts[ip]
        return False


def remaining_seconds(ip: str) -> int:
    """Sekunden bis Entsperrung (0 = nicht gesperrt)."""
    with _lock:
        until = _lockouts.get(ip, 0)
        remaining = until - time.time()
        return max(0, int(remaining))


def record_failure(ip: str) -> bool:
    """Fehlversuch registrieren. Gibt True zurück, wenn die IP jetzt gesperrt wird."""
    with _lock:
        _cleanup_old(ip)
        now = time.time()
        _attempts.setdefault(ip, []).append(now)
        if len(_attempts[ip]) >= MAX_ATTEMPTS:
            _lockouts[ip] = now + LOCKOUT_SECONDS
            _attempts.pop(ip, None)
            return True
        return False


def record_success(ip: str) -> None:
    """Erfolgreicher Login: Zähler zurücksetzen."""
    with _lock:
        _attempts.pop(ip, None)
        _lockouts.pop(ip, None)


def _prune_registrations_locked(ip: str) -> list[float]:
    now = time.time()
    cutoff = now - REG_WINDOW_SECONDS
    pruned = [t for t in _registrations.get(ip, []) if t > cutoff]
    if pruned:
        _registrations[ip] = pruned
    else:
        _registrations.pop(ip, None)
    return pruned


def registration_blocked(ip: str) -> bool:
    """Hat diese IP das Stunden-Registrierungs-Limit erreicht?"""
    with _lock:
        return len(_prune_registrations_locked(ip)) >= REG_MAX_PER_HOUR


def record_registration(ip: str) -> None:
    """Eine (erfolgreiche) Registrierung von dieser IP verbuchen."""
    with _lock:
        _prune_registrations_locked(ip)
        _registrations.setdefault(ip, []).append(time.time())


def _prune_contacts_locked(ip: str) -> list[float]:
    now = time.time()
    cutoff = now - CONTACT_WINDOW_SECONDS
    pruned = [t for t in _contacts.get(ip, []) if t > cutoff]
    if pruned:
        _contacts[ip] = pruned
    else:
        _contacts.pop(ip, None)
    return pruned


def contact_blocked(ip: str) -> bool:
    """Hat diese IP das Stunden-Limit für Kontaktanfragen erreicht?"""
    with _lock:
        return len(_prune_contacts_locked(ip)) >= CONTACT_MAX_PER_HOUR


def record_contact(ip: str) -> None:
    """Eine Kontaktanfrage von dieser IP verbuchen."""
    with _lock:
        _prune_contacts_locked(ip)
        _contacts.setdefault(ip, []).append(time.time())
