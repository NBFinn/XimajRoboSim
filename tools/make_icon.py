"""Erzeugt Programm-Icon und Setup-Bilder aus dem RoboSim-Symbol (vorher tools/make_logo.py ausfuehren)."""
import os
from PIL import Image, ImageDraw

A = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "ximaj_robosim", "assets")
NAVY, BLACK = (6, 30, 68), (0, 0, 0)
logo = Image.open(os.path.join(A, "robosim-mark.png")).convert("RGBA")
logo_light = Image.open(os.path.join(A, "robosim-mark-light.png")).convert("RGBA")


def fit(img, h):
    w = round(img.width * h / img.height)
    return img.resize((w, h), Image.LANCZOS)


def navy_gradient(w, h):
    """65°-Verlauf wie auf ximaj.com: Navy bis 40 %, dann Richtung Schwarz"""
    g = Image.new("RGB", (w, h))
    px = g.load()
    import math
    ax, ay = math.cos(math.radians(25)), math.sin(math.radians(25))
    tmax = w * ax + h * ay
    for y in range(h):
        for x in range(w):
            t = (x * ax + y * ay) / tmax
            k = 0 if t < 0.4 else (t - 0.4) / 0.6
            px[x, y] = tuple(int(NAVY[i] * (1 - k) + BLACK[i] * k) for i in range(3))
    return g


# Programm-Icon: Schild auf transparentem Quadrat
S = 512
icon = Image.new("RGBA", (S, S), (0, 0, 0, 0))
lg = fit(logo, int(S * 0.94))
icon.alpha_composite(lg, ((S - lg.width) // 2, (S - lg.height) // 2))
icon.save(os.path.join(A, "ximaj_robosim.png"))
icon.save(os.path.join(A, "ximaj_robosim.ico"), sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])

# Setup-Assistent: grosses Bild (links) und kleines Bild (oben rechts), je 100 % und 200 %
for scale in (1, 2):
    w, h = 164 * scale, 314 * scale
    big = navy_gradient(w, h).convert("RGBA")
    l2 = fit(logo_light, int(120 * scale))
    big.alpha_composite(l2, ((w - l2.width) // 2, int(h * 0.30)))
    d = ImageDraw.Draw(big)
    d.rectangle([w // 2 - 22 * scale, int(h * 0.30) + l2.height + 18 * scale,
                 w // 2 + 22 * scale, int(h * 0.30) + l2.height + 20 * scale], fill=(14, 116, 187, 255))
    big.convert("RGB").save(os.path.join(A, f"wizard_large_{scale}x.bmp"))
    s = 55 * scale
    small = Image.new("RGBA", (s, s), (255, 255, 255, 255))
    l3 = fit(logo, int(s * 0.9))
    small.alpha_composite(l3, ((s - l3.width) // 2, (s - l3.height) // 2))
    small.convert("RGB").save(os.path.join(A, f"wizard_small_{scale}x.bmp"))
print("Icon und Setup-Bilder erstellt:", os.path.abspath(A))
