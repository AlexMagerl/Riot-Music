# Verzeichnis von Verarbeitungstätigkeiten (VVT)

*nach Art. 30 DSGVO — für die Plattform „Riot Music"*

> Hinweis: Dies ist eine ausgefüllte Vorlage für eine kleine, von einer
> Einzelperson betriebene Plattform. Bitte vor dem Produktivbetrieb prüfen
> und bei Änderungen am Funktionsumfang aktualisieren. Ersetzt keine
> Rechtsberatung.

---

## 1. Verantwortlicher

- **Name:** Alexander Magerl
- **Anschrift:** Gotlandstr. 2, 10439 Berlin
- **Kontakt:** magerl.alexander@gmail.com (bzw. studio@dingsbums-productions.de)
- **Datenschutzbeauftragter:** nicht bestellt (gesetzlich nicht erforderlich —
  keine 20+ Personen mit ständiger Datenverarbeitung, keine umfangreiche
  Verarbeitung besonderer Kategorien)

---

## 2. Verarbeitungstätigkeiten

### 2.1 Künstler-Accounts (Registrierung & Profil)
- **Zweck:** Betrieb der Künstlerprofile, Authentifizierung
- **Betroffene:** registrierte Künstler:innen
- **Datenkategorien:** E-Mail, Passwort-Hash (PBKDF2), Künstlername, Ort, Bio,
  Bild-/Videolinks, PayPal-Adresse (sofern angegeben), Zeitpunkt + IP der
  AGB-Zustimmung, Verifizierungsstatus
- **Rechtsgrundlage:** Art. 6 Abs. 1 lit. b DSGVO (Vertrag) bzw. lit. a
  (Einwilligung durch aktive Eingabe), lit. f (Beweissicherung AGB-Zustimmung)
- **Löschfrist:** bis zur Account-Löschung (Selbstlöschung oder durch Admin);
  Medien innerhalb von 30 Tagen
- **Empfänger:** Hosting-Dienstleister (Auftragsverarbeiter)

### 2.2 E-Mail-Bestätigung (Double-Opt-In)
- **Zweck:** Verifikation der E-Mail-Adresse, Spam-/Fake-Schutz
- **Datenkategorien:** E-Mail, signiertes Token (zeitlich befristet)
- **Rechtsgrundlage:** Art. 6 Abs. 1 lit. f (Integrität der Plattform)
- **Empfänger:** SMTP-Anbieter (siehe 3.)

### 2.3 Kontaktformular & Inhalts-Meldungen
- **Zweck:** Bearbeitung von Anfragen; Notice-and-Action bei gemeldeten Inhalten
- **Betroffene:** Absender:innen von Anfragen/Meldungen
- **Datenkategorien:** Name, E-Mail, Betreff, Nachricht, IP, Zeitpunkt
  (bei Meldungen: gemeldetes Profil, Grund, IP)
- **Rechtsgrundlage:** Art. 6 Abs. 1 lit. b / lit. f DSGVO
- **Löschfrist:** nach abschließender Bearbeitung

### 2.4 Server-Logfiles
- **Zweck:** Sicherheit, Stabilität, Missbrauchsabwehr
- **Datenkategorien:** IP-Adresse, Zeitpunkt, aufgerufene URL, Statuscode,
  User-Agent
- **Rechtsgrundlage:** Art. 6 Abs. 1 lit. f DSGVO
- **Löschfrist:** kurzfristig (Richtwert 7–14 Tage)

### 2.5 Spam-/Missbrauchsabwehr (Captcha, Rate-Limiting, Honeypot)
- **Zweck:** Schutz vor automatisierten Massen-Registrierungen/-Anfragen
- **Datenkategorien:** IP-Adresse (nur im Arbeitsspeicher, kurzlebig)
- **Rechtsgrundlage:** Art. 6 Abs. 1 lit. f DSGVO

### 2.6 Reichweiten-/Nutzungszählung (anonym)
- **Zweck:** Anzeige beliebter Songs, interne Nutzungsübersicht
- **Datenkategorien:** **anonyme** Zähler pro Track / pro Spenden-Button —
  **kein Personenbezug**, keine Hörerprofile
- **Hinweis:** mangels Personenbezug streng genommen nicht VVT-pflichtig,
  hier nur zur Vollständigkeit dokumentiert

### 2.7 Audio-Fingerprinting (Upload-Prüfung)
- **Zweck:** Erkennung von Doppel-Uploads und urheberrechtlich geschütztem
  Fremdmaterial
- **Datenkategorien:** technischer Audio-Fingerprint (kein Personenbezug)
- **Rechtsgrundlage:** Art. 6 Abs. 1 lit. f DSGVO
- **Empfänger:** AcoustID (MetaBrainz Foundation) — nur Fingerprint + Dauer

---

## 3. Auftragsverarbeiter & externe Dienste

| Dienst | Zweck | Vertrag/Grundlage |
| --- | --- | --- |
| Hosting-Anbieter (Netcup GmbH) | Server/Hosting | AV-Vertrag (Art. 28 DSGVO) abgeschlossen |
| SMTP-Anbieter (z. B. Google/Gmail) | E-Mail-Versand | Verarbeitung der Empfängerdaten; ggf. Drittland (USA) |
| AcoustID / MetaBrainz Foundation | Fingerprint-Abgleich | nur technischer Fingerprint, kein Personenbezug |
| PayPal (Europe) S.à r.l. et Cie | Spendenabwicklung (Weiterleitung) | **eigenständig Verantwortlicher**, nicht Auftragsverarbeiter; Drittland (USA) möglich |

---

## 4. Technische und organisatorische Maßnahmen (TOM)

- **Transportverschlüsselung:** HTTPS/TLS (automatisch via Reverse-Proxy)
- **Passwörter:** ausschließlich als Hash (PBKDF2-HMAC-SHA256, gesalzen)
- **Sitzungen:** HttpOnly-Cookie, signiertes Token
- **Zugriffsschutz:** Admin-Funktionen nur nach Authentifizierung
- **Datensparsamkeit:** kein Tracking, keine Werbe-Cookies, nur notwendiges
  Session-Cookie
- **Missbrauchsabwehr:** Captcha, Honeypot, IP-Rate-Limiting, Double-Opt-In
- **Backups:** regelmäßige (verschlüsselte) Sicherung der Server-Daten
- **Löschkonzept:** Selbst- und Admin-Löschung von Profilen inkl. Medien

---

*Stand: Juni 2026 · zuletzt geprüft: __________*
