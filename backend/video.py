"""
YouTube/Vimeo-URL-Validierung für Künstlerprofile.

Akzeptiert nur URLs von vertrauenswürdigen Quellen, normalisiert sie zu
Embed-Links und validiert gegen Code-Injection.
"""
from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse


class InvalidVideoURLError(ValueError):
    pass


def _extract_youtube_id(url: str) -> str:
    """Extrahiert die Video-ID aus einer YouTube-URL. Akzeptiert mehrere Formate."""
    # youtu.be/VIDEO_ID
    match = re.search(r"youtu\.be/([a-zA-Z0-9_-]+)", url)
    if match:
        return match.group(1)
    # youtube.com/watch?v=VIDEO_ID
    match = re.search(r"youtube\.com/watch\?.*v=([a-zA-Z0-9_-]+)", url)
    if match:
        return match.group(1)
    # youtube.com/embed/VIDEO_ID (schon normalisiert)
    match = re.search(r"youtube\.com/embed/([a-zA-Z0-9_-]+)", url)
    if match:
        return match.group(1)
    return None


def _extract_vimeo_id(url: str) -> str:
    """Extrahiert die Video-ID aus einer Vimeo-URL."""
    # vimeo.com/NUMERIC_ID oder player.vimeo.com/video/NUMERIC_ID
    match = re.search(r"vimeo\.com/(\d+)", url)
    if match:
        return match.group(1)
    match = re.search(r"player\.vimeo\.com/video/(\d+)", url)
    if match:
        return match.group(1)
    return None


def normalize_and_validate(url: str | None) -> str | None:
    """
    Normalisiert eine Video-URL zu einem sicheren Embed-Link.
    Akzeptiert nur YouTube und Vimeo. Gibt None zurück, falls URL leer.
    Wirft InvalidVideoURLError bei ungültigen URLs.
    """
    if not url or not url.strip():
        return None

    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    try:
        parsed = urlparse(url)
    except Exception as e:
        raise InvalidVideoURLError("Ungültige URL.") from e

    domain = (parsed.netloc or "").lower()

    # YouTube
    if "youtube" in domain or "youtu.be" in domain:
        vid = _extract_youtube_id(url)
        if not vid:
            raise InvalidVideoURLError("Ungültige YouTube-URL.")
        return f"https://www.youtube.com/embed/{vid}"

    # Vimeo
    if "vimeo" in domain:
        vid = _extract_vimeo_id(url)
        if not vid:
            raise InvalidVideoURLError("Ungültige Vimeo-URL.")
        return f"https://player.vimeo.com/video/{vid}"

    raise InvalidVideoURLError("Nur YouTube und Vimeo werden unterstützt.")
