import os, re
B = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "ximaj_robosim")


def patch(fn, pairs):
    p = os.path.join(B, fn)
    m = open(p, encoding="utf8").read()
    for a, b in pairs:
        if a not in m:
            raise SystemExit(f"{fn}: NICHT GEFUNDEN:\n{a[:300]}")
        m = m.replace(a, b, 1)
    open(p, "w", encoding="utf8").write(m)


patch("sim.py", [('''         "drawing")''', '''         "drawing", "fence")''')])

patch("viewer.py", [
    ('''            elif o.kind == "drawing":''', '''            elif o.kind == "fence":
                self._draw_fence(o, M)
            elif o.kind == "drawing":'''),
    ('''    def _draw_process(self, res):''', '''    def _draw_fence(self, o, M):
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

    def _draw_process(self, res):'''),
])

p = os.path.join(B, "catalog.py")
m = open(p, encoding="utf8").read()
m = re.sub(r'O\("(Zaun[^"]*)", "box"', r'O("\1", "fence"', m)
open(p, "w", encoding="utf8").write(m)

patch("copilot.py", [
    ('''            o = SceneObj(nm, "box", pos, (0, 0, 0), size, "#f5b83d", True, False)
            o.alpha = 0.28''', '''            o = SceneObj(nm, "fence", pos, (0, 0, 0), size, "#f5b83d", True, False)'''),
    ('''        sim.speed_factor = f
        return f"Simulationszeit {f:g}×."''', '''        sim.speed_factor = f
        if win.spd.findText(f"{f:g}x") >= 0:
            win.spd.setCurrentText(f"{f:g}x")
        return f"Simulationszeit {f:g}×."'''),
    ('''            return f"{name} bei X {pos[0]:.0f}, Y {pos[1]:.0f} eingefügt" + (f" (Länge {L / 1000:g} m)." if L else ".")''',
     '''            label = name.split(" ")[0] if L else name
            return f"{label} bei X {pos[0]:.0f}, Y {pos[1]:.0f} eingefügt" + (f" (Länge {L / 1000:g} m)." if L else ".")'''),
    ('''                if L and o.kind in ("conveyor", "box") and''', '''                if L and o.kind in ("conveyor", "box", "fence") and'''),
])
patch("vcmx_import.py", [
    ('''            kind = {"fence": "box", "spawner": "spawner"}.get(gk, gk if gk in ("conveyor", "sensor", "workpiece") else "box")''',
     '''            kind = {"fence": "fence", "spawner": "spawner"}.get(gk, gk if gk in ("conveyor", "sensor", "workpiece") else "box")'''),
    ('''            if gk == "fence":
                o.alpha, o.color = 0.3, "#f5b83d"''', '''            if gk == "fence":
                o.color = "#f5b83d"
                o.size[2] = o.size[2] if o.size[2] > 500 else 1800.0'''),
])
print("ok")
