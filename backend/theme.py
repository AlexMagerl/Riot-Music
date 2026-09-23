"""
Akzentfarbe für Künstlerseiten.

Künstler:innen wählen einen Farbton; damit Buttons und Überschriften auf dem
dunklen Hintergrund lesbar bleiben, werden Sättigung und Helligkeit in einen
sicheren Bereich gerückt (der Farbton selbst bleibt erhalten). Die gleiche
Logik steckt für die Live-Vorschau in frontend/js/accent.js.
Leerer Wert = Standard-Rot der Plattform.
"""
from __future__ import annotations

import colorsys
import re

MIN_SAT = 0.5
MIN_LIGHT, MAX_LIGHT = 0.45, 0.6
MIN_LUMINANCE = 0.12      # z. B. reines Blau wird so weit aufgehellt, bis es sich abhebt
MONO = "#ededed"          # farblose Eingaben ergeben einen Schwarz-Weiß-Look


class InvalidColorError(ValueError):
    pass


def _luminance(r: float, g: float, b: float) -> float:
    def lin(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


def normalize(value: str | None) -> str:
    """'#RRGGBB' (lesbar gemacht) oder '' für den Standard."""
    v = (value or "").strip().lower()
    if not v:
        return ""
    m = re.fullmatch(r"#?([0-9a-f]{3}|[0-9a-f]{6})", v)
    if not m:
        raise InvalidColorError("Bitte eine Farbe im Format #RRGGBB wählen.")
    hexv = m.group(1)
    if len(hexv) == 3:
        hexv = "".join(c * 2 for c in hexv)
    r, g, b = (int(hexv[i:i + 2], 16) / 255 for i in (0, 2, 4))
    hue, light, sat = colorsys.rgb_to_hls(r, g, b)
    if sat < 0.08 or light < 0.04 or light > 0.97:
        return MONO                    # Schwarz/Weiß/Grau → Schwarz-Weiß-Look
    sat = max(sat, MIN_SAT)
    light = min(max(light, MIN_LIGHT), MAX_LIGHT)
    r, g, b = colorsys.hls_to_rgb(hue, light, sat)
    while _luminance(r, g, b) < MIN_LUMINANCE and light < 0.75:
        light += 0.02
        r, g, b = colorsys.hls_to_rgb(hue, light, sat)
    return "#{:02x}{:02x}{:02x}".format(*(round(c * 255) for c in (r, g, b)))
