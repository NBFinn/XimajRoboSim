"""Erzeugt aus dem RoboSim-Logo (assets/robosim-logo-src.webp) die Varianten der App:
robosim-logo.png (dunkle Schrift, helle Flaechen), robosim-logo-light.png (weiss, dunkle Flaechen),
robosim-mark.png / robosim-mark-light.png (nur Symbol, quadratisch, fuer Icon und Setup)."""
import os
from collections import deque
import numpy as np
from PIL import Image

A = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "ximaj_robosim", "assets")
src = np.array(Image.open(os.path.join(A, "robosim-logo-src.webp")).convert("RGBA"))
alpha = src[:, :, 3] > 40
navy = alpha & (src[:, :, 2].astype(int) > src[:, :, 0].astype(int))
orange = alpha & ~navy


def keep_holes(mask):
    """Kreisrunde dunkle Flaechen (Gelenkbohrungen) bleiben dunkel."""
    h, w = mask.shape
    seen = np.zeros_like(mask)
    holes = np.zeros_like(mask)
    for y0, x0 in zip(*np.nonzero(mask)):
        if seen[y0, x0]:
            continue
        comp = []
        q = deque([(y0, x0)])
        seen[y0, x0] = True
        while q:
            y, x = q.popleft()
            comp.append((y, x))
            for ny, nx in ((y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)):
                if not (0 <= ny < h and 0 <= nx < w):
                    continue
                if mask[ny, nx]:
                    if not seen[ny, nx]:
                        seen[ny, nx] = True
                        q.append((ny, nx))
        ys, xs = zip(*comp)
        bh, bw = max(ys) - min(ys) + 1, max(xs) - min(xs) + 1
        if max(xs) < GAP and bw < 150 and 0.85 < bw / bh < 1.15 and 0.7 < len(comp) / (bw * bh) < 0.85:
            for y, x in comp:
                holes[y, x] = True
    return holes


def trim(arr):
    a = arr[:, :, 3] > 0
    ys, xs = np.nonzero(a)
    return arr[ys.min():ys.max() + 1, xs.min():xs.max() + 1]


def square(arr, pad=0.04):
    h, w = arr.shape[:2]
    s = int(max(h, w) * (1 + 2 * pad))
    out = np.zeros((s, s, 4), np.uint8)
    y, x = (s - h) // 2, (s - w) // 2
    out[y:y + h, x:x + w] = arr
    return out


GAP = 563  # erste leere Spalte zwischen Symbol und Schriftzug
light = src.copy()
white = navy & ~keep_holes(navy)
light[white, :3] = 255

save = lambda arr, name: Image.fromarray(arr).save(os.path.join(A, name))
save(trim(src), "robosim-logo.png")
save(trim(light), "robosim-logo-light.png")
save(square(trim(src[:, :GAP])), "robosim-mark.png")
save(square(trim(light[:, :GAP])), "robosim-mark-light.png")
print("Logo-Varianten erstellt:", os.path.abspath(A))
