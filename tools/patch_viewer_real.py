"""Realistische 3D-Darstellung: helle Halle, Licht, Schatten, Kantenglaettung, detailgetreue Foerdertechnik."""
import os
B = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "ximaj_robosim")


def patch(fn, pairs, count_all=()):
    p = os.path.join(B, fn)
    m = open(p, encoding="utf8").read()
    for a, b in pairs:
        if a not in m:
            raise SystemExit(f"{fn}: NICHT GEFUNDEN:\n{a[:300]}")
        m = m.replace(a, b, -1 if a in count_all else 1)
    open(p, "w", encoding="utf8").write(m)


V = "viewer.py"
# 1) alle Farbsetzungen ueber _col (fuer Schattendurchlauf)
p = os.path.join(B, V)
src = open(p, encoding="utf8").read().replace("glColor4f(", "self._col(")
open(p, "w", encoding="utf8").write(src)

patch(V, [
    ('''        self._quad = None

    # ------------------------------------------------ GL''', '''        self._quad = None
        self.light_mode = True          # helle Hallenansicht
        self.shadows = True
        self._shadow = False

    def _col(self, *c):
        if self._shadow:
            glColor4f(0.04, 0.05, 0.07, 0.22)
        else:
            glColor4f(*(tuple(c) + (1.0,) * (4 - len(c))))

    # ------------------------------------------------ GL'''),
    ('''        glEnable(GL_LIGHT0)
        glLightfv(GL_LIGHT0, GL_AMBIENT, (0.35, 0.35, 0.4, 1))
        glLightfv(GL_LIGHT0, GL_DIFFUSE, (0.9, 0.9, 0.9, 1))''', '''        glEnable(GL_LIGHT0)
        glEnable(GL_LIGHT1)
        glLightfv(GL_LIGHT0, GL_AMBIENT, (0.28, 0.29, 0.31, 1))
        glLightfv(GL_LIGHT0, GL_DIFFUSE, (0.82, 0.81, 0.78, 1))
        glLightfv(GL_LIGHT0, GL_SPECULAR, (0.55, 0.55, 0.55, 1))
        glLightfv(GL_LIGHT1, GL_AMBIENT, (0.0, 0.0, 0.0, 1))
        glLightfv(GL_LIGHT1, GL_DIFFUSE, (0.32, 0.34, 0.38, 1))
        glLightfv(GL_LIGHT1, GL_SPECULAR, (0.0, 0.0, 0.0, 1))
        glLightModeli(GL_LIGHT_MODEL_TWO_SIDE, GL_TRUE)
        glMaterialfv(GL_FRONT_AND_BACK, GL_SPECULAR, (0.35, 0.35, 0.35, 1))
        glMaterialf(GL_FRONT_AND_BACK, GL_SHININESS, 42.0)
        try:
            glEnable(GL_MULTISAMPLE)
        except Exception:
            pass'''),
    ('''        glBegin(GL_QUADS)
        glColor3f(*hexrgb(theme.BRAND["viewport_bottom"]))
        glVertex2f(0, 0)
        glVertex2f(1, 0)
        glColor3f(*hexrgb(theme.BRAND["viewport_top"]))
        glVertex2f(1, 1)
        glVertex2f(0, 1)
        glEnd()''', '''        bot, top = ((0.80, 0.82, 0.85), (0.93, 0.94, 0.96)) if self.light_mode else \\
            (hexrgb(theme.BRAND["viewport_bottom"]), hexrgb(theme.BRAND["viewport_top"]))
        glBegin(GL_QUADS)
        glColor3f(*bot)
        glVertex2f(0, 0)
        glVertex2f(1, 0)
        glColor3f(*top)
        glVertex2f(1, 1)
        glVertex2f(0, 1)
        glEnd()'''),
    ('''        glLightfv(GL_LIGHT0, GL_POSITION, (*(eye + np.array([500, 500, 1500])), 1))''',
     '''        # Hauptlicht als "Hallenlicht" schraeg von oben (gerichtet), Fuelllicht von der Kamera
        self._sun = np.array([0.35, 0.25, 1.0])
        self._sun /= np.linalg.norm(self._sun)
        glLightfv(GL_LIGHT0, GL_POSITION, (*self._sun, 0.0))
        d = (eye - self.center)
        d = d / (np.linalg.norm(d) or 1)
        glLightfv(GL_LIGHT1, GL_POSITION, (*d, 0.0))'''),
    ('''        glEnable(GL_LIGHTING)
        self._grid()
        self._draw_robot()
        self._draw_scene()
        glDisable(GL_LIGHTING)''', '''        glEnable(GL_LIGHTING)
        self._grid()
        if self.shadows:
            self._shadow_pass()
        self._draw_robot()
        self._draw_scene()
        glDisable(GL_LIGHTING)'''),
    ('''    def _grid(self):
        glDisable(GL_LIGHTING)
        self._col(*hexrgb(theme.BRAND["grid"]), 0.9)
        glLineWidth(1)
        glBegin(GL_LINES)
        n, step = 20, 250
        for i in range(-n, n + 1):
            glVertex3f(i * step, -n * step, 0)
            glVertex3f(i * step, n * step, 0)
            glVertex3f(-n * step, i * step, 0)
            glVertex3f(n * step, i * step, 0)
        glEnd()
        glEnable(GL_LIGHTING)''', '''    def _grid(self):
        glDisable(GL_LIGHTING)
        ext = 20000
        if self.light_mode:
            # Hallenboden
            glEnable(GL_POLYGON_OFFSET_FILL)
            glPolygonOffset(2.0, 2.0)
            glBegin(GL_QUADS)
            glColor4f(0.86, 0.87, 0.88, 1)
            for x, y in ((-ext, -ext), (ext, -ext), (ext, ext), (-ext, ext)):
                glVertex3f(x, y, 0)
            glEnd()
            glDisable(GL_POLYGON_OFFSET_FILL)
            fine, major = (0.80, 0.81, 0.83, 1), (0.70, 0.72, 0.75, 1)
        else:
            fine = major = (*hexrgb(theme.BRAND["grid"]), 0.9)
        glLineWidth(1)
        glBegin(GL_LINES)
        step = 500
        n = int(ext / step)
        for i in range(-n, n + 1):
            glColor4f(*(major if i % 2 == 0 else fine))
            glVertex3f(i * step, -ext, 0.2)
            glVertex3f(i * step, ext, 0.2)
            glVertex3f(-ext, i * step, 0.2)
            glVertex3f(ext, i * step, 0.2)
        glEnd()
        glEnable(GL_LIGHTING)

    def _shadow_pass(self):
        """Weiche Bodenschatten: Projektion der Geometrie entlang des Hallenlichts auf z=0 (Stencil gegen Doppelungen)."""
        L = self._sun
        h = 0.6
        # Schattenmatrix fuer gerichtetes Licht auf Ebene z = h
        S = np.array([[L[2], 0, -L[0], L[0] * h],
                      [0, L[2], -L[1], L[1] * h],
                      [0, 0, 0, h * L[2]],
                      [0, 0, 0, L[2]]], dtype=float)
        glDisable(GL_LIGHTING)
        glDepthMask(GL_FALSE)
        glEnable(GL_STENCIL_TEST)
        glClear(GL_STENCIL_BUFFER_BIT)
        glStencilFunc(GL_EQUAL, 0, 0xFF)
        glStencilOp(GL_KEEP, GL_KEEP, GL_INCR)
        glPushMatrix()
        glMultMatrixf(np.ascontiguousarray(S.T, dtype=np.float32))
        self._shadow = True
        try:
            self._draw_robot()
            self._draw_scene()
        finally:
            self._shadow = False
            glPopMatrix()
            glDisable(GL_STENCIL_TEST)
            glDepthMask(GL_TRUE)
            glEnable(GL_LIGHTING)'''),
    # Drahtgitter nicht im Schatten
    ('''        if wire:
            glDisable(GL_LIGHTING)''', '''        if wire and self._shadow:
            glPopMatrix()
            return
        if wire:
            glDisable(GL_LIGHTING)'''),
    # Szene: Kanten im hellen Modus, Foerderer detailliert, Meshes schnell
    ('''                else:
                    self._box(M, o.size, c, 1.0)
            elif o.kind == "cylinder":''', '''                else:
                    self._box(M, o.size, c, 1.0)
                    if self.light_mode and not self._shadow:
                        self._box(M, o.size, (0.15, 0.17, 0.2), 1.0, wire=True)
            elif o.kind == "cylinder":'''),
    ('''            elif o.kind == "conveyor":
                self._box(M, o.size, c, 1.0)
                # Bandstreifen als Bewegungsanzeige
                glDisable(GL_LIGHTING)
                self._col(0.1, 0.12, 0.16, 1)
                glPushMatrix()
                glMultMatrixf(np.ascontiguousarray(M.T, dtype=np.float32))
                off = (self.sim.t * o.speed) % 100 if (o.io == 0 or sim.io.get_out(int(o.io))) else 0
                glBegin(GL_QUADS)
                x = -o.size[0] / 2 + off
                while x < o.size[0] / 2:
                    x1 = min(x + 20, o.size[0] / 2)
                    glVertex3f(x, -o.size[1] / 2, o.size[2] + 0.5)
                    glVertex3f(x1, -o.size[1] / 2, o.size[2] + 0.5)
                    glVertex3f(x1, o.size[1] / 2, o.size[2] + 0.5)
                    glVertex3f(x, o.size[1] / 2, o.size[2] + 0.5)
                    x += 100
                glEnd()
                glPopMatrix()
                glEnable(GL_LIGHTING)
            elif o.kind in ("sensor", "spawner", "zone"):''', '''            elif o.kind == "conveyor":
                self._draw_conveyor(o, M)
            elif o.kind == "conveyor_arc":
                self._draw_conveyor_arc(o, M)
            elif o.kind in ("sensor", "spawner", "zone"):
                if self._shadow:
                    continue'''),
    ('''            elif o.kind == "mesh" and o.mesh is not None:
                v, f = o.mesh
                self._col(*c, 1)
                glPushMatrix()
                glMultMatrixf(np.ascontiguousarray(M.T, dtype=np.float32))
                glBegin(GL_TRIANGLES)
                for tri in f:
                    a, b, cc2 = v[tri[0]], v[tri[1]], v[tri[2]]
                    n = np.cross(b - a, cc2 - a)
                    nn = np.linalg.norm(n)
                    glNormal3f(*(n / nn if nn > 0 else (0, 0, 1)))
                    glVertex3f(*a)
                    glVertex3f(*b)
                    glVertex3f(*cc2)
                glEnd()
                glPopMatrix()
            if o is self.selected:''', '''            elif o.kind == "mesh" and o.mesh is not None:
                self._col(*c, 1)
                glPushMatrix()
                glMultMatrixf(np.ascontiguousarray(M.T, dtype=np.float32))
                self._mesh_arrays(o)
                glPopMatrix()
            if o is self.selected and not self._shadow:'''),
    ('''    def _draw_trail(self):''', '''    # ------------------------------------------------ Foerdertechnik (detailgetreu)
    def _draw_conveyor(self, o, M):
        L, W, H = o.size
        belt = hexrgb(o.belt_color)
        frame = hexrgb(o.frame_color)
        dark = (0.42, 0.45, 0.5)
        running = (o.io == 0) or self.sim.io.get_out(int(o.io))
        prof = 36.0
        # Gurt mit gerundeten Enden
        self._lbox(M, (0, 0, H - 8), (L, W, 16), belt)
        for sx in (-1, 1):
            self._lcyl(M, (sx * L / 2, -W / 2, H - 8), (sx * L / 2, W / 2, H - 8), 8, (*belt, 1))
        # Seitenprofile (Aluminium) mit Lippe ueber dem Gurt
        for sy in (-1, 1):
            self._lbox(M, (0, sy * (W / 2 + prof / 2), H - 52), (L + 20, prof, 114), frame)
            self._lbox(M, (0, sy * (W / 2 + prof / 2), H + 2), (L + 20, prof + 4, 6), (0.86, 0.88, 0.9))
        # Umlenk-/Antriebstrommeln
        for sx in (-1, 1):
            self._lcyl(M, (sx * (L / 2 - 30), -W / 2, H - 50), (sx * (L / 2 - 30), W / 2, H - 50), 38, (*dark, 1), True)
        # Antriebsmotor
        self._lcyl(M, (L / 2 - 110, -(W / 2 + prof), H - 95), (L / 2 - 110, -(W / 2 + prof + 120), H - 95), 52,
                   (0.29, 0.33, 0.4, 1), True)
        self._lbox(M, (L / 2 - 110, -(W / 2 + prof + 40), H - 160), (90, 70, 60), (0.29, 0.33, 0.4))
        # Fuesse mit Querstrebe und Stellfuss
        n = max(2, int(o.feet or 2))
        legh = max(H - 110, 10)
        for x in np.linspace(-L / 2 + 90, L / 2 - 90, n):
            for sy in (-1, 1):
                y = sy * (W / 2 + prof / 2)
                self._lbox(M, (x, y, 12 + legh / 2), (40, 40, legh), frame)
                self._lcyl(M, (x, y, 0), (x, y, 12), 32, (0.33, 0.35, 0.38, 1), True)
            self._lbox(M, (x, 0, H * 0.32), (36, W + prof * 2, 28), frame)
        # Gurtmarkierungen (laufen mit)
        if not self._shadow:
            glDisable(GL_LIGHTING)
            mark = tuple(max(0.0, c * 0.82) for c in belt)
            off = (self.sim.t * o.speed) % 300 if running else 0.0
            glPushMatrix()
            glMultMatrixf(np.ascontiguousarray(M.T, dtype=np.float32))
            self._col(*mark, 1)
            glBegin(GL_QUADS)
            x = -L / 2 + off
            while x < L / 2:
                x1 = min(x + 12, L / 2)
                glVertex3f(x, -W / 2, H + 0.6)
                glVertex3f(x1, -W / 2, H + 0.6)
                glVertex3f(x1, W / 2, H + 0.6)
                glVertex3f(x, W / 2, H + 0.6)
                x += 300
            glEnd()
            glPopMatrix()
            glEnable(GL_LIGHTING)

    def _arc_pt(self, o, r, th_deg, z):
        c = o.arc_center()
        t = math.radians(th_deg)
        if o.turn_right:
            return (c[0] + r * math.sin(t), c[1] + r * math.cos(t), z)
        return (c[0] + r * math.sin(t), c[1] - r * math.cos(t), z)

    def _arc_strip(self, o, r0, r1, z0, z1, a0, a1, color, n):
        """Flaeche zwischen zwei Radien (z0==z1: waagrecht) oder Wand bei r0==r1 (z0..z1)"""
        self._col(*color, 1)
        glBegin(GL_QUAD_STRIP)
        for i in range(n + 1):
            th = a0 + (a1 - a0) * i / n
            if abs(r0 - r1) < 1e-6:
                p = self._arc_pt(o, r0, th, 0)
                c = o.arc_center()
                nx, ny = p[0] - c[0], p[1] - c[1]
                ln = math.hypot(nx, ny) or 1
                glNormal3f(nx / ln, ny / ln, 0)
                glVertex3f(p[0], p[1], z0)
                glVertex3f(p[0], p[1], z1)
            else:
                glNormal3f(0, 0, 1)
                glVertex3f(*self._arc_pt(o, r0, th, z0))
                glVertex3f(*self._arc_pt(o, r1, th, z1))
        glEnd()

    def _draw_conveyor_arc(self, o, M):
        R, W, H, A = o.radius, o.size[1], o.size[2], o.angle
        belt = hexrgb(o.belt_color)
        frame = hexrgb(o.frame_color)
        prof = 36.0
        n = max(12, int(A / 4))
        ri, ro = R - W / 2, R + W / 2
        glPushMatrix()
        glMultMatrixf(np.ascontiguousarray(M.T, dtype=np.float32))
        # Gurt oben + Stirnseiten
        self._arc_strip(o, ri, ro, H, H, 0, A, belt, n)
        self._arc_strip(o, ri, ri, H - 16, H, 0, A, belt, n)
        self._arc_strip(o, ro, ro, H - 16, H, 0, A, belt, n)
        # Seitenprofile innen/aussen: Innen-, Aussenwand und Deckel
        for r_a, r_b in ((ri - prof, ri), (ro, ro + prof)):
            self._arc_strip(o, r_a, r_a, H - 110, H + 5, 0, A, frame, n)
            self._arc_strip(o, r_b, r_b, H - 110, H + 5, 0, A, frame, n)
            self._arc_strip(o, r_a, r_b, H + 5, H + 5, 0, A, (0.86, 0.88, 0.9), n)
            self._arc_strip(o, r_a, r_b, H - 110, H - 110, 0, A, frame, n)
        glPopMatrix()
        # Fuesse entlang des Bogens
        k = max(2, int(o.feet or 3))
        legh = max(H - 110, 10)
        for th in np.linspace(min(8, A / 4), max(A - 8, A * 3 / 4), k):
            for r in (ri - prof / 2, ro + prof / 2):
                p = self._arc_pt(o, r, th, 0)
                self._lbox(M, (p[0], p[1], 12 + legh / 2), (40, 40, legh), frame)
                self._lcyl(M, (p[0], p[1], 0), (p[0], p[1], 12), 32, (0.33, 0.35, 0.38, 1), True)

    def _mesh_arrays(self, o):
        """Schnelles Zeichnen grosser CAD-Netze ueber Vertex-Arrays (einmalig aufbereitet)."""
        cache = getattr(o, "_glcache", None)
        if cache is None or cache[0] is not o.mesh:
            v, f = o.mesh
            tri = v[f].reshape(-1, 3, 3)
            nrm = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
            ln = np.linalg.norm(nrm, axis=1, keepdims=True)
            nrm = nrm / np.where(ln > 0, ln, 1)
            verts = np.ascontiguousarray(tri.reshape(-1, 3), dtype=np.float32)
            norms = np.ascontiguousarray(np.repeat(nrm, 3, axis=0), dtype=np.float32)
            cache = (o.mesh, verts, norms)
            o._glcache = cache
        _, verts, norms = cache
        glEnableClientState(GL_VERTEX_ARRAY)
        glEnableClientState(GL_NORMAL_ARRAY)
        glVertexPointer(3, GL_FLOAT, 0, verts)
        glNormalPointer(GL_FLOAT, 0, norms)
        glDrawArrays(GL_TRIANGLES, 0, len(verts))
        glDisableClientState(GL_NORMAL_ARRAY)
        glDisableClientState(GL_VERTEX_ARRAY)

    def _draw_trail(self):'''),
])
# Ansicht-Menue: helle Halle / Schatten ; Multisampling + Stencil im Hauptprogramm
patch("main.py", [
    ('''        for txt, attr in (("TCP-Spur", "show_trail"), ("Koordinatensysteme", "show_frames"),''',
     '''        for txt, attr in (("Helle Hallenansicht", "light_mode"), ("Schatten", "shadows"),
                          ("TCP-Spur", "show_trail"), ("Koordinatensysteme", "show_frames"),'''),
    ('''def main():
    app = QApplication(sys.argv)''', '''def main():
    from PyQt6.QtGui import QSurfaceFormat
    fmt = QSurfaceFormat()
    fmt.setSamples(8)                 # Kantenglaettung
    fmt.setDepthBufferSize(24)
    fmt.setStencilBufferSize(8)       # fuer Bodenschatten
    QSurfaceFormat.setDefaultFormat(fmt)
    app = QApplication(sys.argv)'''),
])
print("ok")
