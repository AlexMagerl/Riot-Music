"""
Spenden-Button-Klicks für Riot Music.

WICHTIG: Hier werden NUR Button-Klicks gezählt, keine echten Spenden oder
Beträge. Die Plattform ist nicht am Zahlungsfluss beteiligt (siehe AGB § 6) –
tatsächliche Eingänge/Beträge sind nur im jeweiligen PayPal-Konto sichtbar.

Daten persistent in data/donate_clicks.json. Threadsicher mit RLock.
"""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
CLICKS_PATH = BASE_DIR / "data" / "donate_clicks.json"

_lock = threading.RLock()


def _load() -> dict:
    if CLICKS_PATH.exists():
        try:
            d = json.loads(CLICKS_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            d = {}
    else:
        d = {}
    d.setdefault("platform", {"count": 0, "last": 0})
    d.setdefault("artists", {})
    return d


def _save(d: dict) -> None:
    CLICKS_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = CLICKS_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, CLICKS_PATH)


def record_platform_click() -> None:
    with _lock:
        d = _load()
        d["platform"]["count"] = d["platform"].get("count", 0) + 1
        d["platform"]["last"] = int(time.time())
        _save(d)


def record_artist_click(artist_id: str) -> None:
    if not artist_id:
        return
    with _lock:
        d = _load()
        entry = d["artists"].setdefault(artist_id, {"count": 0, "last": 0})
        entry["count"] = entry.get("count", 0) + 1
        entry["last"] = int(time.time())
        _save(d)


def platform_count() -> int:
    with _lock:
        return _load()["platform"].get("count", 0)


def artist_count(artist_id: str) -> int:
    with _lock:
        return _load()["artists"].get(artist_id, {}).get("count", 0)


def total_artist_clicks() -> int:
    with _lock:
        return sum(a.get("count", 0) for a in _load()["artists"].values())
