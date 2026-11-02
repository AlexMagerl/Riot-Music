"""
Notfall-Werkzeug für den Server – z. B. wenn Handy UND Wiederherstellungscodes
weg sind und man sich nicht mehr in den Admin-Bereich einloggen kann.

Auf dem Server (im Ordner ~/Riot-Music) ausführen:

    python3 backend/manage.py list
    python3 backend/manage.py disable-2fa  name@beispiel.de
    python3 backend/manage.py logout-all   name@beispiel.de
    python3 backend/manage.py set-password name@beispiel.de

Nutzt nur die Standardbibliothek; der laufende Dienst übernimmt Änderungen
automatisch (users.json wird bei Änderung neu eingelesen).
"""
from __future__ import annotations

import getpass
import sys

import accounts
import auth


def _user_or_exit(email: str) -> dict:
    user = accounts.find_user(email)
    if not user:
        sys.exit(f"Kein Konto mit der E-Mail {email!r} gefunden.")
    return user


def cmd_list() -> None:
    for u in accounts.data()["users"]:
        flags = []
        if u.get("role") == "admin":
            flags.append("ADMIN")
        if accounts.has_2fa(u):
            flags.append("2FA")
        if not accounts.is_active(u):
            flags.append("wartet")
        print(f"{u['email']:40} {' '.join(flags)}")


def cmd_disable_2fa(email: str) -> None:
    _user_or_exit(email)
    accounts.update(email, totpEnabled=None, totpSecret=None, totpLastStep=None,
                    recoveryCodes=None, totpPendingSecret=None)
    accounts.bump_session_version(email)
    print(f"2FA für {email} ausgeschaltet, alle Sitzungen beendet. "
          "Beim nächsten Login (Admin) wird die Einrichtung erneut verlangt.")


def cmd_logout_all(email: str) -> None:
    _user_or_exit(email)
    accounts.bump_session_version(email)
    print(f"Alle Sitzungen und gemerkten Geräte von {email} wurden beendet.")


def cmd_set_password(email: str) -> None:
    _user_or_exit(email)
    pw = getpass.getpass("Neues Passwort: ")
    if len(pw) < 8:
        sys.exit("Passwort muss mind. 8 Zeichen haben.")
    if pw != getpass.getpass("Wiederholen: "):
        sys.exit("Die Passwörter stimmen nicht überein.")
    accounts.set_password(email, auth.hash_password(pw))
    print(f"Passwort für {email} gesetzt, alle Sitzungen beendet.")


COMMANDS = {
    "list": (cmd_list, 0),
    "disable-2fa": (cmd_disable_2fa, 1),
    "logout-all": (cmd_logout_all, 1),
    "set-password": (cmd_set_password, 1),
}

if __name__ == "__main__":
    name, args = (sys.argv[1] if len(sys.argv) > 1 else ""), sys.argv[2:]
    if name not in COMMANDS or len(args) != COMMANDS[name][1]:
        sys.exit(__doc__)
    COMMANDS[name][0](*[a.strip().lower() for a in args])
