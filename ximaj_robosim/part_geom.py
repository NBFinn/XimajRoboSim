"""Detailmodelle der Katalogteile der Ximaj RoboSim (eigene Konstruktion, Millimeter, nur NumPy).

build(kind, style, size, **p) -> [(verts float32 (N,3), normals float32 (N,3), faces uint32 (M,3), mat)]
Lokales System wie in der 3D-Ansicht: x/y mittig, z=0 unten bis z=H, size=(L, W, H).
[] bedeutet: keine Detaildarstellung, die Ansicht zeichnet die einfache Form.
Bewegtes und Leuchtendes (Gurtmarken, Lichtstrahl, Kuppel, Status-LED) zeichnet die Ansicht selbst.
Details haben feste Masse (Pfosten 60 mm, Draht 3 mm, Rollen 50 mm ...), nur die Hauptmasse folgen size.
"""
import math
import numpy as np

MATS = ("paint", "frame", "belt", "metal", "dark", "rubber", "motor", "wood", "wood2", "cardboard", "tape", "label",
        "glass", "warn", "beam", "handle", "mesh", "reflector")

# Darstellungen je Objektart fuer das Eigenschaften-Panel: (style, Anzeigetext); "" = Standard
STYLES = {
    "box": [("", "Einfacher Quader"), ("pallet", "Euro-Palette"), ("cabinet", "Schaltschrank"), ("table", "Arbeitstisch"),
            ("gitterbox", "Gitterbox"), ("shelf", "Lagerregal"), ("pedestal", "Roboter-Sockel"),
            ("fixture", "Spannvorrichtung"), ("carton", "Karton")],
    "workpiece": [("", "Einfacher Quader"), ("carton", "Karton")],
    "cylinder": [("", "Einfacher Zylinder"), ("column", "Säule mit Fußplatte")],
    "conveyor": [("", "Gurtband"), ("roller", "Rollenbahn")],
}


# ------------------------------------------------------------------ Grundkoerper
MAX_SIZE = 20000.0      # groessere Teile (mm) werden einfach dargestellt
MAX_TRIS = 150000       # Obergrenze je Teil, schuetzt vor Einfrieren bei extremen Massen


class _Budget(Exception):
    pass


class _Mesh:
    """Sammelt Flaechen je Material; Dreiecke werden passend zu den Normalen ausgerichtet."""

    def __init__(self):
        self.parts = {}
        self.tris = 0

    def add(self, v, n, f, mat):
        v = np.asarray(v, float).reshape(-1, 3)
        n = np.asarray(n, float).reshape(-1, 3)
        f = np.asarray(f, np.int64).reshape(-1, 3)
        if not len(f):
            return
        self.tris += len(f)
        if self.tris > MAX_TRIS:
            raise _Budget()
        a, b, c = v[f[:, 0]], v[f[:, 1]], v[f[:, 2]]
        cr = np.cross(b - a, c - a)
        keep = np.linalg.norm(cr, axis=1) > 1e-9
        f, cr = f[keep], cr[keep]
        flip = np.einsum("ij,ij->i", cr, n[f].sum(axis=1)) < 0
        f[flip] = f[flip][:, ::-1]
        bucket = self.parts.setdefault(mat, [[], [], [], 0])
        bucket[0].append(v)
        bucket[1].append(n)
        bucket[2].append(f + bucket[3])
        bucket[3] += len(v)

    def poly(self, pts, mat, hint):
        """Ebenes, konvexes Vieleck; hint = ungefaehre Aussenrichtung"""
        p = np.asarray(pts, float)
        n = np.zeros(3)
        for i in range(len(p)):
            a, b = p[i], p[(i + 1) % len(p)]
            n += ((a[1] - b[1]) * (a[2] + b[2]), (a[2] - b[2]) * (a[0] + b[0]), (a[0] - b[0]) * (a[1] + b[1]))
        ln = np.linalg.norm(n)
        if ln < 1e-12:
            return
        n /= ln
        if np.dot(n, hint) < 0:
            n = -n
        self.add(p, np.tile(n, (len(p), 1)), [(0, i, i + 1) for i in range(1, len(p) - 1)], mat)

    def obox(self, center, axes, half, mat, bevel=None):
        """Quader mit 45-Grad-Fasen an allen Kanten; axes = Zeilen lokale Achsen"""
        c = np.asarray(center, float)
        A = np.asarray(axes, float)
        h = np.maximum(np.asarray(half, float), 1e-3)
        b = min(3.0, 0.12 * min(h) * 2) if bevel is None else bevel
        b = max(0.0, min(b, 0.45 * min(h)))
        W = lambda p: c + p @ A

        def V(s, k):
            p = s * (h - b)
            p[k] = s[k] * h[k]
            return W(p)

        for k in range(3):
            i, j = [d for d in range(3) if d != k]
            for sg in (-1, 1):
                pts = []
                for si, sj in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
                    s = np.zeros(3)
                    s[k], s[i], s[j] = sg, si, sj
                    pts.append(V(s, k))
                self.poly(pts, mat, A[k] * sg)
        if b <= 1e-6:
            return
        for m in range(3):
            i, j = [d for d in range(3) if d != m]
            for si in (-1, 1):
                for sj in (-1, 1):
                    s0, s1 = np.zeros(3), np.zeros(3)
                    s0[i] = s1[i] = si
                    s0[j] = s1[j] = sj
                    s0[m], s1[m] = -1, 1
                    self.poly([V(s0, i), V(s1, i), V(s1, j), V(s0, j)], mat, A[i] * si + A[j] * sj)
        for sx in (-1, 1):
            for sy in (-1, 1):
                for sz in (-1, 1):
                    s = np.array((sx, sy, sz), float)
                    self.poly([V(s, 0), V(s, 1), V(s, 2)], mat, s @ A)

    def box(self, center, size, mat, bevel=None):
        self.obox(center, np.eye(3), np.asarray(size, float) / 2, mat, bevel)

    def beam(self, a, b, w, h, mat, bevel=1.0):
        """Rechteckrohr von a nach b, Querschnitt w x h"""
        a, b = np.asarray(a, float), np.asarray(b, float)
        d = b - a
        L = np.linalg.norm(d)
        if L < 1e-6:
            return
        x = d / L
        up = np.array([0, 0, 1.0]) if abs(x[2]) < 0.95 else np.array([1.0, 0, 0])
        y = np.cross(up, x)
        y /= np.linalg.norm(y)
        z = np.cross(x, y)
        self.obox((a + b) / 2, (x, y, z), (L / 2, w / 2, h / 2), mat, bevel)

    def cyl(self, a, b, r, mat, seg=24, bevel=None, r2=None):
        """Rundkoerper von a nach b (Radius r, am Ende r2) mit Fasen und Deckeln"""
        a, b = np.asarray(a, float), np.asarray(b, float)
        d = b - a
        L = np.linalg.norm(d)
        if L < 1e-6 or r <= 0:
            return
        ax = d / L
        u = np.cross(ax, (1, 0, 0) if abs(ax[0]) < 0.8 else (0, 1, 0))
        u /= np.linalg.norm(u)
        w = np.cross(ax, u)
        t = np.arange(seg) * (2 * math.pi / seg)
        rad = np.cos(t)[:, None] * u + np.sin(t)[:, None] * w
        r2 = r if r2 is None else r2
        bv = min(r, r2) * 0.12 if bevel is None else bevel
        bv = max(0.0, min(bv, L * 0.3, min(r, r2) * 0.4))
        rings = [(a, r - bv), (a + ax * bv, r), (b - ax * bv, r2), (b, r2 - bv)] if bv > 0 else [(a, r), (b, r2)]
        side = (r - r2) / L
        V, N, F = [], [], []
        for k, (p, rr) in enumerate(rings):
            V.append(p + rad * rr)
            if bv > 0 and k == 0:
                N.append(rad - ax)
            elif bv > 0 and k == len(rings) - 1:
                N.append(rad + ax)
            else:
                N.append(rad + ax * side)
        V, N = np.vstack(V), np.vstack(N)
        for j in range(len(rings) - 1):
            for i in range(seg):
                q, s = j * seg + i, j * seg + (i + 1) % seg
                F += [(q, s, s + seg), (q, s + seg, q + seg)]
        self.add(V, N, F, mat)
        for p, rr, sg in ((rings[0][0], rings[0][1], -1), (rings[-1][0], rings[-1][1], 1)):
            pts = p + rad * rr
            self.add(np.vstack((pts, p)), np.tile(ax * sg, (seg + 1, 1)), [(seg, i, (i + 1) % seg) for i in range(seg)], mat)

    def bolt(self, p, r, h, mat="metal"):
        """Sechskantschraube mit Scheibe, stehend auf p"""
        p = np.asarray(p, float)
        self.cyl(p, p + (0, 0, 2), r * 1.5, mat, 16, 0.3)
        self.cyl(p + (0, 0, 2), p + (0, 0, 2 + h), r, mat, 6, 0.6)

    def wedge(self, base, dx, dy, h, t, mat):
        """Dreieckige Rippe (Knotenblech): Grundkante dx/dy in der Ebene, Hoehe h, Dicke t"""
        base = np.asarray(base, float)
        d = np.array([dx, dy, 0.0])
        x = d / np.linalg.norm(d)
        nrm = np.cross((0, 0, 1.0), x) * (t / 2)
        tri = [base, base + d, base + (0, 0, h)]
        for s in (-1, 1):
            self.poly([p + s * nrm for p in tri], mat, s * nrm)
        centroid = base + d / 3 + (0, 0, h / 3)
        for p0, p1 in ((tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0])):
            self.poly([p0 - nrm, p1 - nrm, p1 + nrm, p0 + nrm], mat, (p0 + p1) / 2 - centroid)

    def result(self):
        out = []
        for mat, (vs, ns, fs, _) in self.parts.items():
            n = np.vstack(ns)
            ln = np.linalg.norm(n, axis=1, keepdims=True)
            out.append((np.ascontiguousarray(np.vstack(vs), np.float32),
                        np.ascontiguousarray(n / np.where(ln > 0, ln, 1), np.float32),
                        np.ascontiguousarray(np.vstack(fs), np.uint32), mat))
        return out


def _grid(m, center, width, height, plane, pitch=50.0, wire=3.0):
    """Drahtgitter: plane 'xz' (Wand quer zu y) oder 'yz' (quer zu x)"""
    c = np.asarray(center, float)
    along = 0 if plane == "xz" else 1
    nx, nz = max(1, int(width // pitch)), max(1, int(height // pitch))
    if m.tris + (nx + nz + 2) * 12 > MAX_TRIS:      # vorab pruefen statt Tausende Draehte zu erzeugen
        raise _Budget()
    for u in np.linspace(-width / 2, width / 2, nx + 1):
        p = c.copy()
        p[along] += u
        m.box(p, (wire, wire, height), "mesh", 0)
    size = np.array([wire, wire, wire])
    size[along] = width
    for z in np.linspace(-height / 2, height / 2, nz + 1):
        m.box(c + (0, 0, z), size, "mesh", 0)


# ------------------------------------------------------------------ Foerdertechnik
def _conveyor(m, L, W, H, feet, roller):
    pw, ph = 40.0, min(110.0, H * 0.35)          # Seitenprofil Breite / Hoehe
    yf = W / 2 + pw / 2
    ztop = H + 6.0                                # Profillippe ueber dem Gurt
    zp = ztop - ph / 2
    for sy in (-1, 1):
        m.box((0, sy * yf, zp), (L, pw, ph), "frame", 2.0)
        for dz in (-ph * 0.25, ph * 0.15):        # Nuten aussen
            m.box((0, sy * (yf + pw / 2 + 0.4), zp + dz), (L - 30, 1.6, 7), "dark", 0)
        for sx in (-1, 1):                        # Endkappen
            m.box((sx * (L / 2 + 3), sy * yf, zp), (6, pw + 2, ph + 2), "dark", 1.0)
    if roller:
        r = min(25.0, H * 0.06)
        pitch = max(2.5 * r, 70.0)
        n = max(2, int((L - 2 * r - 30) // pitch) + 1)
        span = (n - 1) * pitch
        for x in np.linspace(-span / 2, span / 2, n):
            m.cyl((x, -W / 2, H - r), (x, W / 2, H - r), r, "metal", 20, 1.5)
            for sy in (-1, 1):                    # Achsstummel ins Profil
                m.cyl((x, sy * W / 2, H - r), (x, sy * (W / 2 + 8), H - r), r * 0.35, "dark", 8, 0.5)
        zc, xd = H - r, span / 2
    else:
        rb = min(30.0, H * 0.1, L * 0.1)          # Umlenkradius
        xe = L / 2 - rb - 8
        prof = []
        for t in np.linspace(-math.pi / 2, math.pi / 2, 10):
            prof.append((xe + rb * math.cos(t), H - rb + rb * math.sin(t), math.cos(t), math.sin(t)))
        for t in np.linspace(math.pi / 2, 3 * math.pi / 2, 10):
            prof.append((-xe + rb * math.cos(t), H - rb + rb * math.sin(t), math.cos(t), math.sin(t)))
        bw = W / 2 - 4
        V, N, F = [], [], []
        k = len(prof)
        for i in range(k):
            x, z, nx, nz = prof[i]
            V += [(x, -bw, z), (x, bw, z)]
            N += [(nx, 0, nz), (nx, 0, nz)]
        for i in range(k):
            j = (i + 1) % k
            if i in (9, 19):                      # gerade Trume folgen flach
                continue
            F += [(2 * i, 2 * j, 2 * j + 1), (2 * i, 2 * j + 1, 2 * i + 1)]
        m.add(V, N, F, "belt")
        for i, j, nz in ((9, 10, 1.0), (19, 0, -1.0)):   # Ober- und Untertrum
            a, b = prof[i], prof[j]
            m.poly([(a[0], -bw, a[1]), (b[0], -bw, b[1]), (b[0], bw, b[1]), (a[0], bw, a[1])], "belt", (0, 0, nz))
        for sy in (-1, 1):
            m.poly([(x, sy * bw, z) for x, z, _, _ in prof], "belt", (0, sy, 0))
        zc, xd = H - rb, xe
        for sx in (-1, 1):
            for sy in (-1, 1):                    # Trommelachsen
                m.cyl((sx * xd, sy * (yf + pw / 2), zc), (sx * xd, sy * (yf + pw / 2 + 10), zc), 11, "metal", 16, 1)
    # Getriebemotor auf der Antriebstrommel (Seite -y)
    k = max(0.55, min(1.0, W / 400.0, H / 400.0))
    yg = -(yf + pw / 2 + 45 * k)
    xg = min(xd, L / 2 - 60 * k)
    m.box((xg, yg, zc - 40 * k), (110 * k, 90 * k, 130 * k), "motor", 6 * k)
    mx0, zm = xg - 55 * k, zc - 45 * k
    m.cyl((mx0, yg, zm), (mx0 - 190 * k, yg, zm), 55 * k, "motor", 28, 4 * k)
    for i in range(6):                            # Kuehlrippen
        x = mx0 - 30 * k - i * 22 * k
        m.cyl((x, yg, zm), (x - 5 * k, yg, zm), 60 * k, "motor", 28, 0.8)
    m.cyl((mx0 - 190 * k, yg, zm), (mx0 - 215 * k, yg, zm), 50 * k, "dark", 28, 3 * k)   # Lueferhaube
    m.box((mx0 - 70 * k, yg, zm + 62 * k), (80 * k, 70 * k, 30 * k), "motor", 3 * k)      # Klemmkasten
    # Stuetzen
    n = int(max(0, min(20, feet)))
    if n:
        xs = [0.0] if n == 1 or L < 400 else list(np.linspace(-L / 2 + 120, L / 2 - 120, n))
        zl0, zl1 = 30.0, ztop - ph
        for x in xs:
            for sy in (-1, 1):
                y = sy * yf
                if zl1 > zl0 + 20:
                    m.box((x, y, (zl0 + zl1) / 2), (40, 40, zl1 - zl0), "frame", 1.5)
                m.cyl((x, y, 10), (x, y, zl0), 8, "metal", 12, 0.5)            # Gewindestange
                m.cyl((x, y, 0), (x, y, 10), 30, "rubber", 24, 2)               # Stellfuss
            if zl1 - zl0 > 150:
                zq = zl0 + (zl1 - zl0) * 0.3
                m.box((x, 0, zq), (30, 2 * yf - 40, 30), "frame", 1.5)
                m.beam((x, -yf + 20, zq + 20), (x, yf - 20, zl1 - 30), 25, 25, "frame")
        if len(xs) >= 2 and zl1 - zl0 > 150:
            zq = zl0 + (zl1 - zl0) * 0.3
            for sy in (-1, 1):
                m.box((0, sy * yf, zq), (xs[-1] - xs[0] - 40, 30, 30), "frame", 1.5)


def _fence(m, L, T, H):
    long_x = L >= T
    Ln = L if long_x else T
    panels = max(1, int(math.ceil((Ln - 60) / 1300.0)))
    xs = np.linspace(-Ln / 2 + 30, Ln / 2 - 30, panels + 1)
    P = (lambda x, y, z: (x, y, z)) if long_x else (lambda x, y, z: (y, x, z))
    S = (lambda a, b, c: (a, b, c)) if long_x else (lambda a, b, c: (b, a, c))
    for x in xs:
        m.box(P(x, 0, 10 + (H - 16) / 2), S(60, 60, H - 16), "paint", 2)            # Pfosten
        m.box(P(x, 0, H - 3), S(64, 64, 6), "dark", 1)                               # Kappe
        m.box(P(x, 0, 5), S(160, 160, 10), "metal", 1.5)                            # Fussplatte
        for dx in (-55, 55):
            for dy in (-55, 55):
                m.bolt(P(x + dx, dy, 10), 6, 6, "dark")
    z0, z1 = 150.0, H - 40.0
    for a, b in zip(xs[:-1], xs[1:]):
        x0, x1 = a + 45, b - 45
        if x1 - x0 < 60:
            continue
        mid, w = (x0 + x1) / 2, x1 - x0
        for z in (z0, z1):
            m.box(P(mid, 0, z), S(w, 25, 25), "dark", 1)
        for x in (x0, x1):
            m.box(P(x, 0, (z0 + z1) / 2), S(25, 25, z1 - z0), "dark", 1)
        _grid(m, P(mid, 0, (z0 + z1) / 2), w - 25, z1 - z0 - 25, "xz" if long_x else "yz")
    if H > 1200:                                  # Warnschild am ersten Feld
        mid = (xs[0] + xs[1]) / 2
        m.box(P(mid, 16, H * 0.62), S(220, 2, 160), "warn", 0.5)
        m.box(P(mid, 17.5, H * 0.62), S(150, 1, 18), "dark", 0)


def _sensor(m, L, W, H, color=False):
    """Lichtschranke / Farbsensor: Sender rechts (+y), Reflektor links (-y), Strahl auf H/2"""
    zc = H / 2
    if color:
        hx, hy, hz = max(L * 0.9, 32.0), 40.0, min(H * 0.55, 80.0)
    else:
        hx, hy, hz = max(L * 0.8, 20.0), 28.0, min(H * 0.45, 55.0)
    y = W / 2 + hy / 2
    m.box((0, y, zc), (hx, hy, hz), "dark" if color else "paint", 3)
    m.box((0, W / 2 - 0.5, zc), (hx * 0.86, 1.5, hz * 0.8), "dark", 0)               # Frontrahmen
    m.cyl((0, W / 2 - 0.5, zc), (0, W / 2 - 2.0, zc), min(hx, hz) * 0.28, "glass", 24, 0.4)
    if color:
        m.cyl((0, W / 2 - 0.2, zc), (0, W / 2 - 1.2, zc), min(hx, hz) * 0.36, "metal", 24, 0.3)
    else:
        m.box((hx * 0.22, y, zc + hz / 2 + 1.5), (6, 6, 3), "warn", 0.5)              # Anzeige-LEDs
        m.box((-hx * 0.22, y, zc + hz / 2 + 1.5), (6, 6, 3), "glass", 0.5)
    m.cyl((0, y, zc - hz / 2), (0, y, zc - hz / 2 - 14), 6, "metal", 6, 0.5)          # M12-Stecker
    m.cyl((0, y, zc - hz / 2 - 14), (0, y, zc - hz / 2 - 70), 3.5, "dark", 10, 0)     # Kabel
    for s, yy in ((1, y + hy / 2), (-1, -W / 2 - 12)):                                # Haltewinkel
        m.box((0, yy + s * 2, zc - 10), (hx + 10, 4, hz + 40), "metal", 0.8)
        m.box((0, yy + s * 14, zc - hz / 2 - 28), (hx + 10, 28, 4), "metal", 0.8)
    m.box((0, -W / 2 - 6, zc), (max(hx, 30), 10, max(hz, 40)), "dark", 1.5)          # Reflektor
    m.box((0, -W / 2 - 0.5, zc), (max(hx, 30) * 0.85, 1, max(hz, 40) * 0.85), "reflector", 0)


def led_point(kind, size):
    """Lage der Status-LED (lokal), die die Ansicht in der erkannten Farbe leuchten laesst"""
    L, W, H = size
    if kind == "color_sensor":
        hx, hz = max(L * 0.9, 32.0), min(H * 0.55, 80.0)
        return (hx * 0.25, W / 2 + 20, H / 2 + hz / 2 + 4)
    return (0.0, W / 2, H)


def _lamp(m, L, W, H):
    d = min(L, W)
    r = d * 0.38
    m.cyl((0, 0, 0), (0, 0, 12), d * 0.48, "dark", 32, 2)
    for a in np.arange(4) * (math.pi / 2) + math.pi / 4:
        m.bolt((math.cos(a) * d * 0.36, math.sin(a) * d * 0.36, 12), 3.5, 4)
    m.cyl((0, 0, 12), (0, 0, 22), d * 0.14, "metal", 24, 1)
    m.cyl((0, 0, 22), (0, 0, H * 0.3), d * 0.08, "metal", 20, 1)
    m.cyl((0, 0, H * 0.3), (0, 0, H * 0.33), r * 1.02, "metal", 32, 1)
    m.cyl((0, 0, H * 0.33), (0, 0, H * 0.45), r, "dark", 32, 2)


def _spawner(m, L, W, H):
    """Zufuehrtrichter: oben Einfuelloeffnung L x W, unten Auslauf"""
    t = max(1.5, min(L, W) * 0.03)
    zb, zt = H * 0.4, H
    bx, by = L * 0.22, W * 0.22
    for ax in (0, 1):
        for sg in (-1, 1):
            ha_t, hb_t = (L / 2, W / 2) if ax == 0 else (W / 2, L / 2)
            ha_b, hb_b = (bx, by) if ax == 0 else (by, bx)

            def pt(u, z, ha, hb):
                p = [0.0, 0.0, z]
                p[ax] = sg * ha
                p[1 - ax] = u * hb
                return np.array(p)

            outer = [pt(-1, zb, ha_b, hb_b), pt(1, zb, ha_b, hb_b), pt(1, zt, ha_t, hb_t), pt(-1, zt, ha_t, hb_t)]
            inner = [p - np.eye(3)[ax] * sg * t for p in outer]
            hint = np.eye(3)[ax] * sg
            m.poly(outer, "metal", hint)
            m.poly(inner, "metal", -hint)
    rw = max(3.0, min(L, W) * 0.07)                                                     # Rand (offen)
    for sy in (-1, 1):
        m.box((0, sy * (W / 2 - rw / 2), zt - 3), (L, rw, 6), "paint", 1)
    for sx in (-1, 1):
        m.box((sx * (L / 2 - rw / 2), 0, zt - 3), (rw, W - 2 * rw, 6), "paint", 1)
    m.box((0, 0, (H * 0.08 + zb) / 2), (bx * 2, by * 2, zb - H * 0.08), "metal", 1)   # Auslauf
    m.box((0, 0, H * 0.06), (bx * 2.2, by * 2.2, H * 0.04), "dark", 0.5)


def _sink(m, L, W, H):
    t = max(4.0, min(L, W) * 0.03)
    for x in (-L / 2 + 25, L / 2 - 25):
        for y in (-W / 2 + 25, W / 2 - 25):
            m.box((x, y, 10), (40, 40, 20), "rubber", 2)
    m.box((0, 0, 20 + t / 2), (L, W, t), "paint", 1.5)
    for sy in (-1, 1):
        m.box((0, sy * (W / 2 - t / 2), (20 + H) / 2), (L, t, H - 20), "paint", 1)
    for sx in (-1, 1):
        m.box((sx * (L / 2 - t / 2), 0, (20 + H) / 2), (t, W - 2 * t, H - 20), "paint", 1)
    for sy in (-1, 1):
        m.box((0, sy * (W / 2 - 8), H - 8), (L, 16, 16), "metal", 2)
    for sx in (-1, 1):
        m.box((sx * (L / 2 - 8), 0, H - 8), (16, W - 32, 16), "metal", 2)
    if H > 150:
        m.box((0, -W / 2 - 0.5, H * 0.55), (min(L * 0.5, 160), 1, min(H * 0.25, 60)), "warn", 0)


# ------------------------------------------------------------------ Zellenbau
def _pallet(m, L, W, H):
    fx, fy, fz = L / 1200.0, W / 800.0, H / 144.0
    t, bh = 22 * fz, 78 * fz
    widths = [145, 100, 145, 100, 145]
    gap = (800 - sum(widths)) / 4
    y = -400.0
    for i, w in enumerate(widths):                 # Deckbretter laengs
        m.box((0, (y + w / 2) * fy, H - t / 2), (L, w * fy, t), "wood" if i % 2 == 0 else "wood2", 2)
        y += w + gap
    xs = (-L / 2 + 72.5 * fx, 0, L / 2 - 72.5 * fx)
    ys = (-W / 2 + 50 * fy, 0, W / 2 - 50 * fy)
    for x in xs:                                   # Querbretter und Kloetze
        m.box((x, 0, t + bh + t / 2), (145 * fx, W, t), "wood2", 2)
        for k, yy in enumerate(ys):
            m.box((x, yy, t + bh / 2), (145 * fx, (145 if k == 1 else 100) * fy, bh), "wood", 2.5)
    for k, yy in enumerate(ys):                    # Bodenbretter
        m.box((0, yy, t / 2), (L, (145 if k == 1 else 100) * fy, t), "wood2" if k == 1 else "wood", 2)


def _cabinet(m, L, W, H):
    pl = min(100.0, H * 0.06)
    m.box((0, 5, pl / 2), (L - 20, W - 30, pl), "dark", 2)
    m.box((0, 12, (pl + H - 20) / 2), (L, W - 24, H - 20 - pl), "paint", 3)
    m.box((0, 0, H - 10), (L, W, 20), "paint", 3)
    dw = (L - 12) / 2
    zd0, zd1 = pl + 10, H - 30
    for s in (-1, 1):
        cx = s * (dw / 2 + 3)
        m.box((cx, -W / 2 + 13, (zd0 + zd1) / 2), (dw - 4, 26, zd1 - zd0), "paint", 2.5)
        m.box((s * 30, -W / 2 - 6, H * 0.5), (18, 14, min(200, H * 0.15)), "metal", 4)      # Griff
        m.cyl((s * 30, -W / 2, H * 0.62), (s * 30, -W / 2 - 4, H * 0.62), 9, "metal", 16, 1)  # Schloss
        for i in range(7):                                                                   # Lueftung
            z = zd0 + 70 + i * 22
            if z < zd1 - 20:
                m.box((cx, -W / 2 - 0.8, z), (dw * 0.55, 2, 10), "dark", 0)
    sx = dw / 2 + 3
    m.box((sx, -W / 2 - 1.5, H * 0.72), (90, 3, 90), "warn", 1)                             # Hauptschalter
    m.cyl((sx, -W / 2 - 3, H * 0.72), (sx, -W / 2 - 18, H * 0.72), 26, "handle", 24, 2)
    m.box((sx, -W / 2 - 22, H * 0.72), (60, 10, 14), "handle", 2)
    m.box((L / 2 + 0.5, 0, H * 0.3), (1, W * 0.45, H * 0.12), "dark", 0)                   # Luefter Seite


def _table(m, L, W, H):
    top = min(40.0, H * 0.06)
    m.box((0, 0, H - top / 2), (L, W, top), "wood", 3)
    ins = 40.0
    for sx in (-1, 1):
        for sy in (-1, 1):
            x, y = sx * (L / 2 - ins - 30), sy * (W / 2 - ins - 30)
            m.box((x, y, (40 + H - top) / 2), (60, 60, H - top - 40), "paint", 2)
            m.cyl((x, y, 12), (x, y, 40), 10, "metal", 12, 0.5)
            m.cyl((x, y, 0), (x, y, 12), 28, "rubber", 20, 2)
    za = H - top - 40
    m.box((0, 0, za), (L - 2 * ins - 60, W - 2 * ins - 60, 80), "paint", 2)               # Zarge
    if H > 500:
        zs = 180.0
        for sy in (-1, 1):
            m.box((0, sy * (W / 2 - ins - 30), zs), (L - 2 * ins - 60, 40, 40), "paint", 1.5)
        m.box((0, 0, zs + 29), (L - 2 * ins - 120, W - 2 * ins - 60, 18), "wood2", 2)     # Ablage


def _gitterbox(m, L, W, H):
    for sx in (-1, 1):
        for sy in (-1, 1):
            m.box((sx * (L / 2 - 60), sy * (W / 2 - 60), 50), (120, 120, 100), "paint", 2)
    m.box((0, 0, 105), (L, W, 10), "metal", 1.5)
    for sx in (-1, 1):
        for sy in (-1, 1):
            m.box((sx * (L / 2 - 20), sy * (W / 2 - 20), (110 + H) / 2), (40, 40, H - 110), "paint", 1.5)
    for z in (130.0, H - 20):
        for sy in (-1, 1):
            m.box((0, sy * (W / 2 - 15), z), (L - 80, 30, 40), "paint", 1.5)
        for sx in (-1, 1):
            m.box((sx * (L / 2 - 15), 0, z), (30, W - 80, 40), "paint", 1.5)
    zc, hh = (150 + H - 40) / 2, H - 40 - 150
    for sy in (-1, 1):
        _grid(m, (0, sy * (W / 2 - 15), zc), L - 80, hh, "xz")
    for sx in (-1, 1):
        _grid(m, (sx * (L / 2 - 15), 0, zc), W - 80, hh, "yz")
    m.box((0, -W / 2 + 15, (H + 130) / 2), (L - 80, 30, 30), "paint", 1)                 # Klappe


def _shelf(m, L, W, H):
    uw, ud = 90.0, 70.0
    xs, ys = (-L / 2 + uw / 2, L / 2 - uw / 2), (-W / 2 + ud / 2, W / 2 - ud / 2)
    for x in xs:
        for y in ys:
            m.box((x, y, (8 + H) / 2), (uw, ud, H - 8), "paint", 2)
            m.box((x, y, 4), (uw + 20, ud + 20, 8), "metal", 1)
            if y < 0:                                                                    # Lochung vorne
                for z in np.arange(120, H - 60, 50):
                    m.box((x, y - ud / 2 - 0.4, z), (14, 1, 24), "dark", 0)
        zb = np.linspace(200, H - 200, max(3, int(round(H / 400))))
        for a, b in zip(zb[:-1], zb[1:]):                                                # Diagonalen seitlich
            m.beam((x, ys[0] + ud / 2, a), (x, ys[1] - ud / 2, b), 25, 25, "paint", 1)
    for z in np.linspace(150, H - 100, max(2, int(round(H / 550)) + 1)):
        for y in ys:
            m.box((0, y, z), (L - 2 * uw, 50, 100), "beam", 2)
        m.box((0, 0, z + 62), (L - 2 * uw, W - 20, 24), "metal", 2)


def _pedestal(m, L, W, H):
    t = min(30.0, H * 0.1)
    m.box((0, 0, t / 2), (L, W, t), "metal", 2)
    cw, cd = L * 0.6, W * 0.6
    m.box((0, 0, H / 2), (cw, cd, H - 2 * t), "paint", 3)
    m.box((0, 0, H - t / 2), (L * 0.9, W * 0.9, t), "metal", 2)
    gh = min(H * 0.35, 150)
    for d in ((1, 0), (-1, 0), (0, 1), (0, -1)):                                          # Knotenbleche
        base = np.array([d[0] * cw / 2, d[1] * cd / 2, t])
        reach = (L / 2 - cw / 2 - 10) if d[0] else (W / 2 - cd / 2 - 10)
        if reach > 10:
            m.wedge(base, d[0] * reach, d[1] * reach, gh, 12, "paint")
    for sx in (-1, 1):
        for sy in (-1, 1):
            m.bolt((sx * (L / 2 - 40), sy * (W / 2 - 40), t), 10, 12)
            m.bolt((sx * L * 0.3, sy * W * 0.3, H), 7, 8, "dark")


def _carton(m, L, W, H):
    m.box((0, 0, H / 2), (L, W, H), "cardboard", min(4.0, min(L, W, H) * 0.06))
    tw = min(50.0, W * 0.2)
    m.box((0, 0, H + 0.3), (L * 0.999, tw, 0.8), "tape", 0)
    for sx in (-1, 1):
        m.box((sx * (L / 2 + 0.3), 0, H - min(80, H * 0.4) / 2), (0.8, tw, min(80, H * 0.4)), "tape", 0)
    if L > 120 and H > 80:
        m.box((L * 0.18, -W / 2 - 0.3, H * 0.45), (min(L * 0.3, 110), 0.8, min(H * 0.3, 70)), "label", 0)


def _fixture(m, L, W, H):
    t = min(25.0, H * 0.2)
    m.box((0, 0, t / 2), (L, W, t), "metal", 2)
    for s in (-1, 1):
        m.box((s * L * 0.3, 0, t + (H * 0.55 - t) / 2), (L * 0.18, W * 0.65, H * 0.55 - t), "paint", 2)
        m.cyl((s * L * 0.3, W * 0.2, H * 0.55), (s * L * 0.3, W * 0.2, H * 0.55 + 15), 6, "metal", 16, 1)
    for s in (-1, 1):                                                                     # Kniehebelspanner
        x = s * L * 0.3
        m.box((x, -W * 0.4, t + 15), (40, 40, 30), "dark", 2)
        m.beam((x, -W * 0.4, t + 30), (x, -W * 0.05, H * 0.85), 14, 14, "dark")
        m.cyl((x, -W * 0.05, H * 0.85), (x, -W * 0.05, H * 0.85 - 18), 8, "rubber", 12, 1)
        m.cyl((x, -W * 0.4, t + 30), (x, -W * 0.46, H * 0.95), 9, "handle", 16, 1)


def _column(m, D, H):
    m.box((0, 0, 12.5), (D, D, 25), "metal", 2)
    for sx in (-1, 1):
        for sy in (-1, 1):
            m.bolt((sx * D * 0.38, sy * D * 0.38, 25), max(4, D * 0.03), 10)
    r = D * 0.4
    m.cyl((0, 0, 25), (0, 0, H - 20), r, "paint", 36, 2)
    z = 25.0
    for i in range(8):                                                                    # Warnringe
        if z + 50 > H * 0.5:
            break
        m.cyl((0, 0, z), (0, 0, z + 50), r + 1.5, "warn" if i % 2 == 0 else "dark", 36, 0)
        z += 50
    m.cyl((0, 0, H - 20), (0, 0, H), r * 1.05, "metal", 36, 2)


# ------------------------------------------------------------------ Einstieg
BOX_STYLES = {"pallet": (_pallet, 40), "cabinet": (_cabinet, 200), "table": (_table, 200), "gitterbox": (_gitterbox, 300),
              "shelf": (_shelf, 300), "pedestal": (_pedestal, 100), "carton": (_carton, 20), "fixture": (_fixture, 40)}


def build(kind, style, size, **p):
    try:
        L, W, H = (float(s) for s in size)
    except (TypeError, ValueError):
        return []
    if not all(math.isfinite(s) and 0 < s <= MAX_SIZE for s in (L, W, H)):
        return []
    try:
        return _build(kind, style, L, W, H, p)
    except _Budget:
        return []


def _build(kind, style, L, W, H, p):
    m = _Mesh()
    style = style or ""
    if kind == "conveyor":
        if L < 200 or W < 60 or H < 150:
            return []
        try:
            feet = int(p.get("feet", 2))
        except (TypeError, ValueError):
            feet = 2
        _conveyor(m, L, W, H, feet, bool(p.get("roller")) or style == "roller")
    elif kind == "fence":
        if max(L, W) < 300 or H < 500:
            return []
        _fence(m, L, W, H)
    elif kind in ("sensor", "color_sensor"):
        if H < 20 or W < 20:
            return []
        _sensor(m, L, W, H, kind == "color_sensor")
    elif kind == "lamp":
        _lamp(m, L, W, H)
    elif kind == "spawner":
        _spawner(m, L, W, H)
    elif kind == "sink":
        if min(L, W) < 60 or H < 40:
            return []
        _sink(m, L, W, H)
    elif kind == "cylinder" and style == "column":
        if H < 100 or min(L, W) < 40:
            return []
        _column(m, min(L, W), H)
    elif kind in ("box", "workpiece") and style in BOX_STYLES:
        fn, minimum = BOX_STYLES[style]
        if min(L, W, H) < minimum:
            return []
        fn(m, L, W, H)
    else:
        return []
    return m.result()
