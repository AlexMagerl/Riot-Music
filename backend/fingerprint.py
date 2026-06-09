"""
Audio-Fingerprinting via Chromaprint + (optional) AcoustID.

Verhindert, dass derselbe Song mehrfach hochgeladen wird (lokale Hash-DB)
und kann Uploads gegen die offene AcoustID-Datenbank prüfen, um bekannte
Songs (z. B. Beyoncé-Hits) bereits beim Upload abzufangen.

Hängt von einem extern installierten `fpcalc`-Binary ab (Chromaprint).
Wenn es nicht vorhanden ist, fällt das Modul gracefully zurück und gibt
None zurück — der Upload geht trotzdem durch.

`fpcalc` herunterladen: https://acoustid.org/chromaprint
AcoustID-API-Key beantragen (kostenlos): https://acoustid.org/api-key
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import subprocess
import threading
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import config

log = logging.getLogger("riotmusic.fingerprint")

BASE_DIR = Path(__file__).resolve().parent
STORE_PATH = BASE_DIR / "data" / "fingerprints.json"
ACOUSTID_URL = "https://api.acoustid.org/v2/lookup"
ACOUSTID_TIMEOUT = 10
FPCALC_TIMEOUT = 30      # Sekunden – Chromaprint ist schnell, aber Schutz vor Hängern

# AcoustID: Score 0–1, ab welchem Wert wir einen Match als "bekannt" werten.
ACOUSTID_MATCH_THRESHOLD = 0.85

_lock = threading.RLock()


# ---------------------------------------------------------------------------
# fpcalc-Wrapper
# ---------------------------------------------------------------------------
# Lokaler Ordner, in dem wir die fpcalc-Binary erwarten (mitgeliefert).
# Vorteil: kein PATH-Setup auf dem Server nötig, Dev/Prod identisch.
LOCAL_BIN_DIR = BASE_DIR / "bin"


def _fpcalc_path() -> str | None:
    """
    Sucht fpcalc in dieser Reihenfolge:
      1. backend/bin/fpcalc(.exe)   — mit dem Repo ausgeliefert
      2. System-PATH                 — Fallback für manuelle Installation
    Gibt None zurück, wenn nirgends gefunden.
    """
    candidates = [
        LOCAL_BIN_DIR / "fpcalc.exe",   # Windows
        LOCAL_BIN_DIR / "fpcalc",       # Linux / macOS
    ]
    for c in candidates:
        if c.is_file() and os.access(c, os.X_OK if c.suffix != ".exe" else os.F_OK):
            return str(c)
    return shutil.which("fpcalc") or shutil.which("fpcalc.exe")


def fpcalc_available() -> bool:
    return _fpcalc_path() is not None


def compute(audio_path: Path) -> dict | None:
    """
    Berechnet Chromaprint-Fingerprint und Dauer der Audiodatei.

    Gibt `{"fingerprint": "<str>", "duration": <int>, "hash": "<sha256>"}`
    zurück oder None, wenn fpcalc nicht verfügbar oder die Analyse fehlschlägt.
    """
    exe = _fpcalc_path()
    if not exe:
        log.info("fpcalc nicht gefunden – Fingerprinting deaktiviert.")
        return None
    try:
        # -json liefert {"duration": 123.45, "fingerprint": "AQAA..."}
        result = subprocess.run(
            [exe, "-json", str(audio_path)],
            capture_output=True, text=True, timeout=FPCALC_TIMEOUT,
        )
        if result.returncode != 0:
            log.warning("fpcalc returncode %s: %s", result.returncode, result.stderr.strip())
            return None
        data = json.loads(result.stdout)
        fp = data.get("fingerprint")
        dur = data.get("duration")
        if not fp or dur is None:
            return None
        return {
            "fingerprint": fp,
            "duration": int(round(float(dur))),
            "hash": hashlib.sha256(fp.encode("ascii")).hexdigest(),
        }
    except (subprocess.TimeoutExpired, OSError, json.JSONDecodeError, ValueError) as exc:
        log.warning("fpcalc-Fehler: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Lokale Fingerprint-Datenbank
# ---------------------------------------------------------------------------
def _load() -> dict:
    if not STORE_PATH.exists():
        return {"entries": []}
    try:
        data = json.loads(STORE_PATH.read_text(encoding="utf-8"))
        if "entries" not in data:
            data["entries"] = []
        return data
    except (json.JSONDecodeError, OSError):
        return {"entries": []}


def _save(data: dict) -> None:
    STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = STORE_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, STORE_PATH)


def find_duplicate(fp: dict) -> dict | None:
    """Sucht einen identischen Chromaprint-Hash. Gibt den Eintrag oder None zurück."""
    with _lock:
        data = _load()
        for entry in data["entries"]:
            if entry.get("hash") == fp["hash"]:
                return entry
    return None


def register(fp: dict, track_id: str, artist_id: str,
             acoustid_match: dict | None = None) -> None:
    """Speichert einen Fingerprint zusammen mit dem zugehörigen Track."""
    if not fp:
        return
    entry = {
        "hash": fp["hash"],
        "duration": fp["duration"],
        "trackId": track_id,
        "artistId": artist_id,
        "createdAt": datetime.now(tz=timezone.utc).isoformat(),
    }
    if acoustid_match:
        entry["acoustid"] = acoustid_match
    with _lock:
        data = _load()
        data["entries"].append(entry)
        _save(data)


def unregister_track(track_id: str) -> None:
    """Entfernt alle Einträge zu einem Track (z. B. beim Löschen)."""
    with _lock:
        data = _load()
        before = len(data["entries"])
        data["entries"] = [e for e in data["entries"] if e.get("trackId") != track_id]
        if len(data["entries"]) != before:
            _save(data)


def unregister_artist(artist_id: str) -> None:
    """Entfernt alle Einträge eines Künstlers (Profil-Löschung)."""
    with _lock:
        data = _load()
        before = len(data["entries"])
        data["entries"] = [e for e in data["entries"] if e.get("artistId") != artist_id]
        if len(data["entries"]) != before:
            _save(data)


def count() -> int:
    with _lock:
        return len(_load()["entries"])


# ---------------------------------------------------------------------------
# AcoustID-Abfrage (optional, braucht API-Key)
# ---------------------------------------------------------------------------
def acoustid_configured() -> bool:
    return bool((config.load().get("acoustid_api_key") or "").strip())


def lookup_acoustid(fp: dict) -> dict | None:
    """
    Fragt die AcoustID-Datenbank ab. Gibt bei (gutem) Match ein Dict mit
    Künstler/Titel/Score zurück, sonst None.
    """
    api_key = (config.load().get("acoustid_api_key") or "").strip()
    if not api_key or not fp:
        return None
    params = {
        "client": api_key,
        "format": "json",
        "meta": "recordings",
        "duration": str(fp["duration"]),
        "fingerprint": fp["fingerprint"],
    }
    url = f"{ACOUSTID_URL}?{urllib.parse.urlencode(params)}"
    try:
        with urllib.request.urlopen(url, timeout=ACOUSTID_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        log.warning("AcoustID-Abfrage fehlgeschlagen: %s", exc)
        return None
    if data.get("status") != "ok":
        return None
    best = None
    for r in data.get("results", []):
        score = r.get("score", 0)
        if score < ACOUSTID_MATCH_THRESHOLD:
            continue
        if best and best["score"] >= score:
            continue
        rec = (r.get("recordings") or [{}])[0]
        artists = rec.get("artists") or []
        artist_names = ", ".join(a.get("name", "") for a in artists if a.get("name"))
        best = {
            "score": round(score, 3),
            "title": rec.get("title") or "",
            "artist": artist_names,
            "recordingId": rec.get("id") or "",
        }
    return best


# ---------------------------------------------------------------------------
# Hochstellige Hilfsfunktion: alles auf einmal
# ---------------------------------------------------------------------------
def analyse(audio_path: Path) -> dict:
    """
    Komplette Analyse: Fingerprint berechnen, lokal auf Duplikat prüfen,
    AcoustID befragen.

    Gibt zurück:
        {
          "fingerprint": fp_dict | None,
          "duplicate": entry_dict | None,    # lokaler Duplikat-Treffer
          "acoustid":  match_dict  | None,   # bekannter Song aus AcoustID
        }
    """
    fp = compute(audio_path)
    if not fp:
        return {"fingerprint": None, "duplicate": None, "acoustid": None}
    duplicate = find_duplicate(fp)
    acoustid_match = lookup_acoustid(fp) if acoustid_configured() else None
    return {"fingerprint": fp, "duplicate": duplicate, "acoustid": acoustid_match}
