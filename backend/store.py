"""
Datenhaltung für Riot Music.

Hält den Katalog im Speicher, schreibt Änderungen atomar nach catalog.json zurück
und bietet CRUD-Helfer für Künstler:innen, Releases und Tracks.
Threadsicher über ein einfaches Lock (genügt für den uvicorn-Single-Worker-Betrieb).
"""
from __future__ import annotations

import json
import os
import re
import threading
import unicodedata
import uuid
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
CATALOG_PATH = BASE_DIR / "data" / "catalog.json"

RELEASE_TYPES = {"Album", "EP", "Single"}

_lock = threading.RLock()
_catalog: dict | None = None
_cat_mtime: float = 0


# ---------------------------------------------------------------------------
# Laden / Speichern
# ---------------------------------------------------------------------------
def _load() -> dict:
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))


def _file_mtime() -> float:
    try:
        return CATALOG_PATH.stat().st_mtime
    except OSError:
        return 0


def catalog() -> dict:
    global _catalog, _cat_mtime
    with _lock:
        mt = _file_mtime()
        if _catalog is None or mt > _cat_mtime:
            _catalog = _load()
            _cat_mtime = mt
        return _catalog


def save() -> None:
    """Atomar speichern (erst in temp-Datei, dann ersetzen)."""
    global _cat_mtime
    with _lock:
        tmp = CATALOG_PATH.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(catalog(), ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, CATALOG_PATH)
        _cat_mtime = _file_mtime()


# ---------------------------------------------------------------------------
# Hilfen
# ---------------------------------------------------------------------------
def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return text or "x"


def _unique_id(base: str, taken: set[str]) -> str:
    candidate = base
    n = 2
    while candidate in taken:
        candidate = f"{base}-{n}"
        n += 1
    return candidate


def all_artist_ids() -> set[str]:
    return {a["id"] for a in catalog()["artists"]}


def all_release_ids() -> set[str]:
    return {r["id"] for a in catalog()["artists"] for r in a["releases"]}


def all_track_ids() -> set[str]:
    return {t["id"] for a in catalog()["artists"] for r in a["releases"] for t in r["tracks"]}


# ---------------------------------------------------------------------------
# Lookups
# ---------------------------------------------------------------------------
def find_artist(artist_id: str) -> dict | None:
    return next((a for a in catalog()["artists"] if a["id"] == artist_id), None)


def find_release(release_id: str):
    """-> (artist, release) oder (None, None)"""
    for a in catalog()["artists"]:
        for r in a["releases"]:
            if r["id"] == release_id:
                return a, r
    return None, None


def find_track(track_id: str):
    """-> (artist, release, track) oder (None, None, None)"""
    for a in catalog()["artists"]:
        for r in a["releases"]:
            for t in r["tracks"]:
                if t["id"] == track_id:
                    return a, r, t
    return None, None, None


# ---------------------------------------------------------------------------
# Genres – frei wählbar, dynamisch aus den Daten abgeleitet
# ---------------------------------------------------------------------------
def track_genre(release: dict, track: dict) -> str:
    """Effektives Genre eines Tracks: eigener Override sonst das des Releases."""
    return (track.get("genre") or release.get("genre") or "").strip()


def artist_genres(artist: dict) -> list[str]:
    """Sortierte, eindeutige Genres, die in den Releases/Tracks einer:s Künstler:in vorkommen."""
    seen = []
    for r in artist["releases"]:
        for g in [r.get("genre", "")] + [t.get("genre", "") for t in r["tracks"]]:
            g = (g or "").strip()
            if g and g not in seen:
                seen.append(g)
    return sorted(seen, key=str.casefold)


def all_genres() -> list[str]:
    """Alle tatsächlich verwendeten Genres über den ganzen Katalog."""
    seen = set()
    for a in catalog()["artists"]:
        seen.update(artist_genres(a))
    return sorted(seen, key=str.casefold)


# ---------------------------------------------------------------------------
# Künstler:innen
# ---------------------------------------------------------------------------
def add_artist(name: str, location: str = "", bio: str = "") -> dict:
    with _lock:
        artist = {
            "id": _unique_id(slugify(name), all_artist_ids()),
            "name": name.strip(),
            "location": location.strip(),
            "bio": bio.strip(),
            "image": None,
            "imageThumb": None,
            "releases": [],
        }
        catalog()["artists"].append(artist)
        save()
        return artist


def update_artist(artist_id: str, **fields) -> dict | None:
    with _lock:
        artist = find_artist(artist_id)
        if not artist:
            return None
        for key in ("name", "location", "bio", "image", "imageThumb", "banner", "paypal", "videoUrls", "social"):
            if key in fields and fields[key] is not None:
                artist[key] = fields[key]
        save()
        return artist


def delete_artist(artist_id: str) -> bool:
    with _lock:
        artists = catalog()["artists"]
        idx = next((i for i, a in enumerate(artists) if a["id"] == artist_id), None)
        if idx is None:
            return False
        artists.pop(idx)
        save()
        return True


# ---------------------------------------------------------------------------
# Releases
# ---------------------------------------------------------------------------
def add_release(artist_id: str, title: str, rtype: str, year: int, genre: str = "") -> dict | None:
    with _lock:
        artist = find_artist(artist_id)
        if not artist:
            return None
        release = {
            "id": _unique_id(f"{artist_id}-{slugify(title)}", all_release_ids()),
            "title": title.strip(),
            "type": rtype if rtype in RELEASE_TYPES else "Single",
            "year": int(year),
            "genre": (genre or "").strip(),
            "cover": None,
            "coverThumb": None,
            "tracks": [],
        }
        artist["releases"].append(release)
        save()
        return release


def update_release(release_id: str, **fields) -> dict | None:
    with _lock:
        _, release = find_release(release_id)
        if not release:
            return None
        if fields.get("title") is not None:
            release["title"] = fields["title"].strip()
        if fields.get("type") in RELEASE_TYPES:
            release["type"] = fields["type"]
        if fields.get("year") is not None:
            release["year"] = int(fields["year"])
        if fields.get("genre") is not None:
            release["genre"] = fields["genre"].strip()
        for key in ("cover", "coverThumb"):
            if key in fields and fields[key] is not None:
                release[key] = fields[key]
        save()
        return release


def delete_release(release_id: str) -> bool:
    with _lock:
        artist, release = find_release(release_id)
        if not release:
            return False
        artist["releases"].remove(release)
        save()
        return True


# ---------------------------------------------------------------------------
# Tracks
# ---------------------------------------------------------------------------
def add_track(release_id: str, title: str, filename: str, duration: int = 0,
              genre: str = "") -> dict | None:
    with _lock:
        artist, release = find_release(release_id)
        if not release:
            return None
        track = {
            "id": _unique_id(f"{release_id}-{uuid.uuid4().hex[:6]}", all_track_ids()),
            "title": title.strip(),
            "duration": int(duration),
            "file": filename,
        }
        if (genre or "").strip():
            track["genre"] = genre.strip()
        release["tracks"].append(track)
        save()
        return track


def update_track(track_id: str, **fields) -> dict | None:
    with _lock:
        _, _, track = find_track(track_id)
        if not track:
            return None
        if fields.get("title") is not None:
            track["title"] = fields["title"].strip()
        if fields.get("genre") is not None:
            g = fields["genre"].strip()
            if g:
                track["genre"] = g
            else:
                track.pop("genre", None)
        save()
        return track


def delete_track(track_id: str) -> bool:
    with _lock:
        _, release, track = find_track(track_id)
        if not track:
            return False
        release["tracks"].remove(track)
        save()
        return True
