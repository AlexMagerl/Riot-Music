"""
Benutzerkonten für Riot Music (Künstler-Logins).

Speichert Accounts in data/users.json. Jeder Account ist mit genau einer:m
Künstler:in (artistId) verknüpft. Threadsicher, atomares Schreiben.
"""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
USERS_PATH = BASE_DIR / "data" / "users.json"

_lock = threading.RLock()
_data: dict | None = None
_mtime: float = 0  # Zeitstempel der geladenen Datei


def _load() -> dict:
    if USERS_PATH.exists():
        return json.loads(USERS_PATH.read_text(encoding="utf-8"))
    return {"users": []}


def _file_mtime() -> float:
    try:
        return USERS_PATH.stat().st_mtime
    except OSError:
        return 0


def data() -> dict:
    global _data, _mtime
    with _lock:
        mt = _file_mtime()
        if _data is None or mt > _mtime:
            _data = _load()
            _mtime = mt
        return _data


def save() -> None:
    global _mtime
    with _lock:
        USERS_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = USERS_PATH.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data(), ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, USERS_PATH)
        _mtime = _file_mtime()


def find_user(email: str) -> dict | None:
    email = (email or "").strip().lower()
    return next((u for u in data()["users"] if u["email"] == email), None)


def find_by_artist(artist_id: str) -> dict | None:
    return next((u for u in data()["users"] if u.get("artistId") == artist_id), None)


def add_user(email: str, password_hash: str, artist_id: str,
             role: str = "artist", verified: bool = True) -> dict:
    with _lock:
        user = {
            "email": email.strip().lower(),
            "password": password_hash,
            "artistId": artist_id,
            "role": role,
            "createdAt": int(time.time()),
            "verified": bool(verified),
            "verifiedAt": int(time.time()) if verified else None,
        }
        data()["users"].append(user)
        save()
        return user


def is_verified(user: dict | None) -> bool:
    """
    Ist der Account E-Mail-bestätigt? Fehlt das Flag (Alt-Accounts), gilt er als
    bestätigt (Bestandsschutz). Admins gelten immer als bestätigt.
    """
    if not user:
        return False
    if user.get("role") == "admin":
        return True
    return user.get("verified", True)


def set_verified(email: str) -> dict | None:
    """Markiert einen Account als bestätigt. Gibt den Account zurück."""
    with _lock:
        user = find_user(email)
        if not user:
            return None
        user["verified"] = True
        user["verifiedAt"] = int(time.time())
        save()
        return user


def list_unverified() -> list[dict]:
    return [u for u in data()["users"]
            if u.get("role") != "admin" and not u.get("verified", True)]


def prune_unverified(older_than_seconds: int) -> list[str]:
    """
    Entfernt unbestätigte Accounts, die älter als `older_than_seconds` sind.
    Gibt die Liste der zugehörigen artistIds zurück (zum Aufräumen der Profile).
    """
    cutoff = int(time.time()) - int(older_than_seconds)
    removed_artist_ids = []
    with _lock:
        users = data()["users"]
        keep = []
        for u in users:
            if (u.get("role") != "admin" and not u.get("verified", True)
                    and u.get("createdAt", 0) < cutoff):
                if u.get("artistId"):
                    removed_artist_ids.append(u["artistId"])
            else:
                keep.append(u)
        if len(keep) != len(users):
            data()["users"] = keep
            save()
    return removed_artist_ids


def has_admin() -> bool:
    """Gibt es bereits mindestens einen Admin-Account?"""
    return any(u.get("role") == "admin" for u in data()["users"])


def is_admin(user: dict | None) -> bool:
    return bool(user and user.get("role") == "admin")


def delete_by_artist(artist_id: str) -> None:
    """Verwaister Account-Aufräumer, wenn ein:e Künstler:in (z.B. per Admin) gelöscht wird."""
    with _lock:
        users = data()["users"]
        keep = [u for u in users if u.get("artistId") != artist_id]
        if len(keep) != len(users):
            data()["users"] = keep
            save()
