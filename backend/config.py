"""
Zentrale Konfiguration für Riot Music.

Liest die Datei `data/config.json`. Falls sie fehlt, wird eine Vorlage angelegt.
Damit lässt sich u. a. die Admin-E-Mail-Adresse für Kontaktanfragen einstellen,
ohne den Code anzufassen.

Wer mag, kann die Werte zusätzlich per Umgebungsvariablen überschreiben
(`RIOTMUSIC_ADMIN_EMAIL`, `RIOTMUSIC_SMTP_*`).
"""
from __future__ import annotations

import json
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "data" / "config.json"

DEFAULTS: dict = {
    # Empfänger-Adresse für Kontaktformular-Nachrichten.
    # Wenn leer, werden Nachrichten nur lokal gespeichert (kein Mailversand).
    "admin_email": "",

    # SMTP-Zugangsdaten (z. B. dein Webhoster / mailbox.org / posteo etc.).
    # Wenn host leer bleibt, wird kein Mailversand versucht.
    "smtp_host": "",
    "smtp_port": 587,
    "smtp_user": "",
    "smtp_password": "",
    "smtp_from": "",           # Absender-Adresse (oft = smtp_user)
    "smtp_use_tls": True,      # STARTTLS (587). Für SSL (465) auf False setzen
                               # und smtp_use_ssl auf True.
    "smtp_use_ssl": False,

    # Öffentliche Basis-URL (für Links in E-Mails, z. B. Bestätigungslink).
    # Leer = aus der eingehenden Anfrage ableiten. In Produktion hinter einem
    # Proxy hier z. B. "https://riotmusic.de" eintragen.
    "public_base_url": "",

    # --- Plattform-Spenden ---
    # PayPal-E-Mail oder PayPal.me-Link der Betreiberin. Wenn gesetzt, erscheint
    # auf der Startseite ein Spenden-Button zur Unterstützung der Plattform.
    "platform_paypal": "",

    # --- Audio-Fingerprinting ---
    # AcoustID-API-Key (kostenlos: https://acoustid.org/api-key).
    # Leer = nur lokale Duplikatprüfung, keine Online-Lookup.
    "acoustid_api_key": "",
    # "strict": Match aus AcoustID-DB blockiert den Upload.
    # "warn":   Match wird nur protokolliert, Upload geht durch.
    # "off":    Keine AcoustID-Abfrage, nur lokale Duplikatsprüfung.
    "fingerprint_mode": "strict",
}


def _ensure_file() -> None:
    if not CONFIG_PATH.exists():
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(
            json.dumps(DEFAULTS, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def load() -> dict:
    """Lädt die Konfiguration; ENV-Variablen überschreiben Dateiwerte."""
    _ensure_file()
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        data = {}
    cfg = {**DEFAULTS, **data}

    # Optionales ENV-Override (praktisch für Produktion ohne Datei-Editierung).
    env_map = {
        "admin_email":   "RIOTMUSIC_ADMIN_EMAIL",
        "smtp_host":     "RIOTMUSIC_SMTP_HOST",
        "smtp_port":     "RIOTMUSIC_SMTP_PORT",
        "smtp_user":     "RIOTMUSIC_SMTP_USER",
        "smtp_password": "RIOTMUSIC_SMTP_PASSWORD",
        "smtp_from":     "RIOTMUSIC_SMTP_FROM",
    }
    for key, env in env_map.items():
        if env in os.environ:
            cfg[key] = os.environ[env]
    if "smtp_port" in cfg:
        try: cfg["smtp_port"] = int(cfg["smtp_port"])
        except (TypeError, ValueError): cfg["smtp_port"] = 587
    return cfg


def admin_email() -> str:
    return (load().get("admin_email") or "").strip()


def smtp_configured() -> bool:
    cfg = load()
    return bool(cfg.get("smtp_host")) and bool(admin_email())


# ---------------------------------------------------------------------------
# Schreibzugriff (Admin-UI)
# ---------------------------------------------------------------------------
EDITABLE_KEYS = (
    "admin_email", "smtp_host", "smtp_port",
    "smtp_user", "smtp_password", "smtp_from",
    "smtp_use_tls", "smtp_use_ssl",
    "acoustid_api_key", "fingerprint_mode",
    "platform_paypal", "public_base_url",
)

VALID_FP_MODES = ("strict", "warn", "off")

# Marker, damit das Passwort im UI nie im Klartext zurückkommt.
PASSWORD_MASK = "********"


def safe_view() -> dict:
    """Konfig für die Admin-UI – Passwort wird maskiert."""
    cfg = load()
    view = {k: cfg.get(k, "") for k in EDITABLE_KEYS}
    if view.get("smtp_password"):
        view["smtp_password"] = PASSWORD_MASK
    view["smtp_configured"] = smtp_configured()
    return view


def save(updates: dict) -> dict:
    """
    Persistiert nur erlaubte Schlüssel aus `updates`.

    Das Passwort wird nur überschrieben, wenn ein anderer Wert als die Maske
    übergeben wird – so kann das UI den Wert ungeändert zurückschicken, ohne
    das gespeicherte Passwort zu zerstören.
    """
    _ensure_file()
    try:
        current = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        current = {}
    merged = {**DEFAULTS, **current}

    for key in EDITABLE_KEYS:
        if key not in updates:
            continue
        val = updates[key]
        if key == "smtp_password":
            # Maske oder leerer String? -> nicht überschreiben.
            if val == PASSWORD_MASK or val is None:
                continue
        if key == "smtp_port":
            try: val = int(val)
            except (TypeError, ValueError): val = 587
        if key in ("smtp_use_tls", "smtp_use_ssl"):
            val = bool(val)
        if key == "fingerprint_mode":
            if val not in VALID_FP_MODES:
                val = "strict"
        merged[key] = val

    tmp = CONFIG_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, CONFIG_PATH)
    return safe_view()
