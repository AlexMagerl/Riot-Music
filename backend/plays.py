"""
Play-Counting für Riot Music — speichert ab, wie oft Songs abgespielt wurden.

Daten persistent in data/plays.json. Threadsicher mit RLock.
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
PLAYS_PATH = BASE_DIR / "data" / "plays.json"

_lock = threading.RLock()
_data: dict | None = None
_mtime: float = 0


def _load() -> dict:
    """Lädt Play-Daten aus JSON. Format: {track_id: {count: N, last_played: timestamp}}"""
    if PLAYS_PATH.exists():
        try:
            return json.loads(PLAYS_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _file_mtime() -> float:
    try:
        return PLAYS_PATH.stat().st_mtime
    except OSError:
        return 0


def data() -> dict:
    """Lazy-load mit File-Mtime-Check."""
    global _data, _mtime
    with _lock:
        mt = _file_mtime()
        if _data is None or mt > _mtime:
            _data = _load()
            _mtime = mt
        return _data


def save() -> None:
    """Speichert Play-Daten, atomic."""
    global _mtime
    with _lock:
        PLAYS_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = PLAYS_PATH.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data(), ensure_ascii=False, indent=2), encoding="utf-8")
        import os
        os.replace(tmp, PLAYS_PATH)
        _mtime = _file_mtime()


def record_play(track_id: str) -> None:
    """Zählt einen Play für den Track."""
    with _lock:
        d = data()
        if track_id not in d:
            d[track_id] = {"count": 0, "last_played": 0}
        d[track_id]["count"] = d[track_id].get("count", 0) + 1
        d[track_id]["last_played"] = int(time.time())
        save()


def get_count(track_id: str) -> int:
    """Gibt die Play-Anzahl eines Tracks zurück."""
    with _lock:
        return data().get(track_id, {}).get("count", 0)


def get_top_tracks(track_ids: list[str], limit: int = 10) -> list[tuple[str, int]]:
    """
    Gibt die Top-N Tracks (nach Play-Count) aus einer Liste zurück.
    Rückgabe: [(track_id, count), ...] sorted by count DESC.
    """
    with _lock:
        d = data()
        counts = [(tid, d.get(tid, {}).get("count", 0)) for tid in track_ids]
        return sorted(counts, key=lambda x: x[1], reverse=True)[:limit]
