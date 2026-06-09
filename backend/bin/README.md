# backend/bin/

Hier landen mitgelieferte Binaries, die das Backend zur Laufzeit aufruft.

## fpcalc (Chromaprint)

Wird vom `fingerprint.py`-Modul verwendet, um Audio-Fingerprints zu berechnen.

### Download

https://acoustid.org/chromaprint → „Downloads"

Für jede Plattform gibt es ein eigenes Archiv:

| Plattform     | Archiv                                            | Datei drinnen |
| ------------- | ------------------------------------------------- | ------------- |
| Windows 64-bit| `chromaprint-fpcalc-1.5.1-windows-x86_64.zip`     | `fpcalc.exe`  |
| Linux 64-bit  | `chromaprint-fpcalc-1.5.1-linux-x86_64.tar.gz`    | `fpcalc`      |
| macOS         | `chromaprint-fpcalc-1.5.1-macos-x86_64.tar.gz`    | `fpcalc`      |

### Installation

1. Archiv für deine Plattform entpacken
2. Die Datei `fpcalc` bzw. `fpcalc.exe` **direkt** in diesen `bin/`-Ordner kopieren
   (nicht in einen Unterordner!)
3. Unter Linux/macOS ausführbar machen:
   `chmod +x backend/bin/fpcalc`
4. Backend (PyCharm / uvicorn) neu starten

### Server-Deploy

Achte darauf, die **richtige Plattform-Variante** mitzuliefern. Wenn du auf
einem Linux-Server deployst, brauchst du die Linux-Binary — die Windows-`.exe`
funktioniert dort nicht.

Empfohlener Workflow für Mehrplattform-Setups: keine Binary ins Git-Repo, sondern
beim Deploy-Skript dynamisch herunterladen (siehe `.gitignore`).

### Verifizieren

Nach dem Kopieren kannst du im Admin-Panel unter
**⚙ E-Mail-Einstellungen → 🎧 Audio-Fingerprinting** prüfen, ob die Statuszeile
„✓ fpcalc gefunden" anzeigt.
