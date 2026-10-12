"""Mehrere Roboter + Linearachse: Interpreter, Katalog, Viewer anpassen."""
import os
B = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "ximaj_robosim")


def patch(fn, pairs):
    p = os.path.join(B, fn)
    m = open(p, encoding="utf8").read()
    for a, b in pairs:
        if a not in m:
            raise SystemExit(f"{fn}: NICHT GEFUNDEN:\n{a[:300]}")
        m = m.replace(a, b, 1)
    open(p, "w", encoding="utf8").write(m)


patch("xrl.py", [
    ('''            if keys & set(AX_KEYS):
                cur = [0] * 6 if rel else self.sv.get("AXIS_ACT", [0] * 6)
                return ("axis", [v.get(a, cur[i]) for i, a in enumerate(AX_KEYS)])
            cur = [0] * 6 if rel else self.sv.get("POS_ACT", [0] * 6)
            return ("pos", [v.get(a, cur[i]) for i, a in enumerate(POS_KEYS)], v.get("S"), v.get("T"))''',
     '''            e1 = v.get("E1")
            if keys & set(AX_KEYS):
                cur = [0] * 6 if rel else self.sv.get("AXIS_ACT", [0] * 6)
                return ("axis", [v.get(a, cur[i]) for i, a in enumerate(AX_KEYS)], e1)
            cur = [0] * 6 if rel else self.sv.get("POS_ACT", [0] * 6)
            return ("pos", [v.get(a, cur[i]) for i, a in enumerate(POS_KEYS)], v.get("S"), v.get("T"), e1)'''),
])

patch("catalog.py", [
    ('''    if k == "cell":
        sim.set_model(entry["data"]["model"])''', '''    if k == "cell":
        if hasattr(sim, "clear_robots"):
            sim.clear_robots()
        sim.set_model(entry["data"]["model"])'''),
])

patch("viewer.py", [
    # alle Roboter zeichnen (Normal- und Schattendurchlauf)
    ('''        if self.shadows:
            self._shadow_pass()
        self._draw_robot()
        self._draw_scene()''', '''        if self.shadows:
            self._shadow_pass()
        self._draw_robots()
        self._draw_scene()'''),
    ('''        try:
            self._draw_robot()
            self._draw_scene()''', '''        try:
            self._draw_robots()
            self._draw_scene()'''),
    ('''            self._draw_axes(self.sim.tcp_world(), 120)
            self._draw_axes(self.sim.root, 200, 0.5)
            self._draw_axes(self.sim.base_world(), 150, 0.4)''', '''            for r in self.sim.robots:
                self._draw_axes(r.tcp_world(), 120, 1.0 if r is self.sim.active else 0.45)
                self._draw_axes(r.robroot(), 200, 0.5)
            self._draw_axes(self.sim.base_world(), 150, 0.4)'''),
    ('''    def _draw_robot(self):
        sim = self.sim
        m = sim.model
        collided = bool(sim.collision)''', '''    def _draw_robots(self):
        for r in self.sim.robots:
            if r.track is not None:
                self._draw_track(r)
            self._draw_robot(r)

    def _draw_track(self, r):
        """Linearachse: Bodenschiene mit Zahnstange und Schlitten"""
        L = r.track["length"]
        s = r.model.reach / 1000.0
        w = max(380.0, r.model.reach * 0.32)
        frame = (0.34, 0.37, 0.42)
        rail = (0.78, 0.8, 0.84)
        M = r.root
        self._lbox(M, (L / 2, 0, 60), (L + w, w, 120), frame)
        for sy in (-1, 1):
            self._lbox(M, (L / 2, sy * w * 0.32, 130), (L + w * 0.8, 40, 22), rail)
        self._lbox(M, (L / 2, 0, 124), (L + w * 0.8, 24, 10), (0.2, 0.22, 0.25))
        # Schlitten unter dem Roboter
        self._lbox(r.robroot(), (0, 0, -18), (w * 0.95, w * 1.05, 36), hexrgb(theme.BRAND["robot"]))
        # Endanschlaege
        for x in (-w * 0.45, L + w * 0.45):
            self._lbox(M, (x, 0, 150), (30, w * 0.9, 60), (0.95, 0.75, 0.1))

    def _draw_robot(self, r=None):
        sim = r or self.sim.active
        m = sim.model
        collided = bool(sim.collision)'''),
    ('''        f = [sim.root @ x for x in m.frames(sim.q)]''', '''        f = [sim.robroot() @ x for x in m.frames(sim.q)]'''),
    ('''        self._box(sim.root, (rb * 2.6, rb * 2.6, 18 * s + 8), dark)''', '''        self._box(sim.robroot(), (rb * 2.6, rb * 2.6, 18 * s + 8), dark)'''),
    ('''        self._draw_tool(f[6])''', '''        self._draw_tool(f[6], sim)'''),
    ('''    def _draw_tool(self, F):
        sim = self.sim
        t = sim.tool''', '''    def _draw_tool(self, F, sim=None):
        sim = sim or self.sim.active
        t = sim.tool'''),
    ('''        t = self.sim.trail
        if len(t) < 2:
            return''', '''        for r in self.sim.robots:
            self._draw_one_trail(r.trail)

    def _draw_one_trail(self, t):
        if len(t) < 2:
            return'''),
])
print("ok")
