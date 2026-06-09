"""
Riot Music – Backend (FastAPI).

Liefert:
  * Öffentliche JSON-Katalog-API        (/api/...)
  * Management-API ("Künstler-Studio")  (/api/manage/...)  – CRUD + Uploads
  * Audio-Streaming mit HTTP-Range      (/media/...)        – Seeking im Player
  * Statische Bilder (Künstler/Cover)   (/media/...)
  * Frontend (SPA + Studio)             (/)
"""
from __future__ import annotations

import mimetypes
import random
import re
import shutil
import urllib.parse
import uuid
import wave
from pathlib import Path

from fastapi import Cookie, Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

import accounts
import auth
import captcha
import config
import contact
import fingerprint
import images
import mail
import plays
import ratelimit
import social
import stats
import store
import video

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent
MEDIA_DIR = BASE_DIR / "media"
FRONTEND_DIR = PROJECT_DIR / "frontend"

CHUNK_SIZE = 1024 * 256  # 256 KB
AUDIO_EXTS = {".mp3"}  # Upload nur als MP3 erlaubt
ALLOWED_AUDIO_CT = {"audio/mpeg", "audio/mp3"}

VERIFY_TTL = 60 * 60 * 48          # E-Mail-Bestätigungslink: 48 Stunden gültig
UNVERIFIED_MAX_AGE = 60 * 60 * 24 * 7   # unbestätigte Accounts nach 7 Tagen löschbar

app = FastAPI(title="Riot Music API", version="0.3.0")


# ---------------------------------------------------------------------------
# Anreicherung: Bild-/Audio-URLs an die rohen Katalogdaten hängen
# ---------------------------------------------------------------------------
def _media_url(artist_id: str, filename: str | None) -> str | None:
    return f"/media/{artist_id}/{filename}" if filename else None


def _donate_url(paypal: str | None, artist_name: str) -> str | None:
    """
    Baut aus der PayPal-Angabe einer:s Künstler:in eine öffentliche Spenden-URL.

    Unterstützt:
      * E-Mail-Adresse        -> klassischer PayPal-Spendenlink (?business=...)
      * paypal.me / paypal.com-Link -> wird direkt verwendet
      * bloßer Handle         -> als paypal.me/<handle> interpretiert

    Gibt None zurück, wenn nichts (Brauchbares) hinterlegt ist.
    """
    value = (paypal or "").strip()
    if not value or "DEIN_PAYPAL" in value.upper():
        return None

    low = value.lower()
    # Bereits ein PayPal-Link?
    if "paypal.me" in low or "paypal.com" in low:
        return value if low.startswith("http") else f"https://{value}"

    # E-Mail -> klassischer Spenden-Button
    if EMAIL_RE.match(value):
        params = urllib.parse.urlencode({
            "cmd": "_donations",
            "business": value,
            "no_recurring": "0",
            "item_name": f"Spende für {artist_name} via Riot Music",
            "currency_code": "EUR",
        })
        return f"https://www.paypal.com/cgi-bin/webscr?{params}"

    # Sonst: als paypal.me-Handle behandeln (führendes @ entfernen)
    handle = value.lstrip("@")
    if "/" in handle or " " in handle:
        return None
    return f"https://www.paypal.me/{handle}"


def enrich_track(artist: dict, release: dict, track: dict) -> dict:
    filename = track.get("file") or f"{track['id']}.wav"
    return {
        "id": track["id"],
        "title": track["title"],
        "duration": track.get("duration", 0),
        "artistId": artist["id"],
        "artistName": artist["name"],
        "genre": store.track_genre(release, track),   # eigener Override sonst Release-Genre
        "trackGenre": track.get("genre", ""),          # nur der explizite Override (für Editoren)
        "releaseId": release["id"],
        "releaseTitle": release["title"],
        "year": release["year"],
        "url": _media_url(artist["id"], filename),
        "cover": _media_url(artist["id"], release.get("cover")),
        "coverThumb": _media_url(artist["id"], release.get("coverThumb")),
    }


def enrich_release(artist: dict, release: dict) -> dict:
    return {
        "id": release["id"],
        "title": release["title"],
        "type": release["type"],
        "year": release["year"],
        "genre": release.get("genre", ""),
        "cover": _media_url(artist["id"], release.get("cover")),
        "coverThumb": _media_url(artist["id"], release.get("coverThumb")),
        "tracks": [enrich_track(artist, release, t) for t in release["tracks"]],
    }


def artist_summary(artist: dict) -> dict:
    genres = store.artist_genres(artist)
    return {
        "id": artist["id"],
        "name": artist["name"],
        "genres": genres,                              # frei erfundene Genres dieser:s Künstler:in
        "genre": genres[0] if genres else "",          # primäres Genre für knappe Anzeigen
        "location": artist.get("location"),
        "image": _media_url(artist["id"], artist.get("image")),
        "imageThumb": _media_url(artist["id"], artist.get("imageThumb")),
        "banner": _media_url(artist["id"], artist.get("banner")),
        "releaseCount": len(artist["releases"]),
        "trackCount": sum(len(r["tracks"]) for r in artist["releases"]),
    }


def artist_full(artist: dict, include_private: bool = False) -> dict:
    # Top 10 Tracks (immer verfügbar, mit playCount nur im privaten Modus)
    top_tracks = []
    all_tracks = []
    for release in artist["releases"]:
        for track in release["tracks"]:
            all_tracks.append((track["id"], release))

    if all_tracks:
        track_ids = [t[0] for t in all_tracks]
        top_ids = plays.get_top_tracks(track_ids, limit=10)
        for track_id, _ in top_ids:
            for tid, rel in all_tracks:
                if tid == track_id:
                    track = next((t for t in rel["tracks"] if t["id"] == track_id), None)
                    if track:
                        enriched = {
                            **enrich_track(artist, rel, track),
                        }
                        if include_private:
                            enriched["playCount"] = plays.get_count(track_id)
                        top_tracks.append(enriched)
                    break

    out = {
        **artist_summary(artist),
        "bio": artist.get("bio", ""),
        "videoUrls": artist.get("videoUrls", []),
        "social": artist.get("social", {}),
        "topTracks": top_tracks,
        "releases": [enrich_release(artist, r) for r in artist["releases"]],
        # Öffentlicher Spendenlink (nur falls PayPal hinterlegt) – die rohe
        # Adresse selbst wird nicht ausgeliefert, nur die fertige URL.
        "donateUrl": _donate_url(artist.get("paypal"), artist["name"]),
    }
    if include_private:
        out["paypal"] = artist.get("paypal", "")
    return out


# ---------------------------------------------------------------------------
# Öffentliche API
# ---------------------------------------------------------------------------
@app.get("/api/platform")
def get_platform():
    plat = dict(store.catalog()["platform"])
    # Spendenlink für die Plattform aus den Admin-Einstellungen bauen.
    plat["donateUrl"] = _donate_url(config.load().get("platform_paypal"),
                                    plat.get("name", "Riot Music"))
    # Rohe Adresse nie ausliefern – nur die fertige URL.
    plat.pop("paypal", None)
    return plat


@app.get("/api/genres")
def get_genres():
    return store.all_genres()


def _artist_public(artist_id: str) -> bool:
    """
    Ist ein Künstlerprofil öffentlich sichtbar? Sichtbar, solange der zugehörige
    Account E-Mail-bestätigt ist. Profile ohne Account (z. B. Seed-Daten) bleiben
    sichtbar.
    """
    user = accounts.find_by_artist(artist_id)
    if user is None:
        return True
    return accounts.is_verified(user)


@app.get("/api/artists")
def get_artists(genre: str | None = None):
    out = []
    for artist in store.catalog()["artists"]:
        if not _artist_public(artist["id"]):
            continue
        if genre and genre not in store.artist_genres(artist):
            continue
        out.append(artist_summary(artist))
    return out


@app.get("/api/artists/{artist_id}")
def get_artist(artist_id: str):
    artist = store.find_artist(artist_id)
    if not artist or not _artist_public(artist_id):
        raise HTTPException(status_code=404, detail="Künstler:in nicht gefunden")
    return artist_full(artist)


@app.get("/api/tracks/{track_id}")
def get_track(track_id: str):
    artist, release, track = store.find_track(track_id)
    if not track:
        raise HTTPException(status_code=404, detail="Track nicht gefunden")
    return enrich_track(artist, release, track)


@app.get("/api/radio")
def radio(limit: int = 80):
    """Zufällig gemischte Songs der ganzen Plattform – für den Endlos-Radio-Modus."""
    all_tracks = []
    for artist in store.catalog()["artists"]:
        if not _artist_public(artist["id"]):
            continue
        for release in artist["releases"]:
            for track in release["tracks"]:
                all_tracks.append(enrich_track(artist, release, track))
    random.shuffle(all_tracks)
    return all_tracks[: max(1, limit)]


@app.get("/api/search")
def search(q: str = "", genre: str | None = None):
    needle = q.strip().lower()
    artists, releases, tracks = [], [], []
    for artist in store.catalog()["artists"]:
        if not _artist_public(artist["id"]):
            continue
        a_genres = store.artist_genres(artist)
        hay = f"{artist['name']} {' '.join(a_genres)} {artist.get('location', '')}".lower()
        if (not genre or genre in a_genres) and (not needle or needle in hay):
            artists.append(artist_summary(artist))
        for release in artist["releases"]:
            rgenre = release.get("genre", "")
            if (not genre or genre == rgenre) and \
                    (not needle or needle in release["title"].lower() or needle in rgenre.lower()):
                releases.append({**enrich_release(artist, release), "tracks": None,
                                 "artistId": artist["id"], "artistName": artist["name"]})
            for track in release["tracks"]:
                tg = store.track_genre(release, track)
                if (not genre or genre == tg) and \
                        (not needle or needle in track["title"].lower()
                         or needle in artist["name"].lower() or needle in tg.lower()):
                    tracks.append(enrich_track(artist, release, track))
    return {"query": q, "genre": genre, "artists": artists, "releases": releases, "tracks": tracks}


# ---------------------------------------------------------------------------
# Auth-Dependencies (vor Management & Studio, weil dort als Depends genutzt)
# ---------------------------------------------------------------------------
def _set_session(response: Response, email: str) -> None:
    response.set_cookie(
        auth.COOKIE_NAME, auth.make_token(email),
        max_age=auth.TOKEN_TTL, httponly=True, samesite="lax", path="/",
    )


def current_user(rm_session: str | None = Cookie(default=None)) -> dict | None:
    email = auth.read_token(rm_session)
    return accounts.find_user(email) if email else None


def require_artist(user: dict | None = Depends(current_user)) -> dict:
    if not user:
        raise HTTPException(status_code=401, detail="Bitte zuerst anmelden.")
    artist = store.find_artist(user["artistId"])
    if not artist:
        raise HTTPException(status_code=404, detail="Künstlerprofil nicht gefunden.")
    return artist


def require_admin(user: dict | None = Depends(current_user)) -> dict:
    if not user:
        raise HTTPException(status_code=401, detail="Bitte zuerst anmelden.")
    if not accounts.is_admin(user):
        raise HTTPException(status_code=403, detail="Kein Admin-Zugang.")
    return user


def _check_rate_limit(request: Request) -> None:
    ip = request.client.host if request.client else "unknown"
    if ratelimit.is_locked(ip):
        secs = ratelimit.remaining_seconds(ip)
        raise HTTPException(status_code=429,
                            detail=f"Zu viele Versuche. Bitte {secs}s warten.")


# ---------------------------------------------------------------------------
# Management-API (Admin-geschützt)
# ---------------------------------------------------------------------------
def _save_image(artist_id: str, base: str, upload: UploadFile) -> dict:
    data = upload.file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Leere Bilddatei")
    try:
        return images.save_square_image(data, MEDIA_DIR / artist_id, base)
    except images.InvalidImageError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


def _save_banner(artist_id: str, upload: UploadFile) -> str:
    data = upload.file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Leere Bilddatei")
    try:
        return images.save_banner_image(data, MEDIA_DIR / artist_id, "artist")
    except images.InvalidImageError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


def _safe_unlink(artist_id: str, *filenames: str | None) -> None:
    for name in filenames:
        if not name:
            continue
        p = (MEDIA_DIR / artist_id / name).resolve()
        if str(p).startswith(str(MEDIA_DIR.resolve())) and p.is_file():
            p.unlink(missing_ok=True)


@app.get("/api/manage/artists")
def manage_list_artists(_admin: dict = Depends(require_admin)):
    """Vollständige Liste inkl. Releases/Tracks – für die Admin-Oberfläche."""
    return [artist_full(a, include_private=True) for a in store.catalog()["artists"]]


@app.post("/api/manage/artists")
def create_artist(
    _admin: dict = Depends(require_admin),
    name: str = Form(...),
    location: str = Form(""),
    bio: str = Form(""),
    image: UploadFile | None = File(None),
    banner: UploadFile | None = File(None),
):
    if not name.strip():
        raise HTTPException(status_code=400, detail="Name ist Pflicht.")
    artist = store.add_artist(name=name, location=location, bio=bio)
    if image is not None and image.filename:
        res = _save_image(artist["id"], "artist", image)
        store.update_artist(artist["id"], image=res["image"], imageThumb=res["thumb"])
    if banner is not None and banner.filename:
        bname = _save_banner(artist["id"], banner)
        store.update_artist(artist["id"], banner=bname)
    return artist_full(store.find_artist(artist["id"]), include_private=True)


@app.put("/api/manage/artists/{artist_id}")
def edit_artist(
    artist_id: str,
    _admin: dict = Depends(require_admin),
    name: str | None = Form(None),
    location: str | None = Form(None),
    bio: str | None = Form(None),
    image: UploadFile | None = File(None),
    banner: UploadFile | None = File(None),
):
    if not store.find_artist(artist_id):
        raise HTTPException(status_code=404, detail="Künstler:in nicht gefunden")
    fields = {"name": name, "location": location, "bio": bio}
    if image is not None and image.filename:
        res = _save_image(artist_id, "artist", image)
        fields["image"] = res["image"]
        fields["imageThumb"] = res["thumb"]
    if banner is not None and banner.filename:
        fields["banner"] = _save_banner(artist_id, banner)
    store.update_artist(artist_id, **fields)
    return artist_full(store.find_artist(artist_id), include_private=True)


@app.get("/api/manage/payout")
def payout_overview(_admin: dict = Depends(require_admin), total: float = 0):
    """Auszahlungsübersicht: Berechnet den Anteil pro Künstler:in mit PayPal-Adresse."""
    eligible = []
    for artist in store.catalog()["artists"]:
        pp = (artist.get("paypal") or "").strip()
        if pp:
            eligible.append({
                "id": artist["id"],
                "name": artist["name"],
                "paypal": pp,
                "trackCount": sum(len(r["tracks"]) for r in artist["releases"]),
            })
    count = len(eligible)
    per_artist = round(total / count, 2) if count > 0 and total > 0 else 0
    remainder = round(total - per_artist * count, 2) if count > 0 else 0
    for a in eligible:
        a["amount"] = per_artist
    # Rest dem/der Ersten zuschlagen (Rundungsdifferenz)
    if eligible and remainder > 0:
        eligible[0]["amount"] = round(eligible[0]["amount"] + remainder, 2)
    return {
        "total": total,
        "eligible": eligible,
        "count": count,
        "perArtist": per_artist,
        "withoutPaypal": [a["name"] for a in store.catalog()["artists"]
                          if not (a.get("paypal") or "").strip()],
    }


@app.delete("/api/manage/artists/{artist_id}")
def remove_artist(artist_id: str, _admin: dict = Depends(require_admin)):
    if not store.find_artist(artist_id):
        raise HTTPException(status_code=404, detail="Künstler:in nicht gefunden")
    fingerprint.unregister_artist(artist_id)
    store.delete_artist(artist_id)
    accounts.delete_by_artist(artist_id)
    folder = (MEDIA_DIR / artist_id).resolve()
    if str(folder).startswith(str(MEDIA_DIR.resolve())) and folder.is_dir():
        shutil.rmtree(folder, ignore_errors=True)
    return {"ok": True}


@app.post("/api/manage/artists/{artist_id}/releases")
def create_release(
    artist_id: str,
    _admin: dict = Depends(require_admin),
    title: str = Form(...),
    type: str = Form("Single"),
    year: int = Form(...),
    genre: str = Form(""),
    cover: UploadFile | None = File(None),
):
    if not store.find_artist(artist_id):
        raise HTTPException(status_code=404, detail="Künstler:in nicht gefunden")
    release = store.add_release(artist_id, title=title, rtype=type, year=year, genre=genre)
    if cover is not None and cover.filename:
        res = _save_image(artist_id, release["id"], cover)
        store.update_release(release["id"], cover=res["image"], coverThumb=res["thumb"])
    artist, release = store.find_release(release["id"])
    return enrich_release(artist, release)


@app.put("/api/manage/releases/{release_id}")
def edit_release(
    release_id: str,
    _admin: dict = Depends(require_admin),
    title: str | None = Form(None),
    type: str | None = Form(None),
    year: int | None = Form(None),
    genre: str | None = Form(None),
    cover: UploadFile | None = File(None),
):
    artist, release = store.find_release(release_id)
    if not release:
        raise HTTPException(status_code=404, detail="Release nicht gefunden")
    fields = {"title": title, "type": type, "year": year, "genre": genre}
    if cover is not None and cover.filename:
        res = _save_image(artist["id"], release["id"], cover)
        fields["cover"] = res["image"]
        fields["coverThumb"] = res["thumb"]
    store.update_release(release_id, **fields)
    artist, release = store.find_release(release_id)
    return enrich_release(artist, release)


@app.delete("/api/manage/releases/{release_id}")
def remove_release(release_id: str, _admin: dict = Depends(require_admin)):
    artist, release = store.find_release(release_id)
    if not release:
        raise HTTPException(status_code=404, detail="Release nicht gefunden")
    # zugehörige Dateien aufräumen
    _safe_unlink(artist["id"], release.get("cover"), release.get("coverThumb"))
    for t in release["tracks"]:
        _safe_unlink(artist["id"], t.get("file"))
    store.delete_release(release_id)
    return {"ok": True}


def _store_audio(artist_id: str, audio: UploadFile,
                 allow_known: bool = False) -> tuple[str, int, dict | None]:
    """
    Speichert eine hochgeladene Audiodatei.

    Führt nach dem Speichern eine Fingerprint-Analyse durch:
      * exakt identische Datei schon hochgeladen?      -> 409 Duplikat
      * AcoustID kennt den Song (strict-Modus)?         -> 409 Bekannter Track

    `allow_known=True` umgeht den AcoustID-Block (Admin-Override).

    Rückgabe: (filename, duration, fp_dict_or_None)
    """
    ext = Path(audio.filename or "").suffix.lower()
    if ext not in AUDIO_EXTS:
        raise HTTPException(status_code=400,
                            detail="Nur MP3-Dateien sind erlaubt (.mp3).")
    data = audio.file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Leere Audiodatei")
    filename = f"{uuid.uuid4().hex}{ext}"
    dest = MEDIA_DIR / artist_id / filename
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    duration = _wav_duration(dest) if ext == ".wav" else 0

    # --- Fingerprint-Analyse ----------------------------------------------
    fp_result = fingerprint.analyse(dest)
    fp = fp_result["fingerprint"]

    # fpcalc liefert die Audiodauer kostenlos mit – für MP3s nutzen wir die.
    if fp and not duration:
        duration = int(fp.get("duration") or 0)

    # 1) Lokal bekanntes Duplikat? -> immer blockieren
    dup = fp_result["duplicate"]
    if dup:
        dest.unlink(missing_ok=True)
        same_artist = dup.get("artistId") == artist_id
        if same_artist:
            detail = ("Diese Audiodatei hast du bereits hochgeladen. "
                      "Bitte den vorhandenen Track verwenden.")
        else:
            detail = ("Diese Audiodatei wurde bereits von einer anderen "
                      "Künstler:in hochgeladen und ist auf der Plattform "
                      "registriert.")
        raise HTTPException(status_code=409, detail=detail)

    # 2) AcoustID-Match? Im strict-Modus blockieren, sonst nur loggen
    cfg = config.load()
    mode = cfg.get("fingerprint_mode", "strict")
    match = fp_result["acoustid"]
    if match and mode == "strict" and not allow_known:
        dest.unlink(missing_ok=True)
        raise HTTPException(
            status_code=409,
            detail=(
                f"Dieser Song scheint bereits öffentlich bekannt zu sein: "
                f"„{match.get('title') or '?'}" + (f"\" von {match['artist']}" if match.get("artist") else "\"") +
                f" (Ähnlichkeit {int(match.get('score', 0) * 100)} %). "
                "Bitte lade nur Werke hoch, an denen du alle Rechte hältst (siehe AGB § 4)."
            ),
        )

    return filename, duration, fp_result


@app.post("/api/manage/releases/{release_id}/tracks")
def create_track(release_id: str, _admin: dict = Depends(require_admin),
                 title: str = Form(...), genre: str = Form(""),
                 audio: UploadFile = File(...)):
    artist, release = store.find_release(release_id)
    if not release:
        raise HTTPException(status_code=404, detail="Release nicht gefunden")
    # Admin: erlaubt auch AcoustID-Matches (z. B. zum Wiederherstellen)
    filename, duration, fp_result = _store_audio(artist["id"], audio, allow_known=True)
    track = store.add_track(release_id, title=title, filename=filename,
                            duration=duration, genre=genre)
    if fp_result and fp_result.get("fingerprint"):
        fingerprint.register(fp_result["fingerprint"], track["id"], artist["id"],
                             acoustid_match=fp_result.get("acoustid"))
    return enrich_track(artist, release, track)


@app.put("/api/manage/tracks/{track_id}")
def edit_track(track_id: str, _admin: dict = Depends(require_admin),
               title: str | None = Form(None), genre: str | None = Form(None)):
    artist, release, track = store.find_track(track_id)
    if not track:
        raise HTTPException(status_code=404, detail="Track nicht gefunden")
    store.update_track(track_id, title=title, genre=genre)
    return enrich_track(artist, release, track)


@app.delete("/api/manage/tracks/{track_id}")
def remove_track(track_id: str, _admin: dict = Depends(require_admin)):
    artist, release, track = store.find_track(track_id)
    if not track:
        raise HTTPException(status_code=404, detail="Track nicht gefunden")
    _safe_unlink(artist["id"], track.get("file"))
    fingerprint.unregister_track(track_id)
    store.delete_track(track_id)
    return {"ok": True}


def _wav_duration(path: Path) -> int:
    try:
        with wave.open(str(path), "rb") as w:
            return round(w.getnframes() / float(w.getframerate()))
    except (wave.Error, OSError):
        return 0


# ---------------------------------------------------------------------------
# Auth-Endpunkte (Register, Login, Logout, Me)
# ---------------------------------------------------------------------------
@app.get("/api/auth/captcha")
def get_captcha():
    """Liefert eine frische Mathe-Challenge für die Registrierung."""
    return captcha.create_challenge()


def _antibot_guard(request: Request, website: str, captcha_id: str, captcha_answer: str) -> str:
    """Honeypot + Captcha + IP-Limit. Gibt die Client-IP zurück, falls alles ok."""
    ip = request.client.host if request.client else "unknown"
    # Honeypot: das "website"-Feld ist im UI versteckt — Menschen lassen es leer.
    if website.strip():
        raise HTTPException(status_code=400, detail="Spam erkannt.")
    if ratelimit.registration_blocked(ip):
        raise HTTPException(status_code=429,
                            detail="Zu viele Registrierungen von dieser Adresse. "
                                   "Bitte später erneut versuchen.")
    if not captcha.verify(captcha_id, captcha_answer):
        raise HTTPException(status_code=400, detail="Captcha falsch oder abgelaufen.")
    return ip


def _base_url(request: Request) -> str:
    """Öffentliche Basis-URL: Konfig-Override sonst aus der Anfrage abgeleitet."""
    override = (config.load().get("public_base_url") or "").strip()
    if override:
        return override.rstrip("/")
    return str(request.base_url).rstrip("/")


def _send_verification(request: Request, email: str, artist_name: str) -> bool:
    """Erzeugt einen Bestätigungs-Token und verschickt die Double-Opt-In-Mail."""
    token = auth.make_action_token(email, "verify", VERIFY_TTL)
    link = f"{_base_url(request)}/api/auth/verify?token={token}"
    return mail.send_verification(email, link, artist_name)


@app.post("/api/auth/register")
def register(
    request: Request,
    response: Response,
    email: str = Form(...),
    password: str = Form(...),
    artistName: str = Form(...),
    captchaId: str = Form(...),
    captchaAnswer: str = Form(...),
    website: str = Form(""),
    acceptAgb: str = Form(""),
):
    _check_rate_limit(request)
    ip = _antibot_guard(request, website, captchaId, captchaAnswer)
    # Pflicht-Zustimmung zu AGB/Rechteversicherung. Browser-Checkboxen senden "on"
    # bei gesetztem Häkchen; alles andere lehnen wir ab.
    if acceptAgb.strip().lower() not in ("on", "true", "1", "yes"):
        raise HTTPException(
            status_code=400,
            detail="Bitte bestätige die Rechteversicherung und die AGB.",
        )
    email = email.strip().lower()
    if not EMAIL_RE.match(email):
        raise HTTPException(status_code=400, detail="Ungültige E-Mail-Adresse.")
    if len(password) < 8:
        raise HTTPException(status_code=400, detail="Passwort muss mind. 8 Zeichen haben.")
    if accounts.find_user(email):
        raise HTTPException(status_code=400, detail="Diese E-Mail ist bereits registriert.")
    if not artistName.strip():
        raise HTTPException(status_code=400, detail="Künstlername ist Pflicht.")

    # Double-Opt-In nur, wenn überhaupt E-Mails versendet werden können.
    # Ohne SMTP würde sich der Account sonst dauerhaft selbst aussperren.
    require_verification = mail.can_send()

    artist = store.add_artist(name=artistName)
    user = accounts.add_user(email, auth.hash_password(password), artist["id"],
                             verified=not require_verification)
    # Akzeptanz protokollieren (für Audit / Streit).
    try:
        from datetime import datetime, timezone
        user["agbAcceptedAt"] = datetime.now(tz=timezone.utc).isoformat()
        user["agbAcceptedIp"] = ip
        accounts.save()
    except Exception:
        pass
    ratelimit.record_registration(ip)

    if require_verification:
        sent = _send_verification(request, email, artistName.strip())
        if not sent:
            # Versand fehlgeschlagen (z. B. SMTP-Fehler): Account dennoch anlegen,
            # aber sofort freischalten, damit niemand hängen bleibt.
            accounts.set_verified(email)
            _set_session(response, email)
            return {"email": email,
                    "artist": artist_full(store.find_artist(artist["id"]), include_private=True),
                    "verificationMailFailed": True}
        # Kein Session-Cookie – erst nach Bestätigung einloggbar.
        return {"pending": True, "email": email}

    # Kein SMTP: wie bisher direkt einloggen.
    _set_session(response, email)
    return {"email": email,
            "artist": artist_full(store.find_artist(artist["id"]), include_private=True)}


@app.get("/api/auth/verify")
def verify_email(token: str, response: Response):
    """Bestätigt eine E-Mail über den Link aus der Double-Opt-In-Mail."""
    email = auth.read_action_token(token, "verify")
    page = _verify_result_page  # HTML-Helfer unten
    if not email:
        return Response(content=page(ok=False,
                        msg="Der Bestätigungslink ist ungültig oder abgelaufen. "
                            "Bitte fordere in der Anmeldung einen neuen an."),
                        media_type="text/html", status_code=400)
    user = accounts.find_user(email)
    if not user:
        return Response(content=page(ok=False,
                        msg="Zu diesem Link existiert kein Konto mehr."),
                        media_type="text/html", status_code=404)
    accounts.set_verified(email)
    # Direkt einloggen – bequemer Übergang in den Editor.
    _set_session(response, email)
    return Response(content=page(ok=True,
                    msg="Deine E-Mail wurde bestätigt. Dein Profil ist jetzt aktiv."),
                    media_type="text/html")


def _verify_result_page(ok: bool, msg: str) -> str:
    icon = "✅" if ok else "⚠️"
    color = "#6cd28a" if ok else "#ff6b6f"
    cta = ('<a href="/artist.html" style="display:inline-block;margin-top:22px;'
           'background:#e4252b;color:#fff;padding:12px 24px;border-radius:999px;'
           'font-weight:700;text-decoration:none">Zum Künstlerbereich →</a>') if ok else \
          ('<a href="/artist.html" style="display:inline-block;margin-top:22px;'
           'background:#2a2a30;color:#fff;padding:12px 24px;border-radius:999px;'
           'font-weight:700;text-decoration:none">Zur Anmeldung</a>')
    return f"""<!DOCTYPE html><html lang="de"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Riot Music — E-Mail-Bestätigung</title></head>
<body style="background:#0e0e10;color:#f4f4f5;font-family:system-ui,sans-serif;
display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0">
<div style="text-align:center;max-width:440px;padding:32px">
<div style="font-size:3rem">{icon}</div>
<h1 style="font-size:1.5rem;color:{color}">E-Mail-Bestätigung</h1>
<p style="color:#a1a1aa;line-height:1.6">{msg}</p>
{cta}
</div></body></html>"""


@app.post("/api/auth/resend-verification")
def resend_verification(request: Request, email: str = Form(...)):
    """Verschickt die Bestätigungsmail erneut (rate-limitiert)."""
    _check_rate_limit(request)
    ip = request.client.host if request.client else "unknown"
    if ratelimit.registration_blocked(ip):
        raise HTTPException(status_code=429,
                            detail="Zu viele Anfragen. Bitte später erneut versuchen.")
    email = email.strip().lower()
    user = accounts.find_user(email)
    # Aus Datenschutzgründen immer dieselbe Antwort – verrät nicht, ob die
    # Adresse existiert.
    if user and not accounts.is_verified(user):
        artist = store.find_artist(user.get("artistId", ""))
        _send_verification(request, email, artist["name"] if artist else "")
        ratelimit.record_registration(ip)
    return {"ok": True}


@app.post("/api/auth/admin-register")
def admin_register(
    request: Request,
    response: Response,
    email: str = Form(...),
    password: str = Form(...),
    captchaId: str = Form(...),
    captchaAnswer: str = Form(...),
    website: str = Form(""),
):
    """Bootstrap: Erster Admin-Account. Nur möglich, wenn noch kein Admin existiert."""
    _check_rate_limit(request)
    if accounts.has_admin():
        raise HTTPException(status_code=403, detail="Admin existiert bereits.")
    ip = _antibot_guard(request, website, captchaId, captchaAnswer)
    email = email.strip().lower()
    if not EMAIL_RE.match(email):
        raise HTTPException(status_code=400, detail="Ungültige E-Mail-Adresse.")
    if len(password) < 8:
        raise HTTPException(status_code=400, detail="Passwort muss mind. 8 Zeichen haben.")
    if accounts.find_user(email):
        raise HTTPException(status_code=400, detail="Diese E-Mail ist bereits registriert.")
    accounts.add_user(email, auth.hash_password(password), artist_id="", role="admin")
    ratelimit.record_registration(ip)
    _set_session(response, email)
    return {"email": email, "role": "admin"}


@app.post("/api/auth/login")
def login(request: Request, response: Response,
          email: str = Form(...), password: str = Form(...)):
    ip = request.client.host if request.client else "unknown"
    _check_rate_limit(request)
    user = accounts.find_user(email)
    if not user or not auth.verify_password(password, user["password"]):
        locked = ratelimit.record_failure(ip)
        detail = "E-Mail oder Passwort falsch."
        if locked:
            detail += f" Zu viele Versuche — {ratelimit.LOCKOUT_SECONDS // 60} Minuten gesperrt."
        raise HTTPException(status_code=401, detail=detail)
    # Erst nach E-Mail-Bestätigung einloggbar.
    if not accounts.is_verified(user):
        ratelimit.record_success(ip)   # kein Brute-Force – Passwort war korrekt
        raise HTTPException(
            status_code=403,
            detail="Bitte bestätige zuerst deine E-Mail-Adresse. "
                   "Schau in dein Postfach (auch im Spam-Ordner).",
        )
    ratelimit.record_success(ip)
    _set_session(response, user["email"])
    result = {"email": user["email"], "role": user.get("role", "artist")}
    if user.get("artistId"):
        result["artist"] = artist_full(store.find_artist(user["artistId"]), include_private=True)
    return result


@app.post("/api/auth/logout")
def logout(response: Response):
    response.delete_cookie(auth.COOKIE_NAME, path="/")
    return {"ok": True}


@app.get("/api/auth/me")
def whoami(user: dict | None = Depends(current_user)):
    if not user:
        return {"authenticated": False}
    artist = store.find_artist(user.get("artistId", "")) if user.get("artistId") else None
    return {"authenticated": True, "email": user["email"],
            "role": user.get("role", "artist"),
            "artist": artist_full(artist, include_private=True) if artist else None}


@app.get("/api/auth/admin-exists")
def admin_exists():
    """Öffentliche Info: Gibt es bereits einen Admin? Steuert die Bootstrap-UI."""
    return {"exists": accounts.has_admin()}


# ---------------------------------------------------------------------------
# Kontaktformular (öffentlich, mit Anti-Bot)
# ---------------------------------------------------------------------------
@app.post("/api/report")
def submit_report(
    request: Request,
    artistId: str = Form(...),
    reason: str = Form(...),
    details: str = Form(""),
    website: str = Form(""),     # Honeypot
):
    """
    Meldung eines Künstlerprofils wegen problematischer Inhalte
    (Notice-and-Action). Landet im Admin-Posteingang.
    """
    ip = request.client.host if request.client else "unknown"
    _check_rate_limit(request)
    if website.strip():
        raise HTTPException(status_code=400, detail="Spam erkannt.")
    if ratelimit.contact_blocked(ip):
        raise HTTPException(status_code=429,
                            detail="Zu viele Meldungen von dieser Adresse. "
                                   "Bitte später erneut versuchen.")
    artist = store.find_artist((artistId or "").strip())
    if not artist:
        raise HTTPException(status_code=404, detail="Künstler:in nicht gefunden")
    try:
        contact.add_report(reported_artist_id=artist["id"],
                           reported_artist_name=artist["name"],
                           reason=reason, details=details, ip=ip)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    ratelimit.record_contact(ip)
    return {"ok": True}


@app.post("/api/contact")
def submit_contact_message(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    subject: str = Form(...),
    body: str = Form(...),
    captchaId: str = Form(...),
    captchaAnswer: str = Form(...),
    website: str = Form(""),     # Honeypot (für Bots, von Menschen unsichtbar)
):
    """
    Speichert eine Kontaktnachricht – mehrfach geschützt gegen Bots:
    Honeypot, Mathe-Captcha, IP-Rate-Limit, Längen-/Format-Prüfung
    und leichte Heuristik gegen Linkspam.
    """
    ip = request.client.host if request.client else "unknown"

    # Sperre bei zu vielen fehlgeschlagenen Logins (allgemeines IP-Lock)
    _check_rate_limit(request)

    # 1) Honeypot
    if website.strip():
        raise HTTPException(status_code=400, detail="Spam erkannt.")

    # 2) Spezifisches Kontakt-Rate-Limit pro IP (max. 5/h)
    if ratelimit.contact_blocked(ip):
        raise HTTPException(
            status_code=429,
            detail="Zu viele Kontaktanfragen von dieser Adresse. "
                   "Bitte später erneut versuchen.",
        )

    # 3) Captcha (single-use)
    if not captcha.verify(captchaId, captchaAnswer):
        raise HTTPException(status_code=400, detail="Captcha falsch oder abgelaufen.")

    # 4) E-Mail-Format
    email_clean = email.strip().lower()
    if not EMAIL_RE.match(email_clean):
        raise HTTPException(status_code=400, detail="Ungültige E-Mail-Adresse.")

    # 5) Heuristische Spam-Erkennung
    if contact.looks_like_spam(name, subject, body):
        # Bewusst die gleiche generische Fehlermeldung — wir verraten nicht,
        # warum wir blockiert haben.
        ratelimit.record_contact(ip)
        raise HTTPException(status_code=400, detail="Nachricht wurde abgelehnt.")

    # 6) Speichern (validiert Länge & Pflichtfelder)
    try:
        msg = contact.add_message(name=name, email=email_clean,
                                  subject=subject, body=body, ip=ip)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    ratelimit.record_contact(ip)

    # 7) Optionaler Mailversand an Admin – Fehler ignorieren wir bewusst:
    # Die Nachricht ist sicher gespeichert und im Posteingang abrufbar.
    mail.send_contact_notification(name=name, sender_email=email_clean,
                                   subject=subject, body=body, ip=ip)

    return {"ok": True, "id": msg["id"]}


@app.get("/api/admin/config")
def admin_get_config(_admin: dict = Depends(require_admin)):
    """Liefert die aktuelle E-Mail-/SMTP-Konfiguration (Passwort maskiert)."""
    return config.safe_view()


@app.put("/api/admin/config")
async def admin_update_config(request: Request,
                              _admin: dict = Depends(require_admin)):
    """Speichert E-Mail-/SMTP-Konfiguration. Passwortmaske bleibt unverändert."""
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Ungültiges JSON.")
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Erwartet ein Objekt.")
    email = (payload.get("admin_email") or "").strip()
    if email and not EMAIL_RE.match(email):
        raise HTTPException(status_code=400, detail="Ungültige Admin-E-Mail.")
    return config.save(payload)


@app.get("/api/fingerprint/status")
def public_fingerprint_status():
    """
    Schlanker, öffentlicher Status (für die Upload-UI). Verrät nichts Sensibles:
    nur ob die Pipeline grundsätzlich aktiv ist.
    """
    cfg = config.load()
    return {
        "fpcalc_available": fingerprint.fpcalc_available(),
        "acoustid_configured": fingerprint.acoustid_configured(),
        "mode": cfg.get("fingerprint_mode", "strict"),
    }


@app.post("/api/admin/tracks/backfill-durations")
def admin_backfill_durations(_admin: dict = Depends(require_admin)):
    """
    Liest alle Tracks mit Dauer 0 per fpcalc neu ein und trägt die Dauer nach.
    Nützlich nach dem Aktivieren des Fingerprintings für Alt-Bestand.
    """
    if not fingerprint.fpcalc_available():
        raise HTTPException(status_code=400,
                            detail="fpcalc nicht installiert – kein Backfill möglich.")
    updated = 0
    skipped = 0
    failed = 0
    for artist in store.catalog()["artists"]:
        for rel in artist["releases"]:
            for track in rel["tracks"]:
                if track.get("duration"):
                    skipped += 1
                    continue
                fname = track.get("file")
                if not fname:
                    failed += 1
                    continue
                path = MEDIA_DIR / artist["id"] / fname
                if not path.is_file():
                    failed += 1
                    continue
                fp = fingerprint.compute(path)
                if fp and fp.get("duration"):
                    track["duration"] = int(fp["duration"])
                    updated += 1
                else:
                    failed += 1
    if updated:
        store.save()
    return {"updated": updated, "skipped": skipped, "failed": failed}


@app.get("/api/admin/fingerprint/status")
def admin_fingerprint_status(_admin: dict = Depends(require_admin)):
    """Status der Fingerprint-Pipeline: fpcalc verfügbar? AcoustID konfiguriert?"""
    cfg = config.load()
    return {
        "fpcalc_available": fingerprint.fpcalc_available(),
        "fpcalc_path": fingerprint._fpcalc_path() or "",
        "acoustid_configured": fingerprint.acoustid_configured(),
        "mode": cfg.get("fingerprint_mode", "strict"),
        "stored_count": fingerprint.count(),
    }


@app.get("/api/admin/overview")
def admin_overview(_admin: dict = Depends(require_admin)):
    """
    Nutzungs-Übersicht für das Admin-Dashboard:
      * Plays gesamt und pro Künstler:in
      * Spenden-Button-Klicks (Plattform + pro Künstler:in)
    Hinweis: Klicks sind nur Interesse-Signale, keine echten Spenden/Beträge.
    """
    artists_out = []
    total_plays = 0
    total_tracks = 0
    total_releases = 0
    for artist in store.catalog()["artists"]:
        a_plays = 0
        a_tracks = 0
        for release in artist["releases"]:
            total_releases += 1
            for track in release["tracks"]:
                a_tracks += 1
                a_plays += plays.get_count(track["id"])
        total_plays += a_plays
        total_tracks += a_tracks
        artists_out.append({
            "id": artist["id"],
            "name": artist["name"],
            "plays": a_plays,
            "tracks": a_tracks,
            "donateClicks": stats.artist_count(artist["id"]),
            "hasDonate": bool(_donate_url(artist.get("paypal"), artist["name"])),
            "public": _artist_public(artist["id"]),
        })
    artists_out.sort(key=lambda a: a["plays"], reverse=True)

    return {
        "totals": {
            "artists": len(artists_out),
            "releases": total_releases,
            "tracks": total_tracks,
            "plays": total_plays,
        },
        "donations": {
            "platformClicks": stats.platform_count(),
            "artistClicks": stats.total_artist_clicks(),
        },
        "artists": artists_out,
    }


@app.get("/api/admin/unverified")
def admin_list_unverified(_admin: dict = Depends(require_admin)):
    """Listet unbestätigte (Double-Opt-In offen) Künstler-Accounts."""
    import time as _t
    now = _t.time()
    out = []
    for u in accounts.list_unverified():
        artist = store.find_artist(u.get("artistId", ""))
        out.append({
            "email": u["email"],
            "artistId": u.get("artistId", ""),
            "artistName": artist["name"] if artist else "(Profil fehlt)",
            "createdAt": u.get("createdAt", 0),
            "ageHours": round((now - u.get("createdAt", now)) / 3600, 1),
        })
    out.sort(key=lambda x: x["createdAt"])
    return {"unverified": out, "count": len(out),
            "mailEnabled": mail.can_send()}


@app.post("/api/admin/unverified/{email}/verify")
def admin_verify_user(email: str, _admin: dict = Depends(require_admin)):
    """Schaltet ein Konto manuell frei (z. B. wenn die Mail nicht ankam)."""
    if not accounts.set_verified(email):
        raise HTTPException(status_code=404, detail="Konto nicht gefunden")
    return {"ok": True}


@app.delete("/api/admin/unverified/{email}")
def admin_delete_unverified(email: str, _admin: dict = Depends(require_admin)):
    """Löscht ein einzelnes unbestätigtes Konto samt Profil."""
    user = accounts.find_user(email)
    if not user or accounts.is_verified(user):
        raise HTTPException(status_code=404, detail="Kein unbestätigtes Konto.")
    artist_id = user.get("artistId")
    if artist_id:
        fingerprint.unregister_artist(artist_id)
        store.delete_artist(artist_id)
        folder = (MEDIA_DIR / artist_id).resolve()
        if str(folder).startswith(str(MEDIA_DIR.resolve())) and folder.is_dir():
            shutil.rmtree(folder, ignore_errors=True)
    accounts.delete_by_artist(artist_id) if artist_id else None
    return {"ok": True}


@app.post("/api/admin/prune-unverified")
def admin_prune_unverified(_admin: dict = Depends(require_admin)):
    """Räumt alle unbestätigten Konten auf, die älter als 7 Tage sind."""
    artist_ids = accounts.prune_unverified(UNVERIFIED_MAX_AGE)
    for artist_id in artist_ids:
        fingerprint.unregister_artist(artist_id)
        store.delete_artist(artist_id)
        folder = (MEDIA_DIR / artist_id).resolve()
        if str(folder).startswith(str(MEDIA_DIR.resolve())) and folder.is_dir():
            shutil.rmtree(folder, ignore_errors=True)
    return {"ok": True, "removed": len(artist_ids)}


@app.post("/api/admin/config/test-mail")
def admin_test_mail(_admin: dict = Depends(require_admin)):
    """Sendet eine Test-Mail an die hinterlegte Admin-Adresse."""
    if not config.smtp_configured():
        raise HTTPException(
            status_code=400,
            detail="SMTP nicht vollständig konfiguriert (admin_email & smtp_host nötig).",
        )
    ok = mail.send_contact_notification(
        name="Riot-Music-Testlauf",
        sender_email=config.admin_email(),
        subject="Test-Mail",
        body="Diese Test-Mail bestätigt, dass dein SMTP-Setup funktioniert.",
        ip="127.0.0.1",
    )
    if not ok:
        raise HTTPException(
            status_code=502,
            detail="Versand fehlgeschlagen. Bitte SMTP-Daten und Server-Logs prüfen.",
        )
    return {"ok": True}


@app.get("/api/admin/contact-messages")
def list_contact_messages(_admin: dict = Depends(require_admin)):
    """Admin: alle Kontaktnachrichten (neueste zuerst)."""
    return {"messages": contact.list_messages(),
            "unread": contact.count_unread()}


@app.post("/api/admin/contact-messages/{msg_id}/read")
def mark_contact_read(msg_id: str, read: bool = True,
                      _admin: dict = Depends(require_admin)):
    """Admin: Nachricht als gelesen/ungelesen markieren."""
    if not contact.mark_read(msg_id, read):
        raise HTTPException(status_code=404, detail="Nachricht nicht gefunden")
    return {"ok": True}


@app.delete("/api/admin/contact-messages/{msg_id}")
def delete_contact_message(msg_id: str, _admin: dict = Depends(require_admin)):
    """Admin: Nachricht endgültig löschen."""
    if not contact.delete_message(msg_id):
        raise HTTPException(status_code=404, detail="Nachricht nicht gefunden")
    return {"ok": True}


# ---------------------------------------------------------------------------
# Play-Counting
# ---------------------------------------------------------------------------
@app.post("/api/plays/{track_id}")
def record_play(track_id: str):
    """Zählt einen Play für einen Track (nach 30 Sekunden Wiedergabe)."""
    artist, release, track = store.find_track(track_id)
    if not track:
        raise HTTPException(status_code=404, detail="Track nicht gefunden")
    plays.record_play(track_id)
    return {"ok": True, "playCount": plays.get_count(track_id)}


@app.post("/api/stats/donate-click")
def record_donate_click(artistId: str = Form("")):
    """
    Zählt einen Klick auf einen Spenden-Button. Ohne artistId = Plattform-Button.
    Erfasst nur das Klick-Interesse, NICHT die tatsächliche Spende/den Betrag.
    """
    artist_id = (artistId or "").strip()
    if artist_id:
        if not store.find_artist(artist_id):
            raise HTTPException(status_code=404, detail="Künstler:in nicht gefunden")
        stats.record_artist_click(artist_id)
    else:
        stats.record_platform_click()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Künstler-Export (Admin-only)
# ---------------------------------------------------------------------------
@app.get("/api/artists/export/emails.csv")
def export_artist_emails(user: dict | None = Depends(current_user)):
    """Exportiert alle E-Mails der Künstler als CSV (Admin-only)."""
    if not user or not accounts.is_admin(user):
        raise HTTPException(status_code=403, detail="Nur Admins können E-Mails exportieren")

    # Sammle alle E-Mails von Künstlern (mit artistId, keine Admins)
    emails = []
    for u in accounts.data()["users"]:
        if u.get("artistId"):  # Nur Künstler, nicht Admins
            artist = store.find_artist(u["artistId"])
            if artist:
                emails.append({
                    "email": u["email"],
                    "name": artist.get("name", ""),
                })

    # Generiere CSV
    import io
    output = io.StringIO()
    output.write("E-Mail,Künstler:in\n")
    for entry in emails:
        # CSV-safe: Quotes wenn Komma/Quote vorhanden
        email = entry["email"]
        name = entry["name"].replace('"', '""')  # Escape quotes
        if "," in name or '"' in name:
            name = f'"{name}"'
        output.write(f"{email},{name}\n")

    csv_content = output.getvalue()
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=artist-emails.csv"}
    )


@app.get("/api/artists/export/emails.json")
def export_artist_emails_json(user: dict | None = Depends(current_user)):
    """Exportiert alle E-Mails der Künstler als JSON (Admin-only)."""
    if not user or not accounts.is_admin(user):
        raise HTTPException(status_code=403, detail="Nur Admins können E-Mails exportieren")

    # Sammle alle E-Mails
    emails = []
    for u in accounts.data()["users"]:
        if u.get("artistId"):  # Nur Künstler
            artist = store.find_artist(u["artistId"])
            if artist:
                emails.append({
                    "email": u["email"],
                    "name": artist.get("name", ""),
                    "location": artist.get("location", ""),
                })

    return {
        "count": len(emails),
        "exported_at": str(__import__("datetime").datetime.now(tz=__import__("datetime").timezone.utc).isoformat()),
        "emails": emails,
    }


# ---------------------------------------------------------------------------
# Künstler-Selfservice ("Künstlerbereich") – nur das eigene Profil, mit Login
# ---------------------------------------------------------------------------
def _own_release(artist: dict, release_id: str) -> dict:
    a, r = store.find_release(release_id)
    if not r or a["id"] != artist["id"]:
        raise HTTPException(status_code=404, detail="Release nicht gefunden.")
    return r


def _own_track(artist: dict, track_id: str):
    a, rel, t = store.find_track(track_id)
    if not t or a["id"] != artist["id"]:
        raise HTTPException(status_code=404, detail="Track nicht gefunden.")
    return rel, t


@app.put("/api/studio/artist")
def studio_update_artist(
    artist: dict = Depends(require_artist),
    name: str | None = Form(None),
    location: str | None = Form(None),
    bio: str | None = Form(None),
    paypal: str | None = Form(None),
    videoUrlsJson: str | None = Form(None),
    socialJson: str | None = Form(None),
    image: UploadFile | None = File(None),
    banner: UploadFile | None = File(None),
):
    import json
    fields = {"name": name, "location": location, "bio": bio, "paypal": paypal}
    if videoUrlsJson is not None and videoUrlsJson.strip():
        try:
            urls = json.loads(videoUrlsJson) if videoUrlsJson.strip() else []
            if not isinstance(urls, list):
                raise TypeError
            normalized = []
            for url in urls:
                if url and url.strip():
                    norm = video.normalize_and_validate(url)
                    if norm:
                        normalized.append(norm)
            fields["videoUrls"] = normalized
        except (json.JSONDecodeError, TypeError, video.InvalidVideoURLError) as exc:
            raise HTTPException(status_code=400, detail=f"Ungültige Video-URLs: {exc}")
    if socialJson is not None and socialJson.strip():
        try:
            raw = json.loads(socialJson)
            fields["social"] = social.normalize_links(raw)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Ungültige Social-Links (JSON).")
        except social.InvalidSocialURLError as exc:
            raise HTTPException(status_code=400, detail=f"Ungültiger Link: {exc}")
    if image is not None and image.filename:
        res = _save_image(artist["id"], "artist", image)
        fields["image"] = res["image"]
        fields["imageThumb"] = res["thumb"]
    if banner is not None and banner.filename:
        fields["banner"] = _save_banner(artist["id"], banner)
    store.update_artist(artist["id"], **fields)
    return artist_full(store.find_artist(artist["id"]), include_private=True)


@app.delete("/api/studio/artist")
def studio_delete_artist(
    artist: dict = Depends(require_artist),
    user: dict | None = Depends(current_user),
    password: str = Form(...),
):
    """Löscht das Künstler-Profil nach Passwort-Verifizierung."""
    if not user:
        raise HTTPException(status_code=401, detail="Nicht authentifiziert")

    # Passwort verifizieren
    if not auth.verify_password(password, user["password"]):
        raise HTTPException(status_code=401, detail="Passwort falsch")

    # Fingerprints des Künstlers entfernen
    fingerprint.unregister_artist(artist["id"])

    # Künstler aus Katalog löschen
    store.delete_artist(artist["id"])

    # User-Account löschen
    accounts.delete_by_artist(artist["id"])

    # Mediendateien löschen
    folder = (MEDIA_DIR / artist["id"]).resolve()
    if str(folder).startswith(str(MEDIA_DIR.resolve())) and folder.is_dir():
        shutil.rmtree(folder, ignore_errors=True)

    return {"ok": True}


@app.post("/api/studio/releases")
def studio_create_release(
    artist: dict = Depends(require_artist),
    title: str = Form(...),
    type: str = Form("Single"),
    year: int = Form(...),
    genre: str = Form(""),
    cover: UploadFile | None = File(None),
):
    release = store.add_release(artist["id"], title=title, rtype=type, year=year, genre=genre)
    if cover is not None and cover.filename:
        res = _save_image(artist["id"], release["id"], cover)
        store.update_release(release["id"], cover=res["image"], coverThumb=res["thumb"])
    _, release = store.find_release(release["id"])
    return enrich_release(artist, release)


@app.put("/api/studio/releases/{release_id}")
def studio_update_release(
    release_id: str,
    artist: dict = Depends(require_artist),
    title: str | None = Form(None),
    type: str | None = Form(None),
    year: int | None = Form(None),
    genre: str | None = Form(None),
    cover: UploadFile | None = File(None),
):
    _own_release(artist, release_id)
    fields = {"title": title, "type": type, "year": year, "genre": genre}
    if cover is not None and cover.filename:
        res = _save_image(artist["id"], release_id, cover)
        fields["cover"] = res["image"]
        fields["coverThumb"] = res["thumb"]
    store.update_release(release_id, **fields)
    _, release = store.find_release(release_id)
    return enrich_release(artist, release)


@app.delete("/api/studio/releases/{release_id}")
def studio_delete_release(release_id: str, artist: dict = Depends(require_artist)):
    release = _own_release(artist, release_id)
    _safe_unlink(artist["id"], release.get("cover"), release.get("coverThumb"))
    for t in release["tracks"]:
        _safe_unlink(artist["id"], t.get("file"))
        fingerprint.unregister_track(t["id"])
    store.delete_release(release_id)
    return {"ok": True}


def _fingerprint_summary(fp_result: dict | None) -> dict:
    """Erzeugt eine UI-taugliche Zusammenfassung der Fingerprint-Analyse."""
    if not fp_result or not fp_result.get("fingerprint"):
        if not fingerprint.fpcalc_available():
            return {"checked": False,
                    "note": "fpcalc nicht installiert — Fingerprinting deaktiviert."}
        return {"checked": False, "note": "Audio konnte nicht analysiert werden."}
    fp = fp_result["fingerprint"]
    parts = [f"Fingerprint berechnet (Dauer {fp['duration']}s, Hash {fp['hash'][:10]}…)"]
    if fingerprint.acoustid_configured():
        if fp_result.get("acoustid"):
            m = fp_result["acoustid"]
            parts.append(f"AcoustID-Match: „{m.get('title','?')}" +
                         (f" von {m['artist']}" if m.get("artist") else "") +
                         f" ({int(m.get('score',0)*100)}%)")
        else:
            parts.append("AcoustID: kein Treffer (Song ist neu)")
    else:
        parts.append("AcoustID: nicht konfiguriert (nur lokale Duplikat-Erkennung)")
    return {"checked": True, "note": " · ".join(parts), "data": fp_result}


@app.post("/api/studio/releases/{release_id}/tracks")
def studio_add_track(release_id: str, artist: dict = Depends(require_artist),
                     title: str = Form(...), genre: str = Form(""), audio: UploadFile = File(...)):
    _own_release(artist, release_id)
    filename, duration, fp_result = _store_audio(artist["id"], audio)
    track = store.add_track(release_id, title=title, filename=filename,
                            duration=duration, genre=genre)
    if fp_result and fp_result.get("fingerprint"):
        fingerprint.register(fp_result["fingerprint"], track["id"], artist["id"],
                             acoustid_match=fp_result.get("acoustid"))
    _, release = store.find_release(release_id)
    result = enrich_track(artist, release, track)
    result["fingerprint"] = _fingerprint_summary(fp_result)
    return result


@app.post("/api/studio/single")
def studio_upload_single(
    artist: dict = Depends(require_artist),
    title: str = Form(...),
    year: int = Form(...),
    genre: str = Form(""),
    audio: UploadFile = File(...),
    cover: UploadFile | None = File(None),
):
    """Komfort: lädt einen einzelnen Song als eigenständige Single hoch."""
    filename, duration, fp_result = _store_audio(artist["id"], audio)
    release = store.add_release(artist["id"], title=title, rtype="Single", year=year, genre=genre)
    if cover is not None and cover.filename:
        res = _save_image(artist["id"], release["id"], cover)
        store.update_release(release["id"], cover=res["image"], coverThumb=res["thumb"])
    track = store.add_track(release["id"], title=title, filename=filename, duration=duration)
    if fp_result and fp_result.get("fingerprint"):
        fingerprint.register(fp_result["fingerprint"], track["id"], artist["id"],
                             acoustid_match=fp_result.get("acoustid"))
    _, release = store.find_release(release["id"])
    result = enrich_release(artist, release)
    result["fingerprint"] = _fingerprint_summary(fp_result)
    return result


@app.put("/api/studio/tracks/{track_id}")
def studio_update_track(track_id: str, artist: dict = Depends(require_artist),
                        title: str | None = Form(None), genre: str | None = Form(None)):
    rel, _ = _own_track(artist, track_id)
    store.update_track(track_id, title=title, genre=genre)
    _, _, track = store.find_track(track_id)
    return enrich_track(artist, rel, track)


@app.delete("/api/studio/tracks/{track_id}")
def studio_delete_track(track_id: str, artist: dict = Depends(require_artist)):
    _, track = _own_track(artist, track_id)
    _safe_unlink(artist["id"], track.get("file"))
    fingerprint.unregister_track(track_id)
    store.delete_track(track_id)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Medien-Streaming (Audio mit Range + Bilder)
# ---------------------------------------------------------------------------
@app.get("/media/{artist_id}/{filename}")
def stream_media(artist_id: str, filename: str, request: Request):
    if "/" in artist_id or ".." in artist_id or "/" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Ungültiger Pfad")
    file_path = (MEDIA_DIR / artist_id / filename).resolve()
    if not str(file_path).startswith(str(MEDIA_DIR.resolve())) or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Datei nicht gefunden")

    file_size = file_path.stat().st_size
    media_type = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
    range_header = request.headers.get("range")

    if range_header is None:
        return FileResponse(file_path, media_type=media_type, headers={"Accept-Ranges": "bytes"})

    try:
        units, rng = range_header.split("=")
        assert units.strip() == "bytes"
        start_s, end_s = rng.split("-")
        start = int(start_s) if start_s else 0
        end = int(end_s) if end_s else file_size - 1
    except (ValueError, AssertionError):
        raise HTTPException(status_code=400, detail="Ungültiger Range-Header")

    start = max(0, start)
    end = min(end, file_size - 1)
    if start > end:
        return Response(status_code=416, headers={"Content-Range": f"bytes */{file_size}"})

    length = end - start + 1

    def iter_file():
        with open(file_path, "rb") as f:
            f.seek(start)
            remaining = length
            while remaining > 0:
                chunk = f.read(min(CHUNK_SIZE, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk

    headers = {
        "Content-Range": f"bytes {start}-{end}/{file_size}",
        "Accept-Ranges": "bytes",
        "Content-Length": str(length),
    }
    return StreamingResponse(iter_file(), status_code=206, media_type=media_type, headers=headers)


# ---------------------------------------------------------------------------
# Frontend (SPA + Studio) – statisch ausliefern
# ---------------------------------------------------------------------------
if FRONTEND_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
else:
    @app.get("/")
    def no_frontend():
        return JSONResponse({"detail": "Frontend-Verzeichnis fehlt."}, status_code=500)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
