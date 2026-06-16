# Riot Music — Android-App (TWA)

Diese App ist eine **Trusted Web Activity (TWA)**: eine schlanke native Hülle,
die `https://riot-music.eu` im Vollbild anzeigt. Die App **ist** die Website —
Inhalts-Updates brauchen **keine** neue Veröffentlichung.

> Voraussetzung: Die PWA-Dateien liegen bereits im Webprojekt und sind live:
> `frontend/manifest.json`, `frontend/sw.js`, `frontend/icons/*`,
> `frontend/.well-known/assetlinks.json`. Sie müssen unter
> `https://riot-music.eu/...` erreichbar sein.

---

## Variante A — PWABuilder (am einfachsten, ohne Tooling)

1. Auf <https://www.pwabuilder.com> die URL **`https://riot-music.eu`** eingeben.
2. PWABuilder prüft das Manifest → **Package For Stores → Android**.
3. Paket-ID (Package name) auf **`eu.riotmusic.app`** setzen (muss mit
   `assetlinks.json` übereinstimmen!).
4. **Download** → du erhältst:
   - `app-release-bundle.aab` (für den Play Store)
   - ein `assetlinks.json` mit dem **echten SHA-256-Fingerprint** des Signaturschlüssels
   - eine Anleitung
5. Den **SHA-256-Fingerprint** in `frontend/.well-known/assetlinks.json`
   eintragen (Platzhalter ersetzen), Web neu deployen.

## Variante B — Bubblewrap (CLI, mehr Kontrolle)

```bash
npm install -g @bubblewrap/cli
bubblewrap init --manifest https://riot-music.eu/manifest.json
# Werte aus twa-manifest.json (in diesem Ordner) als Vorlage nutzen
bubblewrap build
```
Erzeugt `app-release-bundle.aab` und zeigt den SHA-256-Fingerprint an.

---

## Digital Asset Links (Pflicht!)

Damit die App **ohne Browserleiste** öffnet, muss
`https://riot-music.eu/.well-known/assetlinks.json` den **SHA-256-Fingerprint
des Signaturschlüssels** enthalten.

- **Play App Signing** (empfohlen): Nach dem ersten Upload findest du den
  Fingerprint in der **Play Console → App → Einrichtung → App-Signatur →
  „SHA-256-Zertifikatsfingerabdruck"**. Diesen in `assetlinks.json` eintragen.
- Prüfen lässt sich die Verknüpfung mit Googles
  [Statement List Tester](https://developers.google.com/digital-asset-links/tools/generator).

## Play-Store-Veröffentlichung

1. Play Console → **Neue App erstellen**.
2. `.aab` in einen (internen) Testtrack hochladen.
3. SHA-256-Fingerprint aus der App-Signatur in `assetlinks.json` eintragen +
   Web deployen → die Verknüpfung greift.
4. Store-Eintrag ausfüllen (Beschreibung, Screenshots, Datenschutz-URL:
   `https://riot-music.eu/datenschutz.html`), zur Prüfung einreichen.

---

## Hintergrund-Wiedergabe (wichtig bei Musik)

Die Web-App nutzt die **MediaSession-API** (in `js/app.js`): Sperrbildschirm-
Steuerung (Play/Pause/Weiter/Zurück), Titel & Cover. Damit läuft Musik bei
gesperrtem Bildschirm im TWA-Rahmen weiter und ist steuerbar.

**Falls die Wiedergabe bei gesperrtem Display abbricht** (je nach Android-Version
unterschiedlich streng), ist der nächste Ausbaustufen-Schritt der Umstieg auf
**Capacitor**: gleiche Web-Codebasis, aber echte native Hülle mit zuverlässigem
Hintergrund-Audio (Foreground-Service). Erst testen, dann ggf. wechseln.

## Paket-ID

`eu.riotmusic.app` — muss in `assetlinks.json`, in PWABuilder/Bubblewrap und in
der Play Console identisch sein. Einmal gewählt, **nicht mehr ändern** (sie
identifiziert die App im Store dauerhaft).
