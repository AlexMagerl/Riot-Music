# Riot Music 🎸✊

> Musik gehört den Menschen, die sie machen — nicht den Konzernen.

Prototyp einer genossenschaftlichen, werbefreien Musikplattform mit drei Zugängen:
das **Hörer-Frontend** (Webplayer, Katalog, Suche, Profile), der **Künstlerbereich**
(Login, jede:r editiert das eigene Profil) und der **Admin-Zugang** (verwaltet alles).

## Features

### Hörer-Frontend (`/`)
- **Persistenter Webplayer** — läuft beim Durchklicken durch (Single-Page-App),
  Play/Pause, Vor/Zurück, Seeking, Lautstärke, automatische Warteschlange.
- **Loop-Funktion** im Player: aus → 🔁 alle (Warteschlange) → 🔂 ein Titel.
- **Radio-Modus** (Button auf der Startseite): endlose Zufallswiedergabe von Songs
  der ganzen Plattform; füllt sich automatisch nach.
- **Audio in allen Browser-Formaten** — natives HTML5-`<audio>`. Das Backend
  streamt mit HTTP-Range-Requests (Seeking funktioniert).
- **Künstlerkatalog nach Genre** — Kachelübersicht, Filter über die Sidebar.
  Genres sind **frei erfunden** (siehe unten) und werden dynamisch aus den Daten
  abgeleitet — keine feste Liste.
- **Suche mit Filter** — Volltextsuche über Künstler:innen, Releases und Songs
  (matcht auch Genre-Namen), optional auf ein Genre eingeschränkt.
- **Künstlerprofil** — Bio, Bild, Releases (Album/EP/Single) mit Tracklisten;
  Genres werden pro Release/Song angezeigt.

### Künstlerbereich (`/artist.html`) — mit Login
- **Registrierung & Login** mit E-Mail + Passwort (PBKDF2-Hashing, signiertes
  HttpOnly-Session-Cookie). Bei der Registrierung wird automatisch ein
  Künstlerprofil angelegt.
- **Editierbare eigene Profilseite** im Look der öffentlichen Künstlerseite:
  Name, Genre, Ort, Bio, Künstlerbild.
- **Einzelnen Song hochladen** (wird als Single veröffentlicht) **oder ganze
  Bündel** (Album/EP/Single) erstellen und Songs hinzufügen.
- **Genres selbst erfinden**: jedes Release hat ein frei wählbares Genre, jeder
  Song kann es per Override eigenständig setzen — keine vorgegebene Liste. Bricht
  bewusst mit den alten Genre-Konventionen.
- **Zugriffsschutz**: man kann ausschließlich das *eigene* Profil bearbeiten.

### Admin-Zugang (`/admin.html`)
- Verwaltet **alle** Künstler:innen, Releases und Songs (für Moderation /
  Vorgehen gegen Verstöße). Anlegen/Bearbeiten/Löschen inkl. Bild-Uploads.
- ⚠️ **Noch ohne eigenes Passwort** — siehe „Nächste Schritte".

### Gemeinsame Bausteine
- **Algorithmisches Bild-Rescaling** (Pillow): EXIF-Ausrichtung korrigiert,
  zentriert quadratisch zugeschnitten, als JPEG in zwei Größen gerendert
  (640×640 voll + 160×160 Thumbnail).
- Änderungen werden direkt nach `catalog.json` persistiert (atomar, threadsicher);
  Accounts liegen in `data/users.json`.

### Demo-Daten
- Aushängeschild ist **Johnny Guitar** (Blues Rock) plus vier weitere Acts. Die
  Audiodateien werden prozedural erzeugt (Karplus-Strong-Synthese), also
  lizenzfrei und ohne externe Downloads.

## Tech-Stack

- **Backend:** Python 3.12 + FastAPI + uvicorn + Pillow (Bildverarbeitung).
  Auth (PBKDF2 + signierte Token) ist mit der Standardbibliothek umgesetzt.
- **Frontend:** Vanilla JS, kein Build-Step (Hörer-SPA + Formular-UIs).
- **Daten:** `backend/data/catalog.json` + `backend/data/users.json` (zur Laufzeit editierbar)

## Projektstruktur

```
RiotMusic/
├─ backend/
│  ├─ main.py            # FastAPI: öffentliche API, Auth, Studio- & Admin-API, Streaming
│  ├─ store.py           # Katalog-Persistenz + CRUD (threadsicher)
│  ├─ accounts.py        # Benutzerkonten (users.json)
│  ├─ auth.py            # Passwort-Hashing (PBKDF2) + signierte Session-Token
│  ├─ images.py          # Bild-Rescaling (Pillow): quadratisch, 640 + 160
│  ├─ generate_media.py  # erzeugt die WAV-Demotracks aus dem Katalog
│  ├─ data/              # catalog.json, users.json (gitignored), secret.key (gitignored)
│  └─ media/             # Audio + Bilder (pro Künstler:in ein Ordner)
├─ frontend/
│  ├─ index.html         # Hörer-SPA
│  ├─ artist.html        # Künstlerbereich (Login + Self-Service)
│  ├─ admin.html         # Admin-Verwaltung
│  ├─ css/{styles,studio}.css
│  └─ js/{app,artist,admin}.js
└─ requirements.txt
```

## Starten

```powershell
# 1. Abhängigkeiten installieren
python -m pip install -r requirements.txt

# 2. Demo-Audio erzeugen (einmalig; überspringt bereits vorhandene Dateien)
python backend/generate_media.py

# 3. Server starten — eine der beiden Varianten:
python -m uvicorn main:app --app-dir backend --reload --port 8000
#   ... oder direkt über main.py (aus dem Ordner backend/):
#   cd backend; python main.py
```

> Hinweis: `main.py` importiert die Geschwistermodule `store` und `images`, daher
> beim uvicorn-Start `--app-dir backend` setzen (legt `backend/` auf den Importpfad).

Dann im Browser öffnen: <http://127.0.0.1:8000>
(Künstlerbereich: `/artist.html` · Admin: `/admin.html`)

## API-Überblick

| Endpoint | Zweck |
|---|---|
| `GET /api/platform` | Name, Tagline, Manifest |
| `GET /api/genres` | Dynamisch: alle tatsächlich verwendeten Genres |
| `GET /api/artists?genre=` | Künstlerkatalog (Filter: hat ein Release/Song dieses Genre) |
| `GET /api/artists/{id}` | Künstlerprofil inkl. abgeleiteter `genres`-Liste, Releases & Track-URLs |
| `GET /api/radio?limit=` | Zufällig gemischte Songs der ganzen Plattform (Radio-Modus) |
| `GET /api/tracks/{id}` | Einzelner Track |
| `GET /api/search?q=&genre=` | Suche über Künstler:innen, Releases, Songs |
| `GET /media/{artist}/{file}` | Audio-Stream (Range) + Bilder |

### Auth-API (Künstlerbereich)

| Endpoint | Zweck |
|---|---|
| `POST /api/auth/register` | Konto + Künstlerprofil anlegen (`email`, `password`, `artistName`) |
| `POST /api/auth/login` | Anmelden (`email`, `password`) → setzt Session-Cookie |
| `POST /api/auth/logout` | Abmelden |
| `GET /api/auth/me` | Aktueller Login-Status + eigenes Profil |

### Studio-API (eingeloggte:r Künstler:in, nur eigenes Profil)

| Endpoint | Zweck |
|---|---|
| `PUT /api/studio/artist` | Eigenes Profil bearbeiten (`name`, `location`, `bio`, `image?`) |
| `POST /api/studio/single` | Einzelnen Song als Single veröffentlichen (`title`, `year`, `genre?`, `audio`, `cover?`) |
| `POST /api/studio/releases` | Bündel anlegen (`title`, `type`, `year`, `genre?`, `cover?`) |
| `PUT /api/studio/releases/{id}` | Eigenes Release bearbeiten (inkl. `genre`) |
| `DELETE /api/studio/releases/{id}` | Eigenes Release löschen |
| `POST /api/studio/releases/{id}/tracks` | Song zum eigenen Release hinzufügen (`title`, `genre?`, `audio`) |
| `PUT /api/studio/tracks/{id}` | Eigenen Song bearbeiten (`title`, `genre`-Override) |
| `DELETE /api/studio/tracks/{id}` | Eigenen Song löschen |

Genre ist frei wählbar; ein leeres Track-Genre erbt das des Releases.

### Admin-API (verwaltet alles)

| Endpoint | Zweck |
|---|---|
| `GET /api/manage/artists` | Alle Künstler:innen inkl. Releases/Tracks |
| `POST /api/manage/artists` | Anlegen (Form: `name`, `location`, `bio`, `image?`) |
| `PUT /api/manage/artists/{id}` | Bearbeiten (`name`, `location`, `bio`, `image?`) |
| `DELETE /api/manage/artists/{id}` | Löschen (inkl. Mediendateien + Account) |
| `POST /api/manage/artists/{id}/releases` | Release anlegen (`title`, `type`, `year`, `genre?`, `cover?`) |
| `PUT /api/manage/releases/{id}` | Release bearbeiten (inkl. `genre`) |
| `DELETE /api/manage/releases/{id}` | Release + zugehörige Dateien löschen |
| `POST /api/manage/releases/{id}/tracks` | Song hochladen (`title`, `genre?`, `audio`) |
| `PUT /api/manage/tracks/{id}` | Song bearbeiten (`title`, `genre`) |
| `DELETE /api/manage/tracks/{id}` | Song löschen |

Uploads laufen als `multipart/form-data`. Bilder werden serverseitig auf 640×640
(+160×160 Thumb) normalisiert; **Audio-Uploads sind auf MP3 (.mp3) beschränkt**.
(Die prozeduralen Demo-Tracks sind WAV und werden direkt gestreamt — die
MP3-Beschränkung gilt nur für neue Uploads.)

## Nächste mögliche Schritte

- **Admin absichern**: eigener Admin-Login/Rolle (aktuell ist `/api/manage/...`
  noch ungeschützt). Z.B. Rollenfeld am User-Account oder separates Admin-Passwort.
- Produktionshärtung der Auth: HTTPS + `Secure`-Cookie, Rate-Limiting,
  E-Mail-Verifikation, Passwort-Reset.
- Echte Transcoding-Pipeline (ffmpeg → HLS/DASH) für adaptives Streaming.
- Persistenz in einer richtigen DB statt JSON.
- Playlists, Favoriten, Hörhistorie.
- Transparente, faire Auszahlungslogik als Kernfeature sichtbar machen.
