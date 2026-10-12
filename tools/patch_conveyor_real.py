"""Realistische Foerdertechnik: Gurtfarbe, Fuesse, Kurvenfoerderer (Transport entlang Bogen)."""
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


patch("sim.py", [
    ('''KINDS = ("box", "cylinder", "mesh", "conveyor", "sensor", "spawner", "workpiece", "zone")''',
     '''KINDS = ("box", "cylinder", "mesh", "conveyor", "conveyor_arc", "sensor", "spawner", "workpiece", "zone")'''),
    ('''        self.visible = True
        self.alpha = 1.0''', '''        self.visible = True
        self.alpha = 1.0
        # Foerdertechnik
        self.belt_color = "#3b4048"     # Gurt
        self.frame_color = "#c3c9d1"    # Aluminiumprofil
        self.feet = 2                   # Fusspaare
        self.radius = 1000.0            # Kurvenfoerderer: Radius Bandmitte
        self.angle = 90.0               # Kurvenfoerderer: Winkel (Grad)
        self.turn_right = True'''),
    ('''"speed", "io", "interval", "max_parts", "mesh_path", "visible", "alpha")}''',
     '''"speed", "io", "interval", "max_parts", "mesh_path", "visible", "alpha",
                                           "belt_color", "frame_color", "feet", "radius", "angle", "turn_right")}'''),
    ('''    def top_z(self):''', '''    # Kurvenfoerderer: lokale Geometrie (Bandmitte startet im Ursprung Richtung +X)
    def arc_center(self):
        return np.array([0.0, -self.radius if self.turn_right else self.radius])

    def arc_local(self, p_world):
        """Weltpunkt -> (Abstand zur Bandmitte, Bogenwinkel Grad, lokaler Punkt) fuer Kurvenfoerderer"""
        L = (inv(self.matrix()) @ np.array([p_world[0], p_world[1], p_world[2], 1.0]))[:3]
        c = self.arc_center()
        v = L[:2] - c
        r = float(np.hypot(*v))
        if self.turn_right:
            th = math.degrees(math.atan2(v[0], v[1]))
        else:
            th = math.degrees(math.atan2(v[0], -v[1]))
        return r - self.radius, th, L

    def on_arc(self, p_world, margin=0.0):
        dr, th, L = self.arc_local(p_world)
        return abs(dr) <= self.size[1] / 2 + margin and -1.0 <= th <= self.angle + 1.0

    def top_z(self):'''),
    # Transport auf Kurvenfoerderern
    ('''        # Schwerkraft fuer lose Objekte''', '''        for b in self.scene:
            if b.kind != "conveyor_arc":
                continue
            active = (b.io == 0) or self.io.get_out(int(b.io))
            if not active:
                continue
            M = b.matrix()
            Mi = inv(M)
            c = b.arc_center()
            for o in self.scene:
                if o is b or o.attached or not o.graspable:
                    continue
                if abs(o.pos[2] - b.top_z()) > 3 or not b.on_arc(o.pos):
                    continue
                L = (Mi @ np.array([*o.pos, 1.0]))[:3]
                v = L[:2] - c
                r = max(float(np.hypot(*v)), 1.0)
                dphi = b.speed * dt / r * (-1 if b.turn_right else 1)
                cs, sn = math.cos(dphi), math.sin(dphi)
                v2 = np.array([cs * v[0] - sn * v[1], sn * v[0] + cs * v[1]])
                L[:2] = c + v2
                W = (M @ np.array([*L, 1.0]))[:3]
                o.pos[0], o.pos[1] = float(W[0]), float(W[1])
                o.rot[0] += math.degrees(dphi)
        # Schwerkraft fuer lose Objekte'''),
    ('''            if not (b.obstacle or b.kind == "conveyor"):
                continue''', '''            if b.kind == "conveyor_arc":
                if b.on_arc([o.pos[0], o.pos[1], b.pos[2]]):
                    z = max(z, b.top_z())
                continue
            if not (b.obstacle or b.kind == "conveyor"):
                continue'''),
])

# ---------------- Import: Materialfarben + Kurvenfoerderer
patch("vcmx_import.py", [
    ('''SKIP_NAMES = ''', '''STD_COLORS = {
    "white": "#f2f4f7", "black": "#1f2328", "blue": "#2563eb", "red": "#dc2626", "green": "#16a34a",
    "yellow": "#facc15", "orange": "#f97316", "grey": "#9ca3af", "gray": "#9ca3af", "blue_grey": "#64748b",
    "light_aqua": "#a5f3fc", "metal": "#b8bec6", "steel": "#9aa3ad", "aluminum": "#c3c9d1", "aluminium": "#c3c9d1",
    "ral7031": "#4e5754", "ral7035": "#cbd0cc", "ral9005": "#0e0e10", "ral1023": "#f7b500", "ral5015": "#2271b3",
    "transp_red": "#ef4444", "dark_grey": "#374151",
}


def _materials(text):
    """Materialtabelle der Datei: Name -> Hex-Farbe (Diffuse, sonst Ambient)"""
    out = {}
    for m in re.finditer(r'\\n\\s*Material\\s+"([^"]+)"\\s*\\n\\s*\\{([\\s\\S]{0,600}?)\\n\\s*\\}\\s*\\n', text):
        body = m.group(2)
        blk = re.search(r"Diffuse\\s*\\{([^}]*)\\}", body) or re.search(r"Ambient\\s*\\{([^}]*)\\}", body)
        if not blk:
            continue
        rgb = []
        for k in ("Red", "Green", "Blue"):
            mm = re.search(k + r"\\s+([-\\d.eE]+)", blk.group(1))
            rgb.append(float(mm.group(1)) if mm else 0.0)
        out[m.group(1)] = "#%02x%02x%02x" % tuple(int(max(0, min(1, c)) * 255) for c in rgb)
    return out


def _comp_material(comp):
    """Direkte Materialzuweisung einer Komponente (z. B. Material "SORT_ROT")"""
    for c in comp.walk():
        if c.k == "Material" and c.a:
            return unq(c.a)
    return None


def _color(name, mats, default):
    if not name:
        return default
    return mats.get(name) or STD_COLORS.get(name.lower()) or default


SKIP_NAMES = '''),
    ('''def _parametric(name, gk, v, M, scene, sensor_no):
    """Foerderer/Sensoren/Erzeuger aus Komponenten-Parametern"""
    f = lambda k, d=None: _num(v.get(k), d)
    if gk == "conveyor":
        H = f("ConveyorHeight", 800.0)
        W = f("ConveyorWidth", 600.0)
        if f("ConveyorRadius"):
            R = f("ConveyorRadius")
            side = -1 if str(v.get("TurnRight", "1")) == "1" else 1
            C = M @ pose_to_mat(0, side * R / 2, 0, 0, 0, 0)
            q = mat_to_pose(C)
            o = SceneObj(name, "box", q[:3], q[3:], [2 * R + W, R + W, H], "#475569", False, False)
            o.alpha = 0.6
            return o
        L = f("ConveyorLength", 1500.0)
        C = M @ pose_to_mat(L / 2, 0, 0, 0, 0, 0)
        q = mat_to_pose(C)
        o = SceneObj(name, "conveyor", q[:3], q[3:], [L, W, H], "#475569", True, False)
        o.speed = f("ConveyorSpeed", 250.0)
        o.io = 0
        return o''', '''def _parametric(name, gk, v, M, scene, sensor_no, color=None):
    """Foerderer/Sensoren/Erzeuger aus Komponenten-Parametern"""
    f = lambda k, d=None: _num(v.get(k), d)
    if gk == "conveyor":
        H = f("ConveyorHeight", 800.0)
        W = f("ConveyorWidth", 600.0)
        if f("ConveyorRadius"):
            q = mat_to_pose(M)
            o = SceneObj(name, "conveyor_arc", q[:3], q[3:], [0, W, H], "#c3c9d1", False, False)
            o.radius = f("ConveyorRadius")
            o.angle = f("ConveyorAngle", 90.0)
            o.turn_right = str(v.get("TurnRight", "1")).strip() in ("1", "True", "true")
            o.size[0] = 2 * o.radius + W
            o.speed = f("ConveyorSpeed", 250.0)
            o.feet = int(f("AmountOfFeet", 3) or 3)
            if color:
                o.belt_color = color
            return o
        L = f("ConveyorLength", 1500.0)
        C = M @ pose_to_mat(L / 2, 0, 0, 0, 0, 0)
        q = mat_to_pose(C)
        o = SceneObj(name, "conveyor", q[:3], q[3:], [L, W, H], "#c3c9d1", True, False)
        o.speed = f("ConveyorSpeed", 250.0)
        o.feet = int(f("AmountOfFeet", 2) or 2)
        if color:
            o.belt_color = color
        o.io = 0
        return o'''),
    ('''            o = _parametric(name, gk, v, M, new_scene, sensor_no)''',
     '''            o = _parametric(name, gk, v, M, new_scene, sensor_no, _color(_comp_material(comp), mats, None))'''),
    ('''    root = parse(text)
    gen_limits''', '''    root = parse(text)
    mats = _materials(text)
    if mats:
        log.append(f"Materialien/Farben übernommen: {', '.join(list(mats)[:12])}")
    gen_limits'''),
    # Grundkoerper und Platzhalter einfaerben
    ('''                o = SceneObj(f"{name}/{pname}" if len(prims) > 1 else name, kind, q[:3], q[3:], size, "#94a3b8", True, False)''',
     '''                o = SceneObj(f"{name}/{pname}" if len(prims) > 1 else name, kind, q[:3], q[3:], size,
                             _color(_comp_material(comp), mats, "#94a3b8"), True, False)'''),
    ('''            o = SceneObj(name, kind, p[:3], p[3:], size, "#64748b", kind in ("box", "conveyor"), kind == "workpiece")''',
     '''            o = SceneObj(name, kind, p[:3], p[3:], size, _color(_comp_material(comp), mats, "#64748b"),
                         kind in ("box", "conveyor"), kind == "workpiece")'''),
])
print("ok")
