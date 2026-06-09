"""
Prozeduraler Audio-Generator für Riot Music.

Erzeugt für jeden Track im Katalog eine kurze, abspielbare WAV-Datei.
Verwendet Karplus-Strong-Synthese (gezupfte Saite) + einfachen Bass,
komplett mit der Python-Standardbibliothek – keine externen Abhängigkeiten,
kein Copyright-Problem.

Aufruf:
    python backend/generate_media.py
"""
from __future__ import annotations

import json
import math
import random
import struct
import wave
from pathlib import Path

SAMPLE_RATE = 22050
BASE_DIR = Path(__file__).resolve().parent
CATALOG_PATH = BASE_DIR / "data" / "catalog.json"
MEDIA_DIR = BASE_DIR / "media"

# Halbton-Offsets gängiger Skalen (relativ zum Grundton)
SCALES = {
    "minor_pentatonic": [0, 3, 5, 7, 10],
    "major_pentatonic": [0, 2, 4, 7, 9],
    "dorian": [0, 2, 3, 5, 7, 9, 10],
    "natural_minor": [0, 2, 3, 5, 7, 8, 10],
}

# Pro Genre eine grobe Klangfarbe (Skala, Tempo-Bereich, Grundton-Bereich)
GENRE_PROFILE = {
    "Blues Rock": dict(scale="minor_pentatonic", bpm=(96, 120), root=(45, 52), decay=0.996),
    "Punk": dict(scale="minor_pentatonic", bpm=(160, 190), root=(48, 55), decay=0.992),
    "Folk": dict(scale="major_pentatonic", bpm=(80, 104), root=(50, 57), decay=0.997),
    "Dub / Reggae": dict(scale="natural_minor", bpm=(70, 84), root=(40, 47), decay=0.998),
    "Ambient / Electronic": dict(scale="dorian", bpm=(60, 76), root=(45, 52), decay=0.999),
}


def midi_to_freq(note: int) -> float:
    return 440.0 * (2 ** ((note - 69) / 12.0))


def karplus_strong(freq: float, n_samples: int, decay: float, rng: random.Random) -> list[float]:
    """Erzeugt einen gezupften Ton via Karplus-Strong."""
    period = max(2, int(SAMPLE_RATE / freq))
    buf = [rng.uniform(-1.0, 1.0) for _ in range(period)]
    out = []
    idx = 0
    for _ in range(n_samples):
        cur = buf[idx]
        nxt = buf[(idx + 1) % period]
        new = (cur + nxt) * 0.5 * decay
        buf[idx] = new
        out.append(cur)
        idx = (idx + 1) % period
    return out


def make_note(freq: float, dur: float, decay: float, rng: random.Random, gain: float = 1.0) -> list[float]:
    n = int(SAMPLE_RATE * dur)
    tone = karplus_strong(freq, n, decay, rng)
    # kurze Attack-/Release-Hülle gegen Klicks
    a = int(0.005 * SAMPLE_RATE)
    r = int(0.02 * SAMPLE_RATE)
    for i in range(min(a, n)):
        tone[i] *= i / a
    for i in range(min(r, n)):
        tone[n - 1 - i] *= i / r
    return [s * gain for s in tone]


def make_bass(freq: float, dur: float, rng: random.Random, gain: float = 0.5) -> list[float]:
    """Weicher Sinus-Bass mit leichter Sättigung."""
    n = int(SAMPLE_RATE * dur)
    out = []
    for i in range(n):
        t = i / SAMPLE_RATE
        env = math.exp(-3.0 * t / dur)
        s = math.sin(2 * math.pi * freq * t)
        s = math.tanh(1.6 * s)  # leichte Sättigung
        out.append(s * env * gain)
    return out


def _profile_for(genre: str) -> dict:
    """Genres sind frei wählbar – für unbekannte wird deterministisch eines der
    Klangprofile anhand des Genre-Namens gewählt."""
    prof = GENRE_PROFILE.get(genre)
    if prof is not None:
        return prof
    vals = list(GENRE_PROFILE.values())
    return vals[sum(ord(c) for c in (genre or "x")) % len(vals)]


def generate_track(track_id: str, genre: str) -> list[float]:
    rng = random.Random(track_id)
    prof = _profile_for(genre)
    scale = SCALES[prof["scale"]]
    bpm = rng.randint(*prof["bpm"])
    root = rng.randint(*prof["root"])
    decay = prof["decay"]

    beat = 60.0 / bpm           # Sekunden pro Beat
    step = beat / 2.0           # Achtel
    total_seconds = 16.0
    n_steps = int(total_seconds / step)
    n_total = int(total_seconds * SAMPLE_RATE)

    mix = [0.0] * (n_total + SAMPLE_RATE)  # etwas Puffer für Ausklang

    # Melodie: gezupfte Saite, läuft über die Skala spazieren
    degree = 0
    octave_choices = [0, 0, 0, 12]
    for s in range(n_steps):
        if rng.random() < 0.18:
            continue  # gelegentliche Pause -> Groove
        degree = max(0, min(len(scale) * 2 - 1, degree + rng.choice([-2, -1, -1, 1, 1, 2])))
        oct_off = octave_choices[degree // len(scale)] if degree // len(scale) < len(octave_choices) else 12
        note = root + 12 + scale[degree % len(scale)] + (12 if degree >= len(scale) else 0)
        freq = midi_to_freq(note)
        dur = step * rng.choice([1, 1, 2])
        note_samples = make_note(freq, dur + 0.15, decay, rng, gain=0.55)
        start = int(s * step * SAMPLE_RATE)
        for i, v in enumerate(note_samples):
            if start + i < len(mix):
                mix[start + i] += v

    # Bass: Grundton auf jedem Beat
    n_beats = int(total_seconds / beat)
    for b in range(n_beats):
        bass_note = root + scale[rng.choice([0, 0, 0, 2, 4]) % len(scale)] - 12
        freq = midi_to_freq(bass_note)
        bass_samples = make_bass(freq, beat * 0.95, rng, gain=0.45)
        start = int(b * beat * SAMPLE_RATE)
        for i, v in enumerate(bass_samples):
            if start + i < len(mix):
                mix[start + i] += v

    return mix[:n_total]


def normalize(samples: list[float], peak: float = 0.89) -> list[float]:
    hi = max((abs(s) for s in samples), default=1.0) or 1.0
    factor = peak / hi
    return [s * factor for s in samples]


def write_wav(path: Path, samples: list[float]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        frames = bytearray()
        for s in samples:
            v = int(max(-1.0, min(1.0, s)) * 32767)
            frames += struct.pack("<h", v)
        w.writeframes(bytes(frames))


def main() -> None:
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    count = 0
    for artist in catalog["artists"]:
        for release in artist["releases"]:
            for track in release["tracks"]:
                genre = track.get("genre") or release.get("genre") or ""
                out_path = MEDIA_DIR / artist["id"] / f"{track['id']}.wav"
                if out_path.exists():
                    print(f"  skip  {out_path.relative_to(BASE_DIR)} (existiert)")
                    continue
                print(f"  gen   {artist['name']} – {track['title']}")
                samples = normalize(generate_track(track["id"], genre))
                write_wav(out_path, samples)
                count += 1
    print(f"\nFertig. {count} neue Track(s) erzeugt in {MEDIA_DIR}")


if __name__ == "__main__":
    main()
