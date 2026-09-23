"""
Spendenwege für Künstlerprofile (zusätzlich zum PayPal-Feld).

Jeder Anbieter hat eine feste Liste erlaubter Domains (und ggf. einen
Pfad-Anfang). So landen keine kaputten oder fremden Links auf dem Profil –
ein Stripe-Link muss z. B. wirklich auf buy.stripe.com zeigen.

Außerdem optional eine Bankverbindung (Kontoinhaber:in + IBAN) für
Überweisungen; die IBAN wird per Prüfziffer (ISO 13616, Mod 97) validiert.
Die Plattform ist in keinem Fall am Zahlungsfluss beteiligt.
"""
from __future__ import annotations

import re
import urllib.parse

# key -> Anzeigename, erlaubte Hosts, optionaler Pfad-Anfang, Beispiel
PROVIDERS: dict[str, dict] = {
    "stripe":         {"label": "Stripe",          "hosts": ["buy.stripe.com", "donate.stripe.com"],
                       "example": "buy.stripe.com/…"},
    "liberapay":      {"label": "Liberapay",       "hosts": ["liberapay.com"],
                       "example": "liberapay.com/deinname"},
    "kofi":           {"label": "Ko-fi",           "hosts": ["ko-fi.com"],
                       "example": "ko-fi.com/deinname"},
    "buymeacoffee":   {"label": "Buy Me a Coffee", "hosts": ["buymeacoffee.com", "coff.ee"],
                       "example": "buymeacoffee.com/deinname"},
    "steady":         {"label": "Steady",          "hosts": ["steadyhq.com"],
                       "example": "steadyhq.com/de/deinname"},
    "patreon":        {"label": "Patreon",         "hosts": ["patreon.com"],
                       "example": "patreon.com/deinname"},
    "opencollective": {"label": "Open Collective", "hosts": ["opencollective.com"],
                       "example": "opencollective.com/deinname"},
    "github":         {"label": "GitHub Sponsors", "hosts": ["github.com"], "path": "/sponsors/",
                       "example": "github.com/sponsors/deinname"},
    "tipeee":         {"label": "Tipeee",          "hosts": ["tipeee.com"],
                       "example": "tipeee.com/deinname"},
    "revolut":        {"label": "Revolut",         "hosts": ["revolut.me"],
                       "example": "revolut.me/deinname"},
    "wise":           {"label": "Wise",            "hosts": ["wise.com"], "path": "/pay/me/",
                       "example": "wise.com/pay/me/deinname"},
    "bunq":           {"label": "bunq.me",         "hosts": ["bunq.me"],
                       "example": "bunq.me/deinname"},
}

MAX_URL_LEN = 300
MAX_HOLDER_LEN = 70          # Grenze des EPC-QR-Standards für den Empfängernamen


class InvalidDonationError(ValueError):
    pass


def _host_ok(host: str, allowed: list[str]) -> bool:
    host = host.lower().split(":")[0]
    if host.startswith("www."):
        host = host[4:]
    return any(host == d or host.endswith("." + d) for d in allowed)


def normalize_one(provider: str, url: str) -> str:
    """Validiert einen Spendenlink. Wirft InvalidDonationError bei Problemen."""
    url = (url or "").strip()
    if not url:
        return ""
    spec = PROVIDERS.get(provider)
    if not spec:
        raise InvalidDonationError(f"Unbekannter Anbieter: {provider}")
    label = spec["label"]
    if len(url) > MAX_URL_LEN:
        raise InvalidDonationError(f"{label}: Link ist zu lang.")
    if " " in url:
        raise InvalidDonationError(f"{label}: Der Link darf keine Leerzeichen enthalten.")
    if not url.lower().startswith(("http://", "https://")):
        url = "https://" + url
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise InvalidDonationError(f"{label}: Bitte einen vollständigen Link angeben.")
    if not _host_ok(parsed.netloc, spec["hosts"]):
        raise InvalidDonationError(
            f"{label}: Der Link muss auf {' oder '.join(spec['hosts'])} zeigen "
            f"(z. B. {spec['example']}).")
    path = parsed.path or ""
    prefix = spec.get("path")
    if prefix and not path.lower().startswith(prefix):
        raise InvalidDonationError(f"{label}: Bitte den vollständigen Link angeben "
                                   f"(z. B. {spec['example']}).")
    # Nur die Startseite des Anbieters ist kein Spendenlink.
    if not path.strip("/") or path.rstrip("/").lower() == (prefix or "").rstrip("/"):
        raise InvalidDonationError(f"{label}: Da fehlt noch dein Name bzw. deine Seite "
                                   f"(z. B. {spec['example']}).")
    return urllib.parse.urlunparse(parsed._replace(scheme="https"))


def normalize_links(raw: dict) -> dict:
    """{provider: url} validieren; leere Einträge fallen weg."""
    if not isinstance(raw, dict):
        raise InvalidDonationError("Erwartet ein Objekt mit Anbieter→Link.")
    out: dict[str, str] = {}
    for provider, url in raw.items():
        if provider not in PROVIDERS:
            continue
        cleaned = normalize_one(provider, url if isinstance(url, str) else "")
        if cleaned:
            out[provider] = cleaned
    return out


def iban_valid(iban: str) -> bool:
    """Prüfziffer nach ISO 13616 (Mod 97)."""
    if not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{10,30}", iban):
        return False
    rearranged = iban[4:] + iban[:4]
    digits = "".join(str(int(c, 36)) for c in rearranged)
    return int(digits) % 97 == 1


def normalize_bank(raw: dict) -> dict:
    """{holder, iban} validieren. Beide leer = keine Bankverbindung ({})."""
    if not isinstance(raw, dict):
        raise InvalidDonationError("Ungültige Bankverbindung.")
    holder = " ".join(str(raw.get("holder") or "").split())
    iban = re.sub(r"\s+", "", str(raw.get("iban") or "")).upper()
    if not holder and not iban:
        return {}
    if not holder:
        raise InvalidDonationError("Bitte den Namen der Kontoinhaber:in angeben.")
    if len(holder) > MAX_HOLDER_LEN:
        raise InvalidDonationError(f"Name der Kontoinhaber:in: max. {MAX_HOLDER_LEN} Zeichen.")
    if not iban_valid(iban):
        raise InvalidDonationError("Die IBAN ist ungültig – bitte auf Tippfehler prüfen.")
    return {"holder": holder, "iban": iban}


def public_links(links: dict | None) -> list[dict]:
    """Für die Profilansicht: [{provider, label, url}] in fester Reihenfolge."""
    links = links or {}
    return [{"provider": key, "label": spec["label"], "url": links[key]}
            for key, spec in PROVIDERS.items() if links.get(key)]


def provider_catalog() -> list[dict]:
    """Anbieterliste für den Profil-Editor."""
    return [{"key": key, "label": spec["label"], "example": spec["example"]}
            for key, spec in PROVIDERS.items()]
