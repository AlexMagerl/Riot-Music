"""
Bildverarbeitung für Riot Music (Pillow).

Nimmt hochgeladene Bilddaten, korrigiert die EXIF-Ausrichtung, schneidet zentriert
quadratisch zu und rendert zwei normalisierte JPEG-Größen:
  * <base>.jpg        – 640x640  (Vollansicht: Profil-/Release-Header)
  * <base>_thumb.jpg  – 160x160  (Kacheln, Player)
"""
from __future__ import annotations

import io
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

FULL_SIZE = 640
THUMB_SIZE = 160
BANNER_W = 1400
BANNER_H = 400
JPEG_QUALITY = 86
MAX_UPLOAD_BYTES = 5 * 1024 * 1024  # 5 MB


class InvalidImageError(ValueError):
    pass


def _open_jpeg(data: bytes) -> Image.Image:
    """Öffnet die Bilddaten und akzeptiert nur JPEG. Erzwingt zusätzlich ein Größenlimit."""
    if len(data) > MAX_UPLOAD_BYTES:
        raise InvalidImageError(
            f"Bild ist zu groß (max. {MAX_UPLOAD_BYTES // (1024 * 1024)} MB).")
    try:
        src = Image.open(io.BytesIO(data))
        src.load()
    except (UnidentifiedImageError, OSError) as exc:
        raise InvalidImageError("Datei ist kein gültiges Bild.") from exc
    if (src.format or "").upper() not in {"JPEG", "JPG"}:
        raise InvalidImageError("Nur JPEG-Bilder sind erlaubt (.jpg / .jpeg).")
    return src


def _to_square(img: Image.Image, size: int) -> Image.Image:
    img = ImageOps.exif_transpose(img)          # Handy-Fotos korrekt drehen
    if img.mode != "RGB":
        img = img.convert("RGB")
    w, h = img.size
    side = min(w, h)
    left = (w - side) // 2
    top = (h - side) // 2
    img = img.crop((left, top, left + side, top + side))   # zentriert quadratisch
    return img.resize((size, size), Image.LANCZOS)          # hochwertig skalieren


def save_square_image(data: bytes, dest_dir: Path, base: str) -> dict:
    """
    Speichert <base>.jpg (640) und <base>_thumb.jpg (160) in dest_dir.
    Vorhandene Dateien werden überschrieben. Gibt die Dateinamen zurück.
    """
    src = _open_jpeg(data)
    dest_dir.mkdir(parents=True, exist_ok=True)
    full_name = f"{base}.jpg"
    thumb_name = f"{base}_thumb.jpg"

    _to_square(src, FULL_SIZE).save(dest_dir / full_name, "JPEG", quality=JPEG_QUALITY, optimize=True)
    _to_square(src, THUMB_SIZE).save(dest_dir / thumb_name, "JPEG", quality=JPEG_QUALITY, optimize=True)

    return {"image": full_name, "thumb": thumb_name}


def _to_banner(img: Image.Image, w: int, h: int) -> Image.Image:
    """Zentriert auf Breitformat zuschneiden."""
    img = ImageOps.exif_transpose(img)
    if img.mode != "RGB":
        img = img.convert("RGB")
    iw, ih = img.size
    target_ratio = w / h
    img_ratio = iw / ih
    if img_ratio > target_ratio:
        # zu breit → Seiten abschneiden
        new_w = int(ih * target_ratio)
        left = (iw - new_w) // 2
        img = img.crop((left, 0, left + new_w, ih))
    else:
        # zu hoch → oben/unten abschneiden
        new_h = int(iw / target_ratio)
        top = (ih - new_h) // 2
        img = img.crop((0, top, iw, top + new_h))
    return img.resize((w, h), Image.LANCZOS)


def save_banner_image(data: bytes, dest_dir: Path, base: str) -> str:
    """
    Speichert <base>_banner.jpg (1400×400) in dest_dir.
    Eine vorhandene Datei wird überschrieben. Gibt den Dateinamen zurück.
    """
    src = _open_jpeg(data)
    dest_dir.mkdir(parents=True, exist_ok=True)
    name = f"{base}_banner.jpg"
    _to_banner(src, BANNER_W, BANNER_H).save(
        dest_dir / name, "JPEG", quality=JPEG_QUALITY, optimize=True)
    return name
