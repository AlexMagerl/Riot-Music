"""
Erzeugt die PWA-/App-Icons aus dem Faust-Emoji (✊) auf dunklem Markenhintergrund.
Nur als Dev-Helfer gedacht (nutzt die Windows-Emoji-Schrift). Lauf:
    .venv\\Scripts\\python.exe tools\\make_icons.py
Ergebnis: frontend/icons/icon-192.png, icon-512.png, icon-maskable-512.png
"""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent.parent / "frontend" / "icons"
OUT.mkdir(parents=True, exist_ok=True)
BG = (14, 14, 16, 255)          # #0e0e10
EMOJI = "✊"                 # ✊
FONT_PATH = "C:/Windows/Fonts/seguiemj.ttf"
STRIKE = 109                     # native Bitmap-Größe der Segoe-UI-Emoji-Schrift

font = ImageFont.truetype(FONT_PATH, STRIKE)
tmp = Image.new("RGBA", (160, 160), (0, 0, 0, 0))
d = ImageDraw.Draw(tmp)
d.text((80, 80), EMOJI, font=font, embedded_color=True, anchor="mm")
emoji = tmp.crop(tmp.getbbox())


def make(size: int, fill_ratio: float, maskable: bool, fname: str) -> None:
    img = Image.new("RGBA", (size, size), BG)
    target_w = int(size * fill_ratio)
    target_h = int(target_w * emoji.height / emoji.width)
    em = emoji.resize((target_w, target_h), Image.LANCZOS)
    img.alpha_composite(em, ((size - target_w) // 2, (size - target_h) // 2))
    if not maskable:
        mask = Image.new("L", (size, size), 0)
        ImageDraw.Draw(mask).rounded_rectangle(
            [0, 0, size - 1, size - 1], radius=int(size * 0.22), fill=255)
        img.putalpha(mask)
    img.save(OUT / fname)
    print("geschrieben:", fname)


make(512, 0.62, False, "icon-512.png")
make(192, 0.62, False, "icon-192.png")
make(512, 0.52, True, "icon-maskable-512.png")   # mehr Rand für die Maskenzone
print("fertig ->", OUT)
