"""
Schlanker SMTP-Versand für Riot Music – ohne externe Dependencies.

Verwendet die Standardbibliothek (smtplib + email.message). Sendet die
Kontakt-Mails an die in `config.json` hinterlegte Admin-E-Mail.

Fehler beim Versand werden protokolliert, blockieren aber NICHT die Annahme
einer Kontaktnachricht – die Nachricht ist immer schon lokal gespeichert.
"""
from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage

import config

log = logging.getLogger("riotmusic.mail")


def can_send() -> bool:
    """Ist überhaupt ein SMTP-Host konfiguriert? (Versand grundsätzlich möglich.)"""
    return bool((config.load().get("smtp_host") or "").strip())


def _send(to_addr: str, subject: str, body: str,
          reply_to: str | None = None) -> bool:
    """
    Generischer SMTP-Versand. Gibt True bei Erfolg zurück, sonst False
    (ohne Exception – Aufrufer entscheiden über die Reaktion).
    """
    cfg = config.load()
    host = (cfg.get("smtp_host") or "").strip()
    to_addr = (to_addr or "").strip()
    if not host or not to_addr:
        log.info("Mailversand übersprungen: smtp_host oder Empfänger leer.")
        return False

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = (cfg.get("smtp_from") or cfg.get("smtp_user") or to_addr).strip()
    msg["To"] = to_addr
    if reply_to:
        msg["Reply-To"] = reply_to
    msg.set_content(body)

    port = int(cfg.get("smtp_port") or 587)
    user = cfg.get("smtp_user") or ""
    password = cfg.get("smtp_password") or ""
    use_ssl = bool(cfg.get("smtp_use_ssl"))
    use_tls = bool(cfg.get("smtp_use_tls", True))

    try:
        if use_ssl:
            ctx = ssl.create_default_context()
            with smtplib.SMTP_SSL(host, port, context=ctx, timeout=20) as s:
                if user: s.login(user, password)
                s.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=20) as s:
                s.ehlo()
                if use_tls:
                    s.starttls(context=ssl.create_default_context())
                    s.ehlo()
                if user: s.login(user, password)
                s.send_message(msg)
        return True
    except Exception as exc:    # pragma: no cover (Netzwerk)
        log.warning("Mailversand fehlgeschlagen: %s", exc)
        return False


def send_verification(to_email: str, verify_link: str, artist_name: str = "") -> bool:
    """Schickt die Double-Opt-In-Bestätigungsmail an eine:n neue:n Künstler:in."""
    greeting = f"Hallo {artist_name}," if artist_name else "Hallo,"
    body = (
        f"{greeting}\n\n"
        "willkommen bei Riot Music! Bitte bestätige deine E-Mail-Adresse, um dein "
        "Künstlerprofil zu aktivieren. Klicke dazu auf den folgenden Link:\n\n"
        f"{verify_link}\n\n"
        "Der Link ist 48 Stunden gültig. Solange dein Konto nicht bestätigt ist, "
        "wird dein Profil nicht öffentlich angezeigt.\n\n"
        "Falls du dich nicht bei Riot Music registriert hast, ignoriere diese "
        "E-Mail einfach – dann passiert nichts.\n\n"
        "✊ Riot Music"
    )
    return _send(to_email, "Bitte bestätige deine Anmeldung bei Riot Music", body)


def send_contact_notification(name: str, sender_email: str,
                              subject: str, body: str, ip: str) -> bool:
    """
    Schickt eine formatierte Kontakt-Mail an die Admin-Adresse.

    Gibt True bei Erfolg, False bei Konfigurationsfehler oder SMTP-Problem
    zurück. Wirft keine Exception – Aufrufer entscheiden, wie sie reagieren.
    """
    to_addr = (config.load().get("admin_email") or "").strip()
    if not to_addr:
        log.info("Kontakt-Mail übersprungen: admin_email leer.")
        return False
    text = (
        f"Neue Kontaktnachricht über das Riot-Music-Formular:\n\n"
        f"Name:    {name}\n"
        f"E-Mail:  {sender_email}\n"
        f"IP:      {ip}\n"
        f"Betreff: {subject}\n\n"
        f"--- Nachricht ---\n{body}\n"
    )
    return _send(to_addr, f"[Riot Music – Kontakt] {subject}", text,
                 reply_to=sender_email)
