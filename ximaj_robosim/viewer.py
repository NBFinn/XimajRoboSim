"""3D-Ansicht (OpenGL, Qt) der Ximaj RoboSim."""
import math
import numpy as np
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtOpenGLWidgets import QOpenGLWidget
from OpenGL.GL import *
from OpenGL.GLU import *

import theme
from kinematics import inv, pose_to_mat
import part_geom


def hexrgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


class Viewer(QOpenGLWidget):
    picked = pyqtSignal(object)
    point_picked = pyqtSignal(object, object)       # Weltpunkt, Objekt (oder None = Boden)
    object_moved = pyqtSignal(object)                # Objekt per Achsenkreuz/PnP bewegt
    target_picked = pyqtSignal(str, object)          # Modus (snap/align/attach), Zielobjekt
    measured = pyqtSignal(dict)                      # Messergebnis
    interacted = pyqtSignal(object)                  # Interagieren-Klick
    selection_changed = pyqtSignal(list)

    def __init__(self, sim, parent=None):
        super().__init__(parent)
        self.sim = sim
        self.az, self.el, self.dist = 35.0, 25.0, 3200.0
        self.center = np.array([300.0, 0.0, 400.0])
        self._last = None
        self.selected = None
        self.show_trail = True
        self.show_reach = False
        self.show_swept = False
        self.show_caps = False
        self.show_frames = True
        self.reach_ok = np.zeros((0, 3))
        self.reach_bad = np.zeros((0, 3))
        self.setMinimumSize(500, 400)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._quad = None
        self.proc_preview = None        # Prozessvorschau (Bahn/Punkte/Abdeckung)
        self.light_mode = True          # helle Hallenansicht
        self.shadows = True
        self._shadow = False
        self._rmesh = {}                # Robotergeometrie je Modellmassen (robot_geom)
        self._pmesh = {}                # Detailgeometrie der Katalogteile (part_geom)
        # Werkzeugmodi des Menuebands
        self.mode = "select"            # select|move|pnp|interact|jog|measure|dim_linear|dim_angle|snap|align|attach
        self.move_children = True       # Bewegungsmodus Hierarchie (True) / nur Ausgewaehlt (False)
        self.snap_step = 500.0          # Positionsraster (mm)
        self.snap_auto = True           # Rastergroesse nach Zoom
        self.snap_always = True         # immer fangen
        self.selection = []             # Mehrfachauswahl
        self.pts = []                   # gesammelte Klickpunkte (Messen/Bemassen)
        self.measure_result = None
        self.show_dims = True
        self.show_traces = True
        self._drag = None
        self._band = None
        self._rgeom_off = False         # nach Fehler: einfache Grundkoerper zeichnen

    def _col(self, *c):
        if self._shadow:
            glColor4f(*((0.10, 0.11, 0.14, 0.34) if self.light_mode else (0.0, 0.01, 0.04, 0.55)))
        else:
            glColor4f(*(tuple(c) + (1.0,) * (4 - len(c))))

    # ------------------------------------------------ GL
    def initializeGL(self):
        glEnable(GL_DEPTH_TEST)
        glEnable(GL_NORMALIZE)
        glEnable(GL_COLOR_MATERIAL)
        glColorMaterial(GL_FRONT_AND_BACK, GL_AMBIENT_AND_DIFFUSE)
        glEnable(GL_LIGHT0)
        glEnable(GL_LIGHT1)
        glLightfv(GL_LIGHT0, GL_AMBIENT, (0.28, 0.29, 0.31, 1))
        glLightfv(GL_LIGHT0, GL_DIFFUSE, (0.82, 0.81, 0.78, 1))
        glLightfv(GL_LIGHT0, GL_SPECULAR, (0.55, 0.55, 0.55, 1))
        glLightfv(GL_LIGHT1, GL_AMBIENT, (0.0, 0.0, 0.0, 1))
        glLightfv(GL_LIGHT1, GL_DIFFUSE, (0.32, 0.34, 0.38, 1))
        glLightfv(GL_LIGHT1, GL_SPECULAR, (0.0, 0.0, 0.0, 1))
        glLightModeli(GL_LIGHT_MODEL_TWO_SIDE, GL_FALSE)
        glMaterialfv(GL_FRONT_AND_BACK, GL_SPECULAR, (0.35, 0.35, 0.35, 1))
        glMaterialf(GL_FRONT_AND_BACK, GL_SHININESS, 42.0)
        try:
            glEnable(GL_MULTISAMPLE)
        except Exception:
            pass
        glEnable(GL_BLEND)
        # Farbe normal mischen, Ziel-Alpha deckend halten (sonst Falschfarben beim Zusammensetzen des Fensters)
        glBlendFuncSeparate(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA, GL_ONE, GL_ONE_MINUS_SRC_ALPHA)
        glClearColor(0, 0, 0, 1)
        glEnable(GL_LINE_SMOOTH)
        self._quad = gluNewQuadric()

    def resizeGL(self, w, h):
        glViewport(0, 0, w, h)

    def _background(self):
        glDisable(GL_DEPTH_TEST)
        glDisable(GL_LIGHTING)
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        glOrtho(0, 1, 0, 1, -1, 1)
        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()
        bot, top = ((0.80, 0.82, 0.85), (0.93, 0.94, 0.96)) if self.light_mode else \
            (hexrgb(theme.BRAND["viewport_bottom"]), hexrgb(theme.BRAND["viewport_top"]))
        glBegin(GL_QUADS)
        glColor3f(*bot)
        glVertex2f(0, 0)
        glVertex2f(1, 0)
        glColor3f(*top)
        glVertex2f(1, 1)
        glVertex2f(0, 1)
        glEnd()
        glEnable(GL_DEPTH_TEST)

    def _camera(self):
        w, h = max(self.width(), 1), max(self.height(), 1)
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        gluPerspective(40, w / h, max(20.0, self.dist / 60.0), max(60000.0, self.dist * 8))
        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()
        az, el = math.radians(self.az), math.radians(self.el)
        eye = self.center + self.dist * np.array([math.cos(el) * math.cos(az), math.cos(el) * math.sin(az), math.sin(el)])
        gluLookAt(*eye, *self.center, 0, 0, 1)
        self._eye = eye
        # Hauptlicht als "Hallenlicht" schraeg von oben (gerichtet), Fuelllicht von der Kamera
        self._sun = np.array([0.35, 0.25, 1.0])
        self._sun /= np.linalg.norm(self._sun)
        glLightfv(GL_LIGHT0, GL_POSITION, (*self._sun, 0.0))
        d = (eye - self.center)
        d = d / (np.linalg.norm(d) or 1)
        glLightfv(GL_LIGHT1, GL_POSITION, (*d, 0.0))

    def paintGL(self):
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        self._background()
        self._camera()
        glEnable(GL_LIGHTING)
        self._grid()
        if self.shadows:
            self._shadow_pass()
        self._draw_robots()
        self._draw_scene()
        glDisable(GL_LIGHTING)
        if self.show_trail:
            self._draw_trail()
        if self.show_reach:
            self._points(self.reach_ok, (0.2, 0.9, 0.5, 0.5), 4)
            self._points(self.reach_bad, (1.0, 0.3, 0.3, 0.12), 2)
        if self.show_swept:
            self._draw_swept()
        if self.show_frames:
            for r in self.sim.robots:
                self._draw_axes(r.tcp_world(), 120, 1.0 if r is self.sim.active else 0.45)
                self._draw_axes(r.robroot(), 200, 0.5)
            self._draw_axes(self.sim.base_world(), 150, 0.4)
        self._draw_safety()
        if self.proc_preview:
            self._draw_process(self.proc_preview)
        self._draw_overlays_gl()
        self._mv, self._pr, self._vp = glGetDoublev(GL_MODELVIEW_MATRIX), glGetDoublev(GL_PROJECTION_MATRIX), glGetIntegerv(GL_VIEWPORT)
        self._overlay_text()

    # ------------------------------------------------ Primitive
    def _grid(self):
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
            # dunkle Ximaj-Halle: Boden in Navy, Raster in Blau
            glEnable(GL_POLYGON_OFFSET_FILL)
            glPolygonOffset(2.0, 2.0)
            glBegin(GL_QUADS)
            glColor4f(*hexrgb(theme.BRAND["floor"]), 1)
            for x, y in ((-ext, -ext), (ext, -ext), (ext, ext), (-ext, ext)):
                glVertex3f(x, y, 0)
            glEnd()
            glDisable(GL_POLYGON_OFFSET_FILL)
            fine = (*hexrgb(theme.BRAND["grid"]), 1)
            major = (*hexrgb(theme.BRAND["grid_major"]), 1)
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
        h = 2.5
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
            self._draw_robots()
            self._draw_scene()
        finally:
            self._shadow = False
            glPopMatrix()
            glDisable(GL_STENCIL_TEST)
            glDepthMask(GL_TRUE)
            glEnable(GL_LIGHTING)

    def _cyl(self, p, q, r, color, caps=True):
        d = q - p
        L = float(np.linalg.norm(d))
        if L < 1e-6:
            return
        self._col(*color)
        glPushMatrix()
        glTranslatef(*p)
        z = np.array([0, 0, 1.0])
        ax = np.cross(z, d / L)
        ang = math.degrees(math.acos(max(-1, min(1, (d / L)[2]))))
        if np.linalg.norm(ax) > 1e-9:
            glRotatef(ang, *ax)
        elif d[2] < 0:
            glRotatef(180, 1, 0, 0)
        gluCylinder(self._quad, r, r, L, 24, 1)
        if caps:
            gluSphere(self._quad, r, 20, 12)
            glTranslatef(0, 0, L)
            gluSphere(self._quad, r, 20, 12)
        glPopMatrix()

    def _sphere(self, p, r, color):
        self._col(*color)
        glPushMatrix()
        glTranslatef(*p)
        gluSphere(self._quad, r, 20, 12)
        glPopMatrix()

    def _box(self, M, size, color, alpha=1.0, wire=False, z0=True):
        """Quader: M Lage am Boden-Mittelpunkt, size=(x,y,z)"""
        sx, sy, sz = size
        glPushMatrix()
        glMultMatrixf(np.ascontiguousarray(M.T, dtype=np.float32))
        glTranslatef(0, 0, sz / 2 if z0 else 0)
        glScalef(sx, sy, sz)
        if wire and self._shadow:
            glPopMatrix()
            return
        if wire:
            glDisable(GL_LIGHTING)
            self._col(*color, 1)
            glLineWidth(2)
            self._cube(GL_LINE_LOOP)
            glEnable(GL_LIGHTING)
        else:
            self._col(*color, alpha)
            self._cube(GL_QUADS)
        glPopMatrix()

    def _cube(self, mode):
        faces = [((0, 0, 1), [(-.5, -.5, .5), (.5, -.5, .5), (.5, .5, .5), (-.5, .5, .5)]),
                 ((0, 0, -1), [(-.5, .5, -.5), (.5, .5, -.5), (.5, -.5, -.5), (-.5, -.5, -.5)]),
                 ((1, 0, 0), [(.5, -.5, -.5), (.5, .5, -.5), (.5, .5, .5), (.5, -.5, .5)]),
                 ((-1, 0, 0), [(-.5, .5, -.5), (-.5, -.5, -.5), (-.5, -.5, .5), (-.5, .5, .5)]),
                 ((0, 1, 0), [(.5, .5, -.5), (-.5, .5, -.5), (-.5, .5, .5), (.5, .5, .5)]),
                 ((0, -1, 0), [(-.5, -.5, -.5), (.5, -.5, -.5), (.5, -.5, .5), (-.5, -.5, .5)])]
        for n, vs in faces:
            glBegin(mode)
            glNormal3f(*n)
            for v in vs:
                glVertex3f(*v)
            glEnd()

    def _points(self, pts, color, size):
        if len(pts) == 0:
            return
        glPointSize(size)
        self._col(*color)
        glBegin(GL_POINTS)
        for p in pts:
            glVertex3f(*p)
        glEnd()

    def _draw_axes(self, M, L, alpha=1.0):
        glLineWidth(3)
        glBegin(GL_LINES)
        o = M[:3, 3]
        for i, c in enumerate(((1, .25, .25), (.3, 1, .3), (.35, .55, 1))):
            self._col(*c, alpha)
            glVertex3f(*o)
            glVertex3f(*(o + M[:3, i] * L))
        glEnd()

    # ------------------------------------------------ Szene
    # Hilfen fuer lokale Geometrie in einem Gelenk-Koordinatensystem M
    def _lcyl(self, M, p, q, r, color, caps=False):
        P = (M @ np.array([*p, 1.0]))[:3]
        Q = (M @ np.array([*q, 1.0]))[:3]
        self._cyl(P, Q, r, color, False)
        if caps:
            d = Q - P
            L = np.linalg.norm(d)
            if L > 1e-6:
                self._col(*color)
                for X, sgn in ((P, -1), (Q, 1)):
                    glPushMatrix()
                    glTranslatef(*X)
                    z = np.array([0, 0, 1.0])
                    ax = np.cross(z, d / L)
                    ang = math.degrees(math.acos(max(-1, min(1, (d / L)[2]))))
                    if np.linalg.norm(ax) > 1e-9:
                        glRotatef(ang, *ax)
                    elif d[2] < 0:
                        glRotatef(180, 1, 0, 0)
                    if sgn < 0:
                        glRotatef(180, 1, 0, 0)
                    gluDisk(self._quad, 0, r, 28, 1)
                    glPopMatrix()

    def _lbox(self, M, c, size, color, alpha=1.0):
        self._box(M @ pose_to_mat(c[0], c[1], c[2], 0, 0, 0), size, color, alpha, z0=False)

    def _draw_robots(self):
        for r in self.sim.robots:
            if r.track is not None:
                self._draw_track(r)
            self._draw_robot(r)

    def _draw_track(self, r):
        """Linearachse: Bodenschiene mit Zahnstange und Schlitten"""
        lo, hi = r.e_limits()
        L = hi - lo
        s = r.model.reach / 1000.0
        w = max(380.0, r.model.reach * 0.32)
        frame = (0.34, 0.37, 0.42)
        rail = (0.78, 0.8, 0.84)
        H = max(float(r.root[2, 3]), 60.0)            # Schiene vom Hallenboden bis zum Roboterfuss
        M = r.root @ pose_to_mat(lo, 0, -H, 0, 0, 0)
        body = max(H - 70, 20)
        self._lbox(M, (L / 2, 0, body / 2), (L + w, w * 0.8, body), frame)          # Grundkoerper
        for x in np.linspace(0, L, max(2, int(L / 1500) + 2)):                       # Bodenplatten
            self._lbox(M, (x, 0, 8), (220, w * 1.1, 16), (0.28, 0.3, 0.34))
        for sy in (-1, 1):
            self._lbox(M, (L / 2, sy * w * 0.3, body + 25), (L + w * 0.8, 46, 50), rail)    # Fuehrungsschienen
        self._lbox(M, (L / 2, -w * 0.42, body + 15), (L + w * 0.8, 20, 30), (0.2, 0.22, 0.25))  # Zahnstange
        self._lbox(M, (L / 2, w * 0.42, body * 0.6), (L + w * 0.6, 60, body * 0.5), (0.12, 0.13, 0.15))  # Energiekette
        # Schlitten unter dem Roboter
        self._lbox(r.robroot(), (0, 0, -10), (w * 1.0, w * 1.05, 20), hexrgb(theme.BRAND["robot"]))
        # Endanschlaege
        for x in (-w * 0.5, L + w * 0.5):
            self._lbox(M, (x, 0, body + 40), (40, w * 0.85, 80), (0.95, 0.75, 0.1))

    def _draw_robot(self, r=None):
        sim = r or self.sim.active
        self._cur_robot = sim
        m = sim.model
        collided = bool(sim.collision)
        body = (1.0, 0.3, 0.35) if collided else hexrgb(getattr(m, "paint", None) or theme.BRAND["robot"])
        dark = (0.13, 0.15, 0.2)
        metal = hexrgb(theme.BRAND["robot_joint"])
        accent = hexrgb(theme.BRAND.get("robot_trim", theme.BRAND["accent"]))
        f = [sim.robroot() @ x for x in m.frames(sim.q)]
        s = m.reach / 1000.0
        drawn = False
        if not self._rgeom_off:
            try:
                self._draw_robot_mesh(m, f, {"body": body, "dark": dark, "metal": metal, "trim": accent,
                                             "warn": (0.98, 0.78, 0.08)})
                if not getattr(m, "cad", None):
                    self._draw_dress(m, f, dark, body, metal)
                drawn = True
            except Exception as e:          # Geometriefehler darf die Ansicht nicht stoppen
                self._rgeom_off = True
                print("Robotergeometrie nicht verfuegbar, einfache Darstellung:", e)
        if not drawn:
            self._draw_robot_prims(sim, f, body, dark, metal, accent)
        self._draw_tool(f[6], sim)
        # TCP-Marker
        self._sphere(sim.tcp_world()[:3, 3], 6 + 4 * s, (1, 1, 1, 1))
        if self.show_caps:
            for p, q, r, nm in sim.capsules():
                glDepthMask(GL_FALSE)
                self._cyl(p, q, r, (1, 0.6, 0.1, 0.18), True)
                glDepthMask(GL_TRUE)

    def _draw_robot_prims(self, sim, f, body, dark, metal, accent):
        """Einfache Darstellung aus Quadern und Zylindern (Rueckfallebene)"""
        m = sim.model
        s = m.reach / 1000.0
        rb = max(60.0, 105 * s)
        w = max(45.0, 85 * s)
        d1, a1, a2, a3, d4, d6 = m.d1, m.a1, m.a2, m.a3, m.d4, m.d6
        # Fuss (fest)
        self._box(sim.robroot(), (rb * 2.6, rb * 2.6, 18 * s + 8), dark)
        self._lcyl(f[0], (0, 0, 0), (0, 0, d1 * 0.22), rb * 1.12, (*dark, 1), True)
        self._lcyl(f[0], (0, 0, d1 * 0.22), (0, 0, d1 * 0.24), rb * 1.16, (*accent, 1), True)   # Ximaj-Ring
        # Karussell (A1)
        self._lcyl(f[1], (0, 0, d1 * 0.24), (0, 0, d1 * 0.62), rb, (*body, 1), True)
        self._lbox(f[1], (a1 * 0.5, 0, d1 * 0.8), (abs(a1) + rb * 1.5, rb * 1.75, d1 * 0.42), body)
        # Schultermotor (A2) quer
        self._lcyl(f[2], (0, -rb * 0.98, 0), (0, rb * 0.98, 0), rb * 0.6, (*body, 1), True)
        self._lcyl(f[2], (0, rb * 0.98, 0), (0, rb * 1.4, 0), rb * 0.38, (*dark, 1), True)
        self._lcyl(f[2], (0, -rb * 0.98, 0), (0, -rb * 1.25, 0), rb * 0.45, (*metal, 1), True)
        # Oberarm (Schwinge)
        self._lbox(f[2], (0, 0, a2 / 2), (w * 1.05, w * 0.85, a2), body)
        self._lbox(f[2], (0, w * 0.43, a2 / 2), (w * 0.7, 6, a2 * 0.7), accent)                 # Zierstreifen
        # Ellbogen (A3)
        self._lcyl(f[3], (0, -w * 0.62, 0), (0, w * 0.62, 0), w * 0.6, (*body, 1), True)
        self._lcyl(f[3], (0, w * 0.62, 0), (0, w * 0.85, 0), w * 0.36, (*dark, 1), True)
        # Unterarm mit Motorgehaeuse hinten
        self._lbox(f[3], (-a3, 0, -w * 0.15), (w * 1.1, w * 1.0, w * 1.5), body)
        self._lbox(f[3], (-a3, 0, -w * 0.95), (w * 0.9, w * 0.85, w * 0.4), dark)
        self._lcyl(f[3], (-a3, 0, w * 0.5), (-a3, 0, d4 - w * 0.45), w * 0.36, (*body, 1), True)
        self._lcyl(f[3], (-a3, 0, d4 * 0.55), (-a3, 0, d4 * 0.58), w * 0.39, (*accent, 1), True)
        # Handgelenk (A4/A5): Gabel + Knick
        self._lbox(f[4], (0, 0, -w * 0.25), (w * 0.55, w * 0.9, w * 0.5), body)
        self._lcyl(f[4], (0, -w * 0.45, 0), (0, w * 0.45, 0), w * 0.3, (*body, 1), True)
        # Hand (A5 -> A6)
        self._lcyl(f[5], (0, 0, 0), (0, 0, max(d6 - 10, 1)), w * 0.24, (*body, 1), True)
        # Flansch (A6)
        self._lcyl(f[6], (0, 0, -10), (0, 0, 0), w * 0.3, (*metal, 1), True)
        self._lcyl(f[6], (w * 0.15, 0, -10.5), (w * 0.15, 0, 0.5), w * 0.04, (*accent, 1), True)  # Markierung A6

    def _robot_meshes(self, m):
        key = (m.a1, m.d1, m.a2, m.a3, m.d4, m.d6, getattr(m, "payload", 0))
        c = self._rmesh.get(key)
        if c is None:
            import robot_geom
            c = []
            for link in robot_geom.build_robot_meshes(m):
                c.append([(np.ascontiguousarray(v, dtype=np.float32), np.ascontiguousarray(n, dtype=np.float32),
                           np.ascontiguousarray(fc, dtype=np.uint32).ravel(), mat) for v, n, fc, mat in link])
            self._rmesh[key] = c
        return c

    def _cad_link(self, path):
        """CAD-Datei eines Roboterglieds (Originalkoordinaten), einmalig geladen und als Arrays gecacht"""
        c = self._rmesh.get(("cad", path))
        if c is None:
            import cad
            V, F = cad.load_cad(path, max_tris=120000, recenter=False)
            tri = V[F].reshape(-1, 3, 3)
            nrm = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
            ln = np.linalg.norm(nrm, axis=1, keepdims=True)
            nrm = nrm / np.where(ln > 0, ln, 1)
            c = (np.ascontiguousarray(tri.reshape(-1, 3), dtype=np.float32),
                 np.ascontiguousarray(np.repeat(nrm, 3, axis=0), dtype=np.float32))
            self._rmesh[("cad", path)] = c
        return c

    def _draw_robot_mesh(self, m, f, colors):
        """Glatte Gussgehaeuse aus robot_geom (oder CAD je Glied), je Glied im Gelenk-Koordinatensystem"""
        meshes = self._robot_meshes(m)
        cadmap = getattr(m, "cad", None) or {}
        if cadmap:
            F0 = m.frames(np.zeros(6))                     # CAD liegt in Nullstellung im Fusssystem vor
            meshes = list(meshes)
            for k, path in cadmap.items():
                k = int(k)
                try:
                    v, n = self._cad_link(path)
                except Exception as e:
                    if not self._shadow:
                        print("CAD-Glied", k, "nicht ladbar:", e)
                    self._rmesh[("cad", path)] = (np.zeros((0, 3), np.float32), np.zeros((0, 3), np.float32))
                    continue
                if len(v) == 0:
                    continue
                meshes[k] = []
                glEnableClientState(GL_VERTEX_ARRAY)
                glEnableClientState(GL_NORMAL_ARRAY)
                glPushMatrix()
                glMultMatrixf(np.ascontiguousarray((f[k] @ inv(F0[k])).T, dtype=np.float32))
                if not self._shadow:
                    spec, shin = self.SURFACE["body" if k else "dark"]
                    glMaterialfv(GL_FRONT_AND_BACK, GL_SPECULAR, (spec, spec, spec, 1))
                    glMaterialf(GL_FRONT_AND_BACK, GL_SHININESS, shin)
                self._col(*(colors["body"] if k else colors["dark"]))
                glVertexPointer(3, GL_FLOAT, 0, v)
                glNormalPointer(GL_FLOAT, 0, n)
                glDrawArrays(GL_TRIANGLES, 0, len(v))
                glPopMatrix()
                glDisableClientState(GL_NORMAL_ARRAY)
                glDisableClientState(GL_VERTEX_ARRAY)
        glEnableClientState(GL_VERTEX_ARRAY)
        glEnableClientState(GL_NORMAL_ARRAY)
        try:
            warn = set()
            r = getattr(self, "_cur_robot", None)
            if r is not None and getattr(self.sim, "show_limit_colors", False):
                warn = {j + 1 for j in (getattr(r, "near_limits", None) or ())}
            for k, (M, link) in enumerate(zip(f, meshes)):
                glPushMatrix()
                glMultMatrixf(np.ascontiguousarray(M.T, dtype=np.float32))
                for v, n, idx, mat in link:
                    if len(idx) == 0:
                        continue
                    if not self._shadow:
                        spec, shin = self.SURFACE.get(mat, (0.35, 42.0))
                        glMaterialfv(GL_FRONT_AND_BACK, GL_SPECULAR, (spec, spec, spec, 1))
                        glMaterialf(GL_FRONT_AND_BACK, GL_SHININESS, shin)
                    col = colors.get(mat, colors["body"])
                    if k in warn and mat in ("body", "trim"):
                        col = (1.0, 0.45, 0.1)                 # Achse nahe ihrer Grenze
                    self._col(*col)
                    glVertexPointer(3, GL_FLOAT, 0, v)
                    glNormalPointer(GL_FLOAT, 0, n)
                    glDrawElements(GL_TRIANGLES, len(idx), GL_UNSIGNED_INT, idx)
                glPopMatrix()
        finally:
            glDisableClientState(GL_NORMAL_ARRAY)
            glDisableClientState(GL_VERTEX_ARRAY)
            glMaterialfv(GL_FRONT_AND_BACK, GL_SPECULAR, (0.35, 0.35, 0.35, 1))
            glMaterialf(GL_FRONT_AND_BACK, GL_SHININESS, 42.0)

    # Lack glaenzend, Metall poliert, Gummi/Guss matt
    SURFACE = {"body": (0.55, 64.0), "trim": (0.5, 64.0), "metal": (0.9, 96.0), "dark": (0.18, 18.0), "warn": (0.3, 30.0)}

    def _tube(self, pts, r, color, n=14):
        """Schlauch entlang einer Punktfolge (Kabelstrang, Leitungen)"""
        pts = np.asarray(pts, float)
        T = np.gradient(pts, axis=0)
        T /= np.maximum(np.linalg.norm(T, axis=1, keepdims=True), 1e-9)
        ref = np.array([0, 0, 1.0]) if abs(T[0, 2]) < 0.9 else np.array([1.0, 0, 0])
        N = np.cross(T[0], ref)
        N /= np.linalg.norm(N)
        ang = np.linspace(0, 2 * np.pi, n + 1)
        rings = []
        for i in range(len(pts)):
            N = N - T[i] * (N @ T[i])                        # parallel transportieren
            N /= max(np.linalg.norm(N), 1e-9)
            B = np.cross(T[i], N)
            rings.append([(pts[i] + r * (np.cos(a) * N + np.sin(a) * B), np.cos(a) * N + np.sin(a) * B) for a in ang])
        self._col(*color)
        for a, b in zip(rings[:-1], rings[1:]):
            glBegin(GL_QUAD_STRIP)
            for (pa, na), (pb, nb) in zip(a, b):
                glNormal3f(*na)
                glVertex3f(*pa)
                glNormal3f(*nb)
                glVertex3f(*pb)
            glEnd()

    @staticmethod
    def _bezier(p0, p1, p2, p3, n=24):
        t = np.linspace(0, 1, n)[:, None]
        return (1 - t) ** 3 * p0 + 3 * (1 - t) ** 2 * t * p1 + 3 * (1 - t) * t ** 2 * p2 + t ** 3 * p3

    def _draw_dress(self, m, f, dark, body, metal):
        """Energiezufuehrung vom Karussell zum Motorpaket und Gewichtsausgleich bei Schwerlastrobotern"""
        P = lambda M, x, y, z: (M @ np.array([x, y, z, 1.0]))[:3]
        heavy = float(np.clip(1 + 0.22 * np.log10(max(getattr(m, "payload", 10) or 10, 1) / 10), 0.85, 1.45))
        s = m.reach / 1000.0
        rb = max(60.0, 105 * s) * heavy
        w = max(45.0, 85 * s) * heavy
        # Kabelstrang: Karussell hinten oben -> ueber den Oberarm -> Rueckseite Motorpaket
        a = P(f[1], -.95 * rb, .35 * rb, .62 * m.d1)
        b = P(f[3], -m.a3 - .35 * w, .55 * w, -.85 * w)
        up1 = f[1][:3, 2] * (.45 * m.a2)
        mid = P(f[2], -.75 * w, .55 * w, .5 * m.a2)
        pts = np.vstack((self._bezier(a, a + up1, mid - f[2][:3, 2] * .3 * m.a2, mid, 16)[:-1],
                         self._bezier(mid, mid + f[2][:3, 2] * .3 * m.a2, b - f[3][:3, 2] * .35 * w, b, 16)))
        self._tube(pts, .11 * w, (0.1, 0.1, 0.11))
        self._tube(pts + f[2][:3, 1] * .16 * w, .06 * w, (0.16, 0.16, 0.18), 10)
        # Gewichtsausgleich (Hydropneumatik) ab 80 kg Traglast
        if (getattr(m, "payload", 0) or 0) >= 80:
            y = .98 * rb
            p0 = P(f[1], m.a1 - .95 * rb, y, m.d1 + .15 * rb)
            p1 = P(f[2], -.55 * w, y, .32 * m.a2)
            d = p1 - p0
            L = np.linalg.norm(d)
            if L > 1:
                u = d / L
                self._cyl(p0, p0 + u * .58 * L, .2 * w, (*body, 1))           # Zylinder
                self._cyl(p0 + u * .5 * L, p1, .09 * w, (*metal, 1))         # Kolbenstange
                self._sphere(p0, .24 * w, (*dark, 1))
                self._sphere(p1, .16 * w, (*dark, 1))

    def _draw_tool(self, F, sim=None):
        sim = sim or self.sim.active
        t = sim.tool
        Tl = t.matrix()
        p = Tl[:3, 3]
        L = float(np.linalg.norm(p))
        grey = (0.62, 0.66, 0.72, 1)
        if L < 1:
            return
        r = max(t.radius, 6)
        if t.grip_out:
            # Greiferkoerper + zwei Backen (Abstand je nach Greiferausgang)
            closed = sim.io.get_out(t.grip_out)
            body_end = p * 0.55
            self._lcyl(F, (0, 0, 0), tuple(body_end), r * 1.15, grey, True)
            self._lbox(F @ Tl, (0, 0, -L * 0.45 + 6), (r * 2.6, r * 1.4, 12), (0.3, 0.33, 0.4))
            gap = r * (0.55 if closed else 1.1)
            for sg in (-1, 1):
                self._lbox(F @ Tl, (sg * gap, 0, -L * 0.2), (r * 0.35, r * 1.1, L * 0.42), (0.85, 0.87, 0.9))
        else:
            # Prozesswerkzeug (Brenner/Duese/Spindel): Koerper + Spitze entlang Flansch->TCP
            self._lcyl(F, (0, 0, 0), tuple(p * 0.65), r, grey, True)
            self._lcyl(F, tuple(p * 0.65), tuple(p), r * 0.35, (0.85, 0.6, 0.25, 1), True)

    def _draw_scene(self):
        sim = self.sim
        for o in sim.scene:
            if not o.visible:
                continue
            c = hexrgb(o.color)
            M = o.matrix()
            parts = self._part_meshes(o)
            if parts and o.kind in self.CENTERED_KINDS:
                M = M @ pose_to_mat(0, 0, -o.size[2] / 2, 0, 0, 0)
            if parts and o.kind in ("box", "workpiece", "cylinder", "fence"):
                self._draw_part(o, M, parts)
            elif o.kind in ("box", "workpiece"):
                if o.alpha < 0.99:
                    glDepthMask(GL_FALSE)
                    self._box(M, o.size, c, o.alpha)
                    glDepthMask(GL_TRUE)
                else:
                    self._box(M, o.size, c, 1.0)
                    if self.light_mode and not self._shadow:
                        self._box(M, o.size, (0.15, 0.17, 0.2), 1.0, wire=True)
            elif o.kind == "cylinder":
                self._col(*c, 1)
                glPushMatrix()
                glMultMatrixf(np.ascontiguousarray(M.T, dtype=np.float32))
                gluCylinder(self._quad, o.size[0] / 2, o.size[0] / 2, o.size[2], 28, 1)
                gluDisk(self._quad, 0, o.size[0] / 2, 28, 1)
                glTranslatef(0, 0, o.size[2])
                gluDisk(self._quad, 0, o.size[0] / 2, 28, 1)
                glPopMatrix()
            elif o.kind == "conveyor" and parts:
                self._draw_part(o, M, parts)
                if getattr(o, "style", "") != "roller":
                    self._draw_belt_marks(o, M)
            elif o.kind == "conveyor":
                self._draw_conveyor(o, M)
            elif o.kind == "conveyor_arc":
                self._draw_conveyor_arc(o, M)
            elif o.kind in ("spawner", "sink") and parts:
                self._draw_part(o, M, parts)
            elif o.kind in ("sensor", "spawner", "sink", "zone"):
                if parts:
                    self._draw_part(o, M, parts)
                if self._shadow:
                    continue
                glDepthMask(GL_FALSE)
                on = o.kind == "sensor" and o.io and sim.io.get_in(int(o.io))
                cc = (0.3, 1, 0.4) if on else c
                self._box(M, o.size, cc, 0.12 if parts else 0.22, z0=bool(parts))
                glDepthMask(GL_TRUE)
                if not parts:
                    self._box(M, o.size, cc, 1.0, wire=True, z0=False)
            elif o.kind == "fence":
                self._draw_fence(o, M)
            elif o.kind == "color_sensor":
                self._draw_color_sensor(o, M, parts)
            elif o.kind == "lamp":
                self._draw_lamp(o, M, parts)
            elif o.kind == "drawing":
                if self._shadow:
                    continue
                glDisable(GL_LIGHTING)
                glLineWidth(1.6)
                glPushMatrix()
                glMultMatrixf(np.ascontiguousarray(M.T, dtype=np.float32))
                glColor4f(*c, 1)
                for pl in o.lines:
                    glBegin(GL_LINE_STRIP)
                    for p in pl:
                        glVertex3f(p[0], p[1], 1.5)
                    glEnd()
                glPopMatrix()
                glEnable(GL_LIGHTING)
            elif o.kind == "mesh" and o.mesh is not None:
                self._col(*c, 1)
                glPushMatrix()
                glMultMatrixf(np.ascontiguousarray(M.T, dtype=np.float32))
                self._mesh_arrays(o)
                glPopMatrix()
            if o is self.selected and not self._shadow:
                self._box(M, o.size, hexrgb(theme.BRAND["accent"]), 1.0, wire=True)

    def _sig(self, n):
        """Signalzustand unabhaengig davon, ob er als Ein- oder Ausgang gefuehrt wird"""
        try:
            n = int(n or 0)
            return n > 0 and bool(self.sim.io.get_in(n) or self.sim.io.get_out(n))
        except Exception:
            return False

    # ------------------------------------------------ Detailgeometrie der Katalogteile (part_geom)
    CENTERED_KINDS = ("sensor", "color_sensor", "spawner", "sink")
    PART_KINDS = ("box", "workpiece", "cylinder", "conveyor", "fence", "sensor", "color_sensor", "lamp", "spawner", "sink")
    PART_SURFACE = {"paint": (0.45, 56.0), "frame": (0.7, 80.0), "metal": (0.9, 96.0), "glass": (0.95, 110.0),
                    "belt": (0.08, 8.0), "rubber": (0.05, 6.0), "wood": (0.06, 8.0), "cardboard": (0.04, 6.0),
                    "dark": (0.2, 20.0), "warn": (0.35, 36.0), "mesh": (0.6, 60.0), "wood2": (0.06, 8.0),
                    "tape": (0.3, 30.0), "label": (0.1, 10.0), "motor": (0.5, 60.0), "beam": (0.45, 56.0),
                    "handle": (0.5, 50.0), "reflector": (0.8, 90.0)}

    def _part_meshes(self, o):
        """Detailmodell eines Katalogteils (zwischengespeichert je Form und Masse); [] = einfache Darstellung"""
        style = getattr(o, "style", "")
        if o.kind not in self.PART_KINDS or (o.kind in ("box", "workpiece", "cylinder") and not style):
            return []
        key = (o.kind, style, tuple(round(float(s), 1) for s in o.size), o.feet)
        if key not in self._pmesh:
            try:
                kind = "box" if o.kind == "workpiece" else o.kind
                feet = 2 if o.feet is None else int(o.feet)
                built = part_geom.build(kind, style or None, tuple(float(s) for s in o.size),
                                        feet=feet, roller=style == "roller")
                self._pmesh[key] = [(np.ascontiguousarray(v, np.float32), np.ascontiguousarray(n, np.float32),
                                     np.ascontiguousarray(f, np.uint32).ravel(), m) for v, n, f, m in built]
            except Exception as e:
                print("Detailmodell", o.kind, o.style, "nicht verfuegbar:", e)
                self._pmesh[key] = []
        return self._pmesh[key]

    def _part_colors(self, o):
        c = hexrgb(o.color)
        wood = c if getattr(o, "style", "") == "pallet" else (0.74, 0.58, 0.4)
        return {"paint": c, "frame": hexrgb(o.frame_color), "belt": hexrgb(o.belt_color),
                "metal": (0.78, 0.8, 0.83), "dark": (0.22, 0.24, 0.27), "rubber": (0.1, 0.1, 0.11),
                "wood": wood, "wood2": tuple(x * 0.86 for x in wood),
                "cardboard": c, "tape": (0.86, 0.72, 0.5), "label": (0.95, 0.95, 0.93),
                "glass": (0.45, 0.62, 0.8), "warn": (0.96, 0.72, 0.05), "beam": (0.95, 0.42, 0.08),
                "motor": (0.29, 0.34, 0.42), "handle": (0.85, 0.12, 0.1), "reflector": (0.85, 0.1, 0.12),
                "mesh": (0.62, 0.65, 0.68) if o.kind != "fence" else (0.2, 0.22, 0.25)}

    def _draw_part(self, o, M, parts):
        colors = self._part_colors(o)
        alpha = 1.0 if o.kind == "fence" or getattr(o, "style", "") == "gitterbox" else float(o.alpha)
        if alpha < 0.99:
            glDepthMask(GL_FALSE)
        glEnableClientState(GL_VERTEX_ARRAY)
        glEnableClientState(GL_NORMAL_ARRAY)
        glPushMatrix()
        glMultMatrixf(np.ascontiguousarray(M.T, dtype=np.float32))
        try:
            for v, n, idx, mat in parts:
                if len(idx) == 0:
                    continue
                if not self._shadow:
                    spec, shin = self.PART_SURFACE.get(mat, (0.35, 42.0))
                    glMaterialfv(GL_FRONT_AND_BACK, GL_SPECULAR, (spec, spec, spec, 1))
                    glMaterialf(GL_FRONT_AND_BACK, GL_SHININESS, shin)
                self._col(*colors.get(mat, colors["paint"])[:3], alpha)
                glVertexPointer(3, GL_FLOAT, 0, v)
                glNormalPointer(GL_FLOAT, 0, n)
                glDrawElements(GL_TRIANGLES, idx.size, GL_UNSIGNED_INT, idx)
        finally:
            glPopMatrix()
            glDepthMask(GL_TRUE)
            glDisableClientState(GL_NORMAL_ARRAY)
            glDisableClientState(GL_VERTEX_ARRAY)
            glMaterialfv(GL_FRONT_AND_BACK, GL_SPECULAR, (0.35, 0.35, 0.35, 1))
            glMaterialf(GL_FRONT_AND_BACK, GL_SHININESS, 42.0)

    COLOR_RGB = {"ROT": (0.9, 0.12, 0.1), "GRUEN": (0.15, 0.75, 0.25), "BLAU": (0.1, 0.35, 0.95), "GELB": (1.0, 0.85, 0.1),
                 "WEISS": (0.97, 0.97, 0.97), "SCHWARZ": (0.08, 0.08, 0.08), "ORANGE": (1.0, 0.5, 0.05)}

    def _named_rgb(self, name):
        n = str(name).upper().replace("Ü", "UE").replace("ß", "SS")
        for k, v in self.COLOR_RGB.items():
            if k in n:
                return v
        return (0.9, 0.9, 0.9)

    def _draw_color_sensor(self, o, M, parts=None):
        """Farbsensor: Lichtstrahl, Sensorkopf und LED in der erkannten Farbe"""
        L, W, H = o.size
        lit = None
        for name, n in (getattr(o, "color_outs", None) or {}).items():
            if self._sig(n):
                lit = self._named_rgb(name)
                break
        on = lit is not None or self._sig(getattr(o, "detected", 0))
        if not self._shadow:
            glDepthMask(GL_FALSE)
            self._box(M, o.size, lit or ((0.3, 1, 0.4) if on else (0.95, 0.3, 0.25)), 0.16, z0=bool(parts))
            glDepthMask(GL_TRUE)
        head = (max(L * 0.6, 40), max(min(W * 0.15, 60), 30), max(min(H * 0.6, 80), 40))
        Mh = M @ pose_to_mat(0, W / 2 + head[1] / 2, -head[2] / 2, 0, 0, 0)
        if parts:
            self._draw_part(o, M, parts)
        else:
            self._box(Mh, head, (0.18, 0.2, 0.24))
            self._box(M @ pose_to_mat(0, -W / 2 - 6, -20, 0, 0, 0), (head[0] * 0.6, 12, 40), (0.6, 0.62, 0.66))  # Reflektor
        if not self._shadow:
            glDisable(GL_LIGHTING)
            led = (M @ np.array([*part_geom.led_point("color_sensor", o.size), 1.0])) if parts else \
                (Mh @ np.array([0, -head[1] / 2, head[2] * 0.75, 1.0]))
            self._sphere(led[:3], 9, (*(lit or (0.25, 0.27, 0.3)), 1))
            glEnable(GL_LIGHTING)

    def _draw_lamp(self, o, M, parts=None):
        """Farbanzeige: Gehaeuse mit leuchtender Kuppel in der gemeldeten Farbe"""
        L, W, H = o.size
        if parts:
            self._draw_part(o, M, parts)
        else:
            self._box(M, (L, W, H * 0.45), (0.2, 0.22, 0.26))
        lit = getattr(o, "lit_color", None)
        if lit is None:
            for name, n in (getattr(o, "inputs", None) or {}).items():
                if self._sig(n):
                    lit = self._named_rgb(name)
                    break
        r = min(L, W) * 0.38
        P = (M @ np.array([0, 0, H * 0.45 + r * 0.6, 1.0]))[:3]
        if self._shadow:
            self._sphere(P, r, (0, 0, 0, 1))
            return
        if lit is not None:
            glDisable(GL_LIGHTING)
            self._sphere(P, r, (*lit[:3], 1))
            glEnable(GL_LIGHTING)
        else:
            self._sphere(P, r, (0.75, 0.77, 0.8, 0.55))

    # ------------------------------------------------ Foerdertechnik (detailgetreu)
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
        self._draw_belt_marks(o, M)

    def _draw_belt_marks(self, o, M):
        """Gurtmarkierungen, die mit dem laufenden Band mitwandern"""
        L, W, H = o.size
        bw = W * (0.4 if self._part_meshes(o) else 0.5)
        belt = hexrgb(o.belt_color)
        running = (o.io == 0) or self.sim.io.get_out(int(o.io))
        if not self._shadow:
            glDisable(GL_LIGHTING)
            mark = tuple(max(0.0, c * 0.9) for c in belt)
            off = (self.sim.t * o.speed) % 300 if running else 0.0
            glPushMatrix()
            glMultMatrixf(np.ascontiguousarray(M.T, dtype=np.float32))
            self._col(*mark, 1)
            glBegin(GL_QUADS)
            x = -L / 2 + off
            while x < L / 2:
                x1 = min(x + 12, L / 2)
                glVertex3f(x, -bw, H + 0.6)
                glVertex3f(x1, -bw, H + 0.6)
                glVertex3f(x1, bw, H + 0.6)
                glVertex3f(x, bw, H + 0.6)
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

    def _draw_fence(self, o, M):
        """Schutzzaun: gelbe Pfosten, Rahmen, Gittergeflecht"""
        L, T, H = o.size
        long_x = L >= T
        Ln = L if long_x else T
        post = (0.96, 0.72, 0.05)
        frame = (0.2, 0.22, 0.25)
        n = max(1, int(math.ceil(Ln / 1300.0)))
        xs = np.linspace(-Ln / 2, Ln / 2, n + 1)
        P = (lambda x, y, z: (x, y, z)) if long_x else (lambda x, y, z: (y, x, z))
        S = (lambda a, b, c: (a, b, c)) if long_x else (lambda a, b, c: (b, a, c))
        for x in xs:
            self._lbox(M, P(x, 0, H / 2), S(50, 50, H), post)
            self._lbox(M, P(x, 0, 5), S(140, 140, 10), post)
        for z in (120, H - 20):
            self._lbox(M, P(0, 0, z), S(Ln, 26, 26), frame)
        for i in range(n):
            self._lbox(M, P((xs[i] + xs[i + 1]) / 2, 0, H / 2), S(18, 18, H - 160), frame)
        if self._shadow:
            return
        glDisable(GL_LIGHTING)
        glPushMatrix()
        glMultMatrixf(np.ascontiguousarray(M.T, dtype=np.float32))
        glColor4f(0.25, 0.27, 0.3, 0.55)
        glLineWidth(1)
        glBegin(GL_LINES)
        step = 60.0
        z0, z1 = 133.0, H - 33.0
        x = -Ln / 2
        while x <= Ln / 2:
            glVertex3f(*P(x, 0, z0))
            glVertex3f(*P(x, 0, z1))
            x += step
        z = z0
        while z <= z1:
            glVertex3f(*P(-Ln / 2, 0, z))
            glVertex3f(*P(Ln / 2, 0, z))
            z += step
        glEnd()
        glPopMatrix()
        glEnable(GL_LIGHTING)

    def _draw_process(self, res):
        glDisable(GL_LIGHTING)
        # Abdeckung (Flaechenprozess)
        glDepthMask(GL_FALSE)
        for p0, p1, wdt in res.get("coverage", []):
            d = p1 - p0
            n = np.array([-d[1], d[0], 0.0])
            ln = np.linalg.norm(n)
            if ln < 1e-9:
                continue
            n = n / ln * wdt / 2
            glColor4f(0.95, 0.45, 0.1, 0.28)
            glBegin(GL_QUADS)
            for q in (p0 - n, p1 - n, p1 + n, p0 + n):
                glVertex3f(q[0], q[1], q[2] + 0.8)
            glEnd()
        glDepthMask(GL_TRUE)
        glLineWidth(3)
        for poly in res.get("preview", []):
            glColor4f(0.95, 0.4, 0.05, 1)
            glBegin(GL_LINE_STRIP if not res.get("points") else GL_POINTS)
            for p in poly:
                glVertex3f(*p)
            glEnd()
            glPointSize(9)
            glColor4f(0.1, 0.1, 0.1, 1)
            glBegin(GL_POINTS)
            for p in poly:
                glVertex3f(*p)
            glEnd()
        glEnable(GL_LIGHTING)

    def _draw_trail(self):
        for r in self.sim.robots:
            self._draw_one_trail(r.trail)

    def _draw_one_trail(self, t):
        if len(t) < 2:
            return
        glLineWidth(2)
        self._col(*hexrgb(theme.BRAND["accent"]), 0.9)
        glBegin(GL_LINE_STRIP)
        for p in t[-3000:]:
            glVertex3f(*p)
        glEnd()

    def _draw_swept(self):
        self._col(1.0, 0.7, 0.2, 0.18)
        glDepthMask(GL_FALSE)
        glEnable(GL_LIGHTING)
        for key in list(self.sim.swept)[:4000]:
            c = (np.array(key) + 0.5) * 40.0
            self._box(np.eye(4) @ pose_to_mat(c[0], c[1], c[2] - 20, 0, 0, 0), (40, 40, 40), (1.0, 0.7, 0.2), 0.18)
        glDepthMask(GL_TRUE)

    def _draw_safety(self):
        glDisable(GL_LIGHTING)
        for z in self.sim.safety:
            lo, hi = np.array(z["min"], float), np.array(z["max"], float)
            col = (1, .3, .3) if z.get("type", "verbot") == "verbot" else (.3, .7, 1)
            self._box(pose_to_mat(*((lo + hi) / 2 - np.array([0, 0, (hi - lo)[2] / 2])), 0, 0, 0), tuple(hi - lo), col,
                      1.0, wire=True)
            glDepthMask(GL_FALSE)
            self._box(pose_to_mat(*((lo + hi) / 2 - np.array([0, 0, (hi - lo)[2] / 2])), 0, 0, 0), tuple(hi - lo), col,
                      0.07)
            glDepthMask(GL_TRUE)
        glEnable(GL_LIGHTING)

    # ------------------------------------------------ Eingabe
    # ------------------------------------------------ Interaktion (Menueband-Werkzeuge)
    def _matrices(self):
        self.makeCurrent()
        self._camera()
        return glGetDoublev(GL_MODELVIEW_MATRIX), glGetDoublev(GL_PROJECTION_MATRIX), glGetIntegerv(GL_VIEWPORT)

    def _ray(self, pos):
        mv, pr, vp = self._matrices()
        x, y = pos.x(), self.height() - pos.y()
        p0 = np.array(gluUnProject(x, y, 0.0, mv, pr, vp))
        p1 = np.array(gluUnProject(x, y, 1.0, mv, pr, vp))
        return p0, (p1 - p0) / np.linalg.norm(p1 - p0)

    def _project(self, P, mats=None):
        mv, pr, vp = mats or self._matrices()
        x, y, z = gluProject(*P, mv, pr, vp)
        return np.array([x, self.height() - y]), z

    def pick_point(self, pos):
        """Objekt und Treffpunkt unter dem Mauszeiger (Boden z=0, wenn nichts getroffen)"""
        p0, d = self._ray(pos)
        best, bt = None, 1e18
        for o in self.sim.scene:
            if not o.visible or o.kind == "group":
                continue
            Mi = inv(o.matrix())
            lo = (Mi @ np.array([*p0, 1]))[:3]
            ld = Mi[:3, :3] @ d
            hs = np.array(o.size) / 2
            c = np.array([0, 0, hs[2]]) if o.kind not in ("sensor", "spawner", "zone", "color_sensor") else np.zeros(3)
            t = _ray_box(lo - c, ld, hs)
            if t is not None and 0 <= t < bt:
                best, bt = o, t
        if best is None:
            if abs(d[2]) < 1e-9:
                return None, None
            t = -p0[2] / d[2]
            return None, (p0 + d * t if t > 0 else None)
        return best, p0 + d * bt

    def _snap(self, v, force=False):
        step = self.snap_step
        if self.snap_auto:
            step = 10 ** math.floor(math.log10(max(self.dist / 20.0, 1)))
        if (self.snap_always or force) and step > 0:
            return round(v / step) * step
        return v

    def _gizmo_frame(self):
        """Ursprung und Achsen des Achsenkreuzes (Objekt oder Roboter-TCP)"""
        if self.mode == "jog":
            T = self.sim.active.tcp_world()
            return T[:3, 3], np.eye(3), max(80.0, self.dist * 0.07)
        o = self.selected
        if o is None or self.mode not in ("move", "pnp"):
            return None
        return np.array(o.pos, float), np.eye(3), max(80.0, self.dist * 0.07)

    def _hit_gizmo(self, pos):
        g = self._gizmo_frame()
        if g is None:
            return None
        o, R, L = g
        mats = self._matrices()
        m = np.array([pos.x(), pos.y()])
        a, _ = self._project(o, mats)
        best = None
        for i in range(3):
            b, _ = self._project(o + R[:, i] * L, mats)
            ab = b - a
            t = np.clip((m - a) @ ab / max(ab @ ab, 1e-9), 0, 1)
            dd = np.linalg.norm(a + t * ab - m)
            if dd < 9 and t > 0.15 and (best is None or dd < best[1]):
                best = (("axis", i), dd)
        if self.mode == "move":                      # Drehring um Z
            ring = [o + L * 0.8 * np.array([math.cos(t), math.sin(t), 0]) for t in np.linspace(0, 2 * math.pi, 48)]
            pts = np.array([self._project(P, mats)[0] for P in ring])
            dd = np.min(np.linalg.norm(pts - m, axis=1))
            if dd < 8 and (best is None or dd < best[1]):
                best = (("rot", 2), dd)
        return best[0] if best else None

    def _axis_param(self, pos, o, axis):
        """Parameter des Punkts auf der Achse (o + t*axis), der dem Mausstrahl am naechsten liegt"""
        p0, d = self._ray(pos)
        w0 = o - p0
        a, b, c = axis @ axis, axis @ d, d @ d
        den = a * c - b * b
        if abs(den) < 1e-9:
            return 0.0
        return (b * (d @ w0) - c * (axis @ w0)) / den

    def _ring_angle(self, pos, o):
        p0, d = self._ray(pos)
        if abs(d[2]) < 1e-9:
            return 0.0
        t = (o[2] - p0[2]) / d[2]
        P = p0 + d * t - o
        return math.degrees(math.atan2(P[1], P[0]))

    def mousePressEvent(self, e):
        self._last = e.position()
        self._moved = False
        self._btn = e.button()
        self._drag = None
        self._drag_rot0 = None
        if e.button() != Qt.MouseButton.LeftButton:
            return
        if e.modifiers() & Qt.KeyboardModifier.ShiftModifier and self.mode in ("select", "move"):
            self._band = (e.position(), e.position())
            return
        h = self._hit_gizmo(e.position())
        if h:
            o, R, L = self._gizmo_frame()
            kind, i = h
            start = self._axis_param(e.position(), o, R[:, i]) if kind == "axis" else self._ring_angle(e.position(), o)
            self._drag = (kind, i, start, o.copy())
            return
        if self.mode == "pnp":
            obj, P = self.pick_point(e.position())
            if obj is not None and P is not None:
                self.selected = obj
                self._drag = ("plane", obj, P.copy(), np.array(obj.pos, float))

    def _apply_move(self, obj, newpos, rot=None):
        delta = np.asarray(newpos, float) - np.array(obj.pos, float)
        obj.pos = [float(v) for v in newpos]
        if rot is not None:
            obj.rot = [float(v) for v in rot]
        try:
            import editing
            if self.move_children:
                editing.update_hierarchy(self.sim)
            else:                                    # Kinder bleiben in der Welt stehen
                for c in self.sim.scene:
                    if getattr(c, "parent", None) == obj.name:
                        c.pos = [float(v) for v in np.array(c.pos) - delta]
                        editing.attach(self.sim, c, obj.name)
        except Exception:
            pass
        self.object_moved.emit(obj)

    def mouseMoveEvent(self, e):
        if self._last is None:
            return
        d = e.position() - self._last
        self._last = e.position()
        if abs(d.x()) + abs(d.y()) > 1:
            self._moved = True
        if self._band is not None:
            self._band = (self._band[0], e.position())
            self.update()
            return
        if self._drag is not None:
            kind = self._drag[0]
            if kind == "axis":
                _, i, t0, o0 = self._drag
                axis = np.eye(3)[:, i]
                delta = self._snap(self._axis_param(e.position(), o0, axis) - t0)
                if self.mode == "jog":
                    self._jog_tcp(o0 + axis * delta)
                elif self.selected is not None:
                    newp = o0.copy()
                    newp[i] += delta
                    self._apply_move(self.selected, newp)
            elif kind == "rot" and self.selected is not None:
                _, i, a0, o0 = self._drag
                da = self._ring_angle(e.position(), o0) - a0
                if self.snap_always:
                    da = round(da / 15.0) * 15.0
                if self._drag_rot0 is None:
                    self._drag_rot0 = list(self.selected.rot)
                b = self._drag_rot0
                self._apply_move(self.selected, self.selected.pos, [b[0] + da, b[1], b[2]])
            elif kind == "plane":
                _, obj, P0, pos0 = self._drag
                p0, dr = self._ray(e.position())
                if abs(dr[2]) > 1e-9:
                    t = (P0[2] - p0[2]) / dr[2]
                    newp = pos0 + (p0 + dr * t - P0)
                    self._apply_move(obj, [self._snap(newp[0]), self._snap(newp[1]), pos0[2]])
            self.update()
            return
        if self._btn == Qt.MouseButton.LeftButton:
            self.az -= d.x() * 0.4
            self.el = max(-85, min(85, self.el + d.y() * 0.4))
        else:
            az = math.radians(self.az)
            right = np.array([-math.sin(az), math.cos(az), 0])
            k = self.dist / 1000.0
            self.center += right * d.x() * k * 1.1
            self.center[2] += d.y() * k * 1.1
        self.update()

    def _jog_tcp(self, P):
        r = self.sim.active
        Tw = r.tcp_world()
        Tw[:3, 3] = P
        try:
            q = r.model.ik(inv(r.root) @ Tw @ inv(r.tool_mat()), r.q)
        except Exception:
            q = None
        if q is not None:
            r.q = q
            if hasattr(r, "update_sv"):
                r.update_sv()

    def mouseReleaseEvent(self, e):
        if self._band is not None:
            a, b = self._band
            self._band = None
            x0, x1 = sorted((a.x(), b.x()))
            y0, y1 = sorted((a.y(), b.y()))
            mats = self._matrices()
            sel = []
            for o in self.sim.scene:
                if not o.visible or o.kind == "group":
                    continue
                q, _ = self._project(np.array(o.pos, float), mats)
                if x0 <= q[0] <= x1 and y0 <= q[1] <= y1:
                    sel.append(o)
            self.selection = sel
            self.selected = sel[0] if sel else None
            self.selection_changed.emit(sel)
            self.picked.emit(self.selected)
            self._last = None
            self.update()
            return
        if self._drag is not None:
            if self._drag[0] == "plane" and self.mode == "pnp":
                try:
                    import editing
                    msg = editing.pnp(self.sim, self._drag[1])
                    if msg:
                        self.object_moved.emit(self._drag[1])
                        self.measured.emit({"text": msg})
                except Exception as ex:
                    self.measured.emit({"text": f"PnP: {ex}"})
            self._drag = None
            self._last = None
            self.update()
            return
        if not self._moved and e.button() == Qt.MouseButton.LeftButton:
            self._click(e)
        self._last = None

    def _click(self, e):
        m = self.mode
        if m in ("measure", "dim_linear", "dim_angle"):
            obj, P = self.pick_point(e.position())
            if P is None:
                return
            if e.modifiers() & Qt.KeyboardModifier.ControlModifier and obj is not None:
                P = np.array(obj.pos, float)                  # Strg: Objektursprung fangen
            self.pts.append(P)
            need = 3 if m == "dim_angle" else 2
            if len(self.pts) >= need:
                pts, self.pts = self.pts[:need], []
                if m == "measure":
                    d = pts[1] - pts[0]
                    self.measure_result = {"pts": pts, "dist": float(np.linalg.norm(d)), "d": d}
                    self.measured.emit({"text": f"Abstand {np.linalg.norm(d):.1f} mm  (dX {d[0]:.1f}, dY {d[1]:.1f}, dZ {d[2]:.1f})"})
                else:
                    try:
                        import editing
                        editing.add_dimension(self.sim, "linear" if m == "dim_linear" else "angle",
                                              [[float(v) for v in p] for p in pts])
                    except Exception as ex:
                        self.measured.emit({"text": f"Bemaßung: {ex}"})
            self.update()
            return
        obj = self._pick(e.position())
        if m in ("snap", "align", "attach"):
            if obj is not None and obj is not self.selected:
                self.target_picked.emit(m, obj)
            return
        if m == "interact":
            self.interacted.emit(obj)
            return
        if e.modifiers() & Qt.KeyboardModifier.ControlModifier and obj is not None:
            if obj in self.selection:
                self.selection.remove(obj)
            else:
                self.selection.append(obj)
        else:
            self.selection = [obj] if obj is not None else []
        self.selection_changed.emit(self.selection)
        self.picked.emit(obj)

    def wheelEvent(self, e):
        self.dist = max(300.0, min(30000.0, self.dist * (0.9 if e.angleDelta().y() > 0 else 1.1)))
        self.update()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape:
            self.pts = []
            self.measure_result = None
            self.update()
        super().keyPressEvent(e)

    # ------------------------------------------------ Overlays: Achsenkreuz, Messung, Bemassung, Traces
    def _draw_overlays_gl(self):
        if self._shadow:
            return
        glDisable(GL_LIGHTING)
        glDisable(GL_DEPTH_TEST)
        g = self._gizmo_frame()
        if g is not None:
            o, R, L = g
            glLineWidth(4)
            for i, c in enumerate(((0.93, 0.25, 0.25), (0.2, 0.8, 0.3), (0.2, 0.45, 1.0))):
                glColor4f(*c, 1)
                glBegin(GL_LINES)
                glVertex3f(*o)
                glVertex3f(*(o + R[:, i] * L))
                glEnd()
                self._sphere(o + R[:, i] * L, L * 0.07, (*c, 1))
            if self.mode == "move":
                glLineWidth(2.5)
                glColor4f(1.0, 0.78, 0.1, 1)
                glBegin(GL_LINE_LOOP)
                for t in np.linspace(0, 2 * math.pi, 64, endpoint=False):
                    glVertex3f(*(o + L * 0.8 * np.array([math.cos(t), math.sin(t), 0])))
                glEnd()
        if len(self.selection) > 1:
            for o in self.selection:
                if o is not None:
                    self._box(o.matrix(), o.size, hexrgb(theme.BRAND["accent"]), 1.0, wire=True)
        glLineWidth(2)
        for P in self.pts:
            self._sphere(P, max(6.0, self.dist * 0.004), (1, 0.55, 0.05, 1))
        if self.measure_result:
            a, b = self.measure_result["pts"]
            glColor4f(1, 0.55, 0.05, 1)
            glBegin(GL_LINES)
            glVertex3f(*a)
            glVertex3f(*b)
            glEnd()
        if self.show_dims:
            glColor4f(0.1, 0.12, 0.16, 1)
            for dm in getattr(self.sim, "dimensions", None) or []:
                glBegin(GL_LINE_STRIP)
                for P in dm.get("pts", []):
                    glVertex3f(*P)
                glEnd()
        rec = getattr(self.sim, "recorder", None)
        if self.show_traces and rec is not None:
            try:
                for r in self.sim.robots:
                    t, xyz = rec.series(r.name, "tcp")
                    if len(xyz) > 1:
                        glColor4f(0.95, 0.35, 0.6, 0.9)
                        glBegin(GL_LINE_STRIP)
                        for P in xyz[:: max(1, len(xyz) // 2000)]:
                            glVertex3f(*P)
                        glEnd()
            except Exception:
                pass
        glEnable(GL_DEPTH_TEST)
        glEnable(GL_LIGHTING)

    def _overlay_text(self):
        """Beschriftungen (Messwert, Bemassungen) und Auswahlrahmen per QPainter"""
        from PyQt6.QtGui import QPainter, QColor, QFont, QPen
        items = []
        if self.measure_result:
            a, b = self.measure_result["pts"]
            items.append(((a + b) / 2, f"{self.measure_result['dist']:.1f} mm"))
        for dm in (getattr(self.sim, "dimensions", None) or []) if self.show_dims else []:
            pts = [np.array(p, float) for p in dm.get("pts", [])]
            if dm.get("type") == "angle" and len(pts) == 3:
                u, v = pts[0] - pts[1], pts[2] - pts[1]
                ang = math.degrees(math.acos(np.clip(u @ v / max(np.linalg.norm(u) * np.linalg.norm(v), 1e-9), -1, 1)))
                items.append((pts[1], dm.get("label") or f"{ang:.1f}°"))
            elif len(pts) >= 2:
                items.append(((pts[0] + pts[1]) / 2, dm.get("label") or f"{np.linalg.norm(pts[1] - pts[0]):.1f} mm"))
        if not items and self._band is None:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        f = QFont()
        f.setPointSize(9)
        f.setBold(True)
        p.setFont(f)
        for P, txt in items:
            x, y, z = gluProject(*P, self._mv, self._pr, self._vp)
            if not 0 < z < 1:
                continue
            y = self.height() - y
            w = p.fontMetrics().horizontalAdvance(txt) + 12
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(6, 30, 68, 225))
            p.drawRoundedRect(int(x - w / 2), int(y - 11), w, 22, 6, 6)
            p.setPen(QColor("white"))
            p.drawText(int(x - w / 2), int(y - 11), w, 22, Qt.AlignmentFlag.AlignCenter, txt)
        if self._band is not None:
            a, b = self._band
            p.setPen(QPen(QColor(theme.BRAND["accent"]), 1, Qt.PenStyle.DashLine))
            p.setBrush(QColor(14, 116, 187, 40))
            p.drawRect(int(min(a.x(), b.x())), int(min(a.y(), b.y())), int(abs(a.x() - b.x())), int(abs(a.y() - b.y())))
        p.end()

    def view(self, name):
        self.az, self.el = {"front": (0, 5), "side": (90, 5), "top": (0, 89), "iso": (35, 25)}[name]
        self.update()

    def _pick(self, pos):
        w, h = self.width(), self.height()
        self.makeCurrent()
        self._camera()
        mv = glGetDoublev(GL_MODELVIEW_MATRIX)
        pr = glGetDoublev(GL_PROJECTION_MATRIX)
        vp = glGetIntegerv(GL_VIEWPORT)
        x, y = pos.x(), h - pos.y()
        p0 = np.array(gluUnProject(x, y, 0.0, mv, pr, vp))
        p1 = np.array(gluUnProject(x, y, 1.0, mv, pr, vp))
        d = (p1 - p0) / np.linalg.norm(p1 - p0)
        best, bt = None, 1e18
        for o in self.sim.scene:
            if not o.visible:
                continue
            M = o.matrix()
            Mi = inv(M)
            lo = (Mi @ np.array([*p0, 1]))[:3]
            ld = Mi[:3, :3] @ d
            hs = np.array(o.size) / 2
            c = np.array([0, 0, hs[2]]) if o.kind not in ("sensor", "spawner", "zone") else np.zeros(3)
            t = _ray_box(lo - c, ld, hs)
            if t is not None and t < bt:
                best, bt = o, t
        return best


def _ray_box(o, d, h):
    t0, t1 = -1e18, 1e18
    for i in range(3):
        if abs(d[i]) < 1e-12:
            if abs(o[i]) > h[i]:
                return None
        else:
            a, b = (-h[i] - o[i]) / d[i], (h[i] - o[i]) / d[i]
            if a > b:
                a, b = b, a
            t0, t1 = max(t0, a), min(t1, b)
            if t0 > t1:
                return None
    return t0 if t1 >= 0 else None
