"""
Validierung & Normalisierung von Social-Media-Links für Künstlerprofile.

Erlaubt pro Plattform genau einen Link und prüft, dass die URL zu einer
zugelassenen Domain der jeweiligen Plattform gehört (gegen Phishing/Spam).
Für "website" ist jede http(s)-URL erlaubt.
"""
from __future__ import annotations

import urllib.parse

# platform -> Liste erlaubter Host-Endungen (None = beliebige Domain).
PLATFORMS: dict[str, list[str] | None] = {
    "website":    None,
    "instagram":  ["instagram.com"],
    "facebook":   ["facebook.com", "fb.com", "fb.me"],
    "x":          ["x.com", "twitter.com"],
    "tiktok":     ["tiktok.com"],
    "youtube":    ["youtube.com", "youtu.be"],
    "bandcamp":   ["bandcamp.com"],
    "soundcloud": ["soundcloud.com"],
    "spotify":    ["spotify.com"],
    "mastodon":   None,   # föderiert – beliebiger Host
}

MAX_URL_LEN = 300


class InvalidSocialURLError(ValueError):
    pass


def _host_ok(host: str, allowed: list[str]) -> bool:
    host = host.lower()
    if host.startswith("www."):
        host = host[4:]
    return any(host == d or host.endswith("." + d) for d in allowed)


def normalize_one(platform: str, url: str) -> str:
    """Validiert eine einzelne URL. Wirft InvalidSocialURLError bei Problemen."""
    url = (url or "").strip()
    if not url:
        return ""
    if len(url) > MAX_URL_LEN:
        raise InvalidSocialURLError("URL zu lang.")
    if platform not in PLATFORMS:
        raise InvalidSocialURLError(f"Unbekannte Plattform: {platform}")

    # Schema ergänzen, falls die Person es weggelassen hat.
    if not url.lower().startswith(("http://", "https://")):
        url = "https://" + url
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise InvalidSocialURLError("Bitte eine vollständige URL angeben.")

    allowed = PLATFORMS[platform]
    if allowed is not None and not _host_ok(parsed.netloc, allowed):
        raise InvalidSocialURLError(
            f"Link passt nicht zu {platform} (erlaubt: {', '.join(allowed)})."
        )
    # Auf https vereinheitlichen.
    parsed = parsed._replace(scheme="https")
    return urllib.parse.urlunparse(parsed)


def normalize_links(raw: dict) -> dict:
    """
    Nimmt ein dict {platform: url}, validiert jeden Eintrag und gibt ein
    bereinigtes dict zurück (leere Felder werden weggelassen).
    """
    if not isinstance(raw, dict):
        raise InvalidSocialURLError("Erwartet ein Objekt mit Plattform→URL.")
    out: dict[str, str] = {}
    for platform, url in raw.items():
        if platform not in PLATFORMS:
            continue  # unbekannte Felder ignorieren
        cleaned = normalize_one(platform, url if isinstance(url, str) else "")
        if cleaned:
            out[platform] = cleaned
    return out
