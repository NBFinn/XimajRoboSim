"""Simulationskern der Ximaj RoboSim.

Aufbau:
  Simulation (Halle/Welt)  – Szene, E/A-Bus, Physik (Foerderer, Schwerkraft, Sensoren, Erzeuger, Senken),
                             Zeit, Meldungen, Sicherheitszonen, Durchsatz, mehrere Roboter
  Robot (Steuerung)        – Kinematik, Linearachse E1, Programm/Interpreter, Bewegungsplanung, Greifer,
                             Kollision, Taktzeit, Energie
Die Simulation leitet unbekannte Attribute an den *aktiven* Roboter weiter (sim.q, sim.state, sim.start() ...),
so dass Oberflaeche, OPC UA und Import mit dem aktiven Roboter arbeiten.
"""
import json
import copy
import math
import random
import re
import threading
import time
import numpy as np

from kinematics import (MODELS, HOME, D2R, R2D, pose_to_mat, mat_to_pose, inv, rx, ry, rz, tr)
from xrl import Interp, XrlError


# ------------------------------------------------------------------ E/A
class IO:
    N = 4097

    @staticmethod
    def is_virtual(n):
        return 1024 < n < IO.N

    def __init__(self):
        self.inp = [False] * self.N
        self.out = [False] * self.N
        self.lock = threading.Lock()
        self.names = {}            # E/A-Mapping: ("in"|"out", nr) -> Name

    def get_in(self, n):
        return self.inp[n] if 0 < n < self.N else False

    def get_out(self, n):
        return self.out[n] if 0 < n < self.N else False

    def set_out(self, n, v):
        if 0 < n < self.N:
            self.out[n] = bool(v)

    def set_in(self, n, v):
        if 0 < n < self.N:
            self.inp[n] = bool(v)


# ------------------------------------------------------------------ Szene
KINDS = ("box", "cylinder", "mesh", "conveyor", "conveyor_arc", "sensor", "spawner", "sink", "workpiece", "zone",
         "drawing", "fence", "color_sensor", "lamp", "group")

SIGNAL_COLORS = {
    "ROT": (1., 0., 0.), "GRUEN": (0., 1., 0.), "BLAU": (0., 0., 1.),
    "GELB": (1., 1., 0.), "WEISS": (1., 1., 1.), "SCHWARZ": (0., 0., 0.),
    "ORANGE": (1., .5, 0.), "GRAU": (.5, .5, .5), "VIOLETT": (.5, 0., 1.),
}

def signal_color(name):
    key = name.upper().replace("Ü", "UE").replace("ß", "SS")
    key = {"RED": "ROT", "GREEN": "GRUEN", "BLUE": "BLAU", "YELLOW": "GELB",
           "WHITE": "WEISS", "BLACK": "SCHWARZ", "GRAY": "GRAU", "GREY": "GRAU"}.get(key, key)
    return SIGNAL_COLORS.get(key)

def color_rgb(color):
    if isinstance(color, str):
        return tuple(int(color[i:i + 2], 16) / 255 for i in (1, 3, 5))
    return tuple(color)


def _mirrored(mesh, axes):
    """Netz an den angegebenen Achsen spiegeln (Dreiecksumlauf bleibt nach aussen gerichtet)"""
    V, F = np.array(mesh[0], float), np.array(mesh[1])
    for ax in axes or []:
        V[:, int(ax)] *= -1
        F = F[:, ::-1]
    return V, F


def prim_mesh(kind, size):
    """Netz eines Quaders/Zylinders mit Ursprung unten in der Mitte"""
    import trimesh
    sx, sy, sz = size
    m = trimesh.creation.box(extents=(sx, sy, sz)) if kind == "box" else         trimesh.creation.cylinder(radius=sx / 2, height=sz, sections=48)
    m.apply_translation((0, 0, sz / 2))
    return np.asarray(m.vertices, float), np.asarray(m.faces, int)


# Detaildarstellung fuer Projekte, die vor dem Feld "style" gespeichert wurden (Katalognamen)
_STYLE_NAMES = (("palette", "box", "pallet"), ("schaltschrank", "box", "cabinet"), ("tisch", "box", "table"),
                ("gitterbox", "box", "gitterbox"), ("regal", "box", "shelf"), ("sockel", "box", "pedestal"),
                ("karton", "workpiece", "carton"), ("vorrichtung", "box", "fixture"), ("säule", "cylinder", "column"),
                ("rollenbahn", "conveyor", "roller"))


def guess_style(name, kind):
    n = str(name).lower()
    return next((st for key, k, st in _STYLE_NAMES if k == kind and key in n), "")


class SceneObj:
    def __init__(self, name, kind="box", pos=(0, 0, 0), rot=(0, 0, 0), size=(200, 200, 200),
                 color="#8a9bb8", obstacle=True, graspable=False):
        self.name, self.kind = name, kind
        self.pos = list(map(float, pos))
        self.rot = list(map(float, rot))        # A,B,C Grad
        self.size = list(map(float, size))      # Box: x,y,z ; Zylinder: d,d,h
        self.color = color
        self.obstacle = obstacle
        self.graspable = graspable
        self.speed = 200.0       # Foerderband mm/s
        self.io = 0              # Foerderband: Ausgang (0=immer an) | Sensor: Eingang | Spawner/Senke: Freigabe-Ausgang
        self.interval = 4.0
        self.max_parts = 20
        self.part_size = [60.0, 40.0, 40.0]
        self.part_color = "#f5b83d"
        self.mesh = None         # (verts Nx3, faces Mx3) lokal
        self.mesh_path = ""
        self.mesh_max_tris = 200000
        self.mesh_offset = [0., 0., 0.]
        self.prim = ""                 # Grundform eines in ein Netz umgewandelten Quaders/Zylinders
        self.mesh_mirror = []          # gespiegelte Achsen (0=X, 1=Y) eines Netzes
        self.style = ""                # Detaildarstellung (part_geom), z. B. "pallet", "cabinet", "roller"
        self.parent = None
        self.local = None
        self.lines = []          # DXF-Grundriss: Liste (N,2) lokal
        self.attached = False
        self.attached_to = None  # Robotername
        self.rel = None          # Transform relativ zum TCP bei Greifen
        self.visible = True
        self.alpha = 1.0
        # Foerdertechnik
        self.belt_color = "#3b4048"
        self.frame_color = "#c3c9d1"
        self.feet = 2
        self.radius = 1000.0
        self.angle = 90.0
        self.turn_right = True
        self.timer = 0.0
        self.spawned = 0
        self.consumed = 0
        self.trigger = 0
        self.color_outs = {}
        self.detected = 0
        self.inputs = {}
        self.colors = []
        self.lit_color = None
        self._trigger_high = False
        self.scripted = False
        self.vc_data = {}
        self.product_templates = []
        self.vc_component = name

    def matrix(self):
        key = tuple(self.pos) + tuple(self.rot)
        if getattr(self, '_matrix_key', None) != key:
            self._matrix_key = key
            self._matrix_cache = pose_to_mat(*self.pos, *self.rot)
            self._inverse_cache = inv(self._matrix_cache)
        return self._matrix_cache.copy()

    def inverse_matrix(self):
        self.matrix()
        return self._inverse_cache.copy()

    def half(self):
        s = self.size
        return np.array([s[0] / 2, s[1] / 2, s[2] / 2])

    FIELDS = ("name", "kind", "pos", "rot", "size", "color", "obstacle", "graspable", "speed", "io", "interval",
              "max_parts", "part_size", "part_color", "mesh_path", "mesh_max_tris", "visible", "alpha", "belt_color",
              "frame_color",
              "feet", "radius", "angle", "turn_right", "trigger", "color_outs", "detected", "inputs", "colors",
              "vc_data", "product_templates", "vc_component", "parent", "local", "mesh_offset", "prim", "mesh_mirror", "style")

    def to_dict(self):
        return {k: getattr(self, k) for k in self.FIELDS}

    @staticmethod
    def from_dict(d):
        o = SceneObj(d["name"], d["kind"])
        for k, v in d.items():
            if k in SceneObj.FIELDS:
                setattr(o, k, v)
        if "style" not in d:                     # Projekt aus der Zeit vor dem Feld "style"
            o.style = guess_style(o.name, o.kind)
        if o.mesh_path:
            try:
                if o.kind == "drawing":
                    o.load_dxf(o.mesh_path, keep_pos=True)
                else:
                    offset = list(o.mesh_offset)
                    o.load_mesh(o.mesh_path, o.mesh_max_tris, keep_size=True)
                    o.mesh_offset = offset
                    o.mesh = (_mirrored(o.mesh, o.mesh_mirror)[0] - np.asarray(offset), _mirrored(o.mesh, o.mesh_mirror)[1])
            except Exception:
                pass
        elif o.prim and o.kind == "mesh":
            V, F = _mirrored(prim_mesh(o.prim, o.size), o.mesh_mirror)
            o.mesh = (V - np.asarray(o.mesh_offset, float), F)
        return o

    def load_mesh(self, path, max_tris=200000, keep_size=False):
        """CAD-Datei laden (STEP/IGES/STL/OBJ/PLY/GLB/3MF), Einheit mm, Unterseite auf Z=0"""
        import cad
        V, F = cad.load_cad(path, max_tris=max_tris)
        self.mesh = (V, F)
        self.mesh_offset = [0., 0., 0.]
        self.mesh_path = path
        self.mesh_max_tris = max_tris
        ext = V.max(axis=0) - V.min(axis=0)
        if not keep_size:
            self.size = [float(ext[0]), float(ext[1]), float(ext[2])]
        self.kind = "mesh"

    def simplify_mesh(self, target_tris):
        import cad
        if self.mesh is not None:
            self.mesh = cad.simplify(self.mesh[0], self.mesh[1], target_tris)
            self.mesh_max_tris = int(target_tris)
            self._glcache = None

    def load_dxf(self, path, keep_pos=False):
        import cad
        lines, lo, hi = cad.load_dxf(path)
        c = (lo + hi) / 2
        self.lines = [l - c for l in lines]
        self.mesh_path = path
        self.kind = "drawing"
        self.size = [float(hi[0] - lo[0]), float(hi[1] - lo[1]), 1.0]
        self.obstacle = False
        if not keep_pos:
            self.pos = [float(c[0]), float(c[1]), 0.0]

    # Kurvenfoerderer: lokale Geometrie (Bandmitte startet im Ursprung Richtung +X)
    def arc_center(self):
        return np.array([0.0, -self.radius if self.turn_right else self.radius])

    def arc_local(self, p_world):
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

    def top_z(self):
        return self.pos[2] + self.size[2]


class Tool:
    def __init__(self, name="Greifer", tcp=(0, 0, 120, 0, 0, 0), grip_out=1, length=120.0, radius=20.0, grip_range=60.0):
        self.name = name
        self.tcp = list(tcp)
        self.grip_out = grip_out
        self.length = length
        self.radius = radius
        self.grip_range = grip_range

    def matrix(self):
        return pose_to_mat(*self.tcp)

    def to_dict(self):
        return dict(self.__dict__)


# ------------------------------------------------------------------ Geometrie-Helfer
def seg_seg_dist(p1, q1, p2, q2):
    d1, d2, r = q1 - p1, q2 - p2, p1 - p2
    a, e, f = d1 @ d1, d2 @ d2, d2 @ r
    if a < 1e-9 and e < 1e-9:
        return float(np.linalg.norm(r))
    if a < 1e-9:
        s, t = 0.0, np.clip(f / e, 0, 1)
    else:
        c = d1 @ r
        if e < 1e-9:
            t, s = 0.0, np.clip(-c / a, 0, 1)
        else:
            b = d1 @ d2
            den = a * e - b * b
            s = np.clip((b * f - c * e) / den, 0, 1) if den > 1e-9 else 0.0
            t = (b * s + f) / e
            if t < 0:
                t, s = 0.0, np.clip(-c / a, 0, 1)
            elif t > 1:
                t, s = 1.0, np.clip((b - c) / a, 0, 1)
    return float(np.linalg.norm((p1 + d1 * s) - (p2 + d2 * t)))


def pts_box_dist(pts, M, half):
    """Abstand von Punkten (Nx3) zu OBB (Matrix M, Halbmasse half); negativ = innen"""
    L = (inv(M) @ np.c_[pts, np.ones(len(pts))].T).T[:, :3]
    q = np.abs(L) - half
    out = np.linalg.norm(np.maximum(q, 0), axis=1)
    ins = np.minimum(np.max(q, axis=1), 0)
    return out + ins


# ------------------------------------------------------------------ Bewegung
class Motion:
    """Skalare Bahnparametrisierung s in [0,L] mit v/a-Begrenzung. qfun(s)->q, efun(s)->E1"""

    def __init__(self, kind, L, vmax, acc, qfun, target=None, efun=None, e_target=None):
        self.kind, self.L, self.vmax, self.acc = kind, max(L, 1e-9), max(vmax, 1e-9), max(acc, 1e-9)
        self.qfun = qfun
        self.efun = efun
        self.e_target = e_target
        self.s, self.v = 0.0, 0.0
        self.done = False
        self.target = target
        self.stopped = False

    def step(self, dt, ovr, decel=None):
        vm = self.vmax * ovr
        if decel:
            self.v = max(self.v - decel * dt, 0.0)
            self.s = min(self.s + self.v * dt, self.L)
            if self.v <= 1e-9:
                self.stopped = True
            return self.qfun(self.s), self.stopped
        rem = self.L - self.s
        vallow = math.sqrt(max(2 * self.acc * ovr * rem, 0.0))
        self.v = min(self.v + self.acc * ovr * dt, vm, max(vallow, 0.02 * vm))
        self.s = min(self.s + self.v * dt, self.L)
        if self.L - self.s < 1e-6:
            self.done = True
        return self.qfun(self.s), self.done


class PlanError(Exception):
    pass


# ------------------------------------------------------------------ Roboter (Steuerung)
class Robot:
    """Eine Robotersteuerung mit Kinematik, optionaler Linearachse (E1) und eigenem Programm."""

    def __init__(self, world, name="Roboter 1", model_key="XR-9 (0.9 m, 6 kg)"):
        self.w = world
        self.name = name
        self.model_key = model_key if model_key in MODELS else "XR-9 (0.9 m, 6 kg)"
        self.model = MODELS[self.model_key]
        self.root = np.eye(4)                      # Roboterfuss (bzw. Linearachsen-Nullpunkt) in Welt
        self.root_pose = [0, 0, 0, 0, 0, 0]
        self.base = [0, 0, 0, 0, 0, 0]             # $BASE relativ zum Roboterfuss
        self.tool = Tool()
        self.q = HOME.copy()
        self.e1 = 0.0                              # Linearachse (mm)
        self.track = None                          # {"min": mm, "max": mm, "vmax": mm/s, "name": str}
        self.sv = {"VEL_CP": 2.0, "ACC_CP": 2.3, "VEL_ORI1": 200.0, "ACC_ORI1": 1500.0, "APO_CDIS": 0.0,
                   "POS_ACT": [0] * 6, "AXIS_ACT": list(HOME), "TOOL": {}, "BASE": {}}
        self.src = DEFAULT_PROGRAM
        self.interp = None
        self.gen = None
        self.state = "idle"
        self.step_mode = False
        self.breakpoints = set()
        self._paused_state = 'running'
        self._pause_at = None
        self.wait_started = None
        self.motion = None
        self.wait_until = None
        self.wait_fn = None
        self.pulses = []
        self.cur_line = 0
        self.run_t = 0.0
        self.collision = None
        self.near_limits = set()
        self.safety_msg = ""
        self.stop_dist = None
        self.trail = []
        self.cycle_times = []
        self._last_tick = None
        self.line_time = {}
        self.energy_wh = 0.0
        self.power_w = 0.0
        self._last_u = None
        self.waypoints = []
        self.statements = []                       # Statement-Programm (Bausteine)
        self.mode = "xrl"                          # "xrl" | "statements"
        self.stmt_linemap = {}
        self.tool_table = {}
        self.base_table = {}
        self.pending_stop = None
        self.prev_grip = False
        self.q_prev_frame = self.q.copy()
        self.update_sv()

    # ---- Weltbezug
    scene = property(lambda self: self.w.scene)
    io = property(lambda self: getattr(self, "_signal_io", self.w.io))
    t = property(lambda self: self.w.t)
    override = property(lambda self: self.w.override)
    safety = property(lambda self: self.w.safety)
    stop_on_collision = property(lambda self: self.w.stop_on_collision)
    imported_models = property(lambda self: self.w.imported_models)

    def say(self, m):
        self.w.say(m if len(self.w.robots) < 2 else f"{self.name}: {m}")

    # ---- Konfiguration
    def set_model(self, key):
        self.model_key = key
        self.model = MODELS[key]
        self.q = np.clip(HOME, self.model.limits[:, 0], self.model.limits[:, 1])
        self.reset()

    def set_root(self, pose):
        self.root_pose = list(map(float, pose))
        self.root = pose_to_mat(*pose)

    def set_track(self, length=None, vmax=1500.0, name="Linearachse", e_min=None, e_max=None, lift=False):
        """Linearachse E1 entlang der X-Achse des Roboterfusses. length=None und keine Grenzen -> keine Achse"""
        if not length and e_min is None and e_max is None:
            self.track, self.e1 = None, 0.0
        else:
            lo = float(e_min if e_min is not None else 0.0)
            hi = float(e_max if e_max is not None else lo + float(length))
            if lift and self.track is None and self.root_pose[2] < 250.0:   # Roboter auf die Schiene stellen
                self.set_root([self.root_pose[0], self.root_pose[1], 250.0] + list(self.root_pose[3:]))
            self.track = {"min": lo, "max": hi, "vmax": float(vmax), "name": name}
            self.e1 = float(np.clip(self.e1, lo, hi))
        self.update_sv()

    def e_limits(self):
        if self.track is None:
            return 0.0, 0.0
        if "min" not in self.track:          # aelteres Format
            self.track = {"min": 0.0, "max": self.track.get("length", 0.0), "vmax": self.track.get("vmax", 1500.0),
                          "name": self.track.get("name", "Linearachse")}
        return self.track["min"], self.track["max"]

    @staticmethod
    def _frame_from_sv(v):
        if isinstance(v, dict) and any(k in v for k in ("X", "Y", "Z", "A", "B", "C")):
            return pose_to_mat(*[float(v.get(k, 0)) for k in ("X", "Y", "Z", "A", "B", "C")])
        return None

    def tool_mat(self):
        m = self._frame_from_sv(self.sv.get("TOOL")) if self.state != "idle" else None
        return m if m is not None else self.tool.matrix()

    def base_mat(self):
        m = self._frame_from_sv(self.sv.get("BASE")) if self.state != "idle" else None
        return m if m is not None else pose_to_mat(*self.base)

    def frame_tables(self):
        keys = ("X", "Y", "Z", "A", "B", "C")
        td = [dict(zip(keys, [0.0] * 6)) for _ in range(17)]
        bd = [dict(zip(keys, [0.0] * 6)) for _ in range(33)]
        for n, t in self.tool_table.items():
            if 0 <= int(n) < 17:
                td[int(n)] = dict(zip(keys, map(float, t["frame"])))
        for n, t in self.base_table.items():
            if 0 <= int(n) < 33:
                bd[int(n)] = dict(zip(keys, map(float, t["frame"])))
        return {"TOOL_DATA": td, "BASE_DATA": bd}

    # ---- Koordinaten
    def carriage(self, e1=None):
        """Lage des Roboterfusses (Schlitten) relativ zum Linearachsen-Nullpunkt"""
        return tr(self.e1 if e1 is None else e1, 0, 0)

    def robroot(self, e1=None):
        return self.root @ self.carriage(e1)

    def flange_world(self, q=None, e1=None):
        return self.robroot(e1) @ self.model.fk(self.q if q is None else q)

    def tcp_world(self, q=None):
        return self.flange_world(q) @ self.tool_mat()

    def base_world(self):
        """$BASE gilt relativ zum Roboterfuss bzw. Linearachsen-Nullpunkt (Roboter-Welt)."""
        return self.root @ self.base_mat()

    def tcp_in_base(self, q=None):
        return inv(self.base_world()) @ self.tcp_world(q)

    def update_sv(self):
        p = mat_to_pose(self.tcp_in_base())
        self.sv["POS_ACT"] = [float(x) for x in p]
        self.sv["AXIS_ACT"] = [float(x) for x in self.q]
        self.sv["E1_ACT"] = float(self.e1)
        s, t = self.model.status_turn(self.q)
        self.sv["POS_ACT_S"], self.sv["POS_ACT_T"] = s, t

    # ---- Planung
    def _e_target(self, tgt):
        """E1 aus Ziel (5. Element) oder unveraendert"""
        if self.track is None:
            return self.e1
        e = tgt[4] if tgt[0] == "pos" and len(tgt) > 4 else (tgt[2] if tgt[0] == "axis" and len(tgt) > 2 else None)
        if e is None:
            return self.e1
        return float(np.clip(float(e), *self.e_limits()))

    def target_root(self, tgt):
        """Ziel -> Flanschmatrix im Linearachsen-/Fuss-System (ohne Schlitten)"""
        return self.base_mat() @ pose_to_mat(*tgt[1][:6]) @ inv(self.tool_mat())

    def target_flange_robot(self, tgt, e1=None):
        """Ziel ('pos',...)-> Flanschmatrix im Roboter-Koordinatensystem (Schlitten bei e1)."""
        e = self.e1 if e1 is None else e1
        return inv(self.carriage(e)) @ self.target_root(tgt)

    def plan_ptp(self, tgt, rel=False):
        e0 = self.e1
        e1 = self._e_target(tgt)
        if tgt[0] == "axis":
            q1 = np.array(tgt[1][:6], float)
            if rel:
                q1 = self.q + q1
                if self.track is not None and len(tgt) > 2 and tgt[2] is not None:
                    e1 = float(np.clip(e0 + float(tgt[2]), *self.e_limits()))
        else:
            tg = tgt
            if rel:
                cur = np.array(self.sv["POS_ACT"])
                tg = ("pos", list(cur + np.array(tgt[1][:6])), tgt[2], tgt[3])
            T = self.target_flange_robot(tg, e1)
            st = (tg[2], tg[3]) if tg[2] is not None and tg[3] is not None else None
            q1 = self.model.ik(T, self.q, st)
            if q1 is None:
                raise PlanError("Ziel nicht erreichbar (ausserhalb Reichweite/Achsgrenzen)")
        if not self.model.in_limits(q1):
            raise PlanError("Zielachswinkel ausserhalb der Achsgrenzen")
        q0 = self.q.copy()
        dq = q1 - q0
        ad = np.abs(dq)
        de = e1 - e0
        if ad.max() < 1e-6 and abs(de) < 1e-6:
            return Motion("ptp", 1e-6, 1, 1, lambda s: q1, target=q1, e_target=e1)
        pct = self.sv.get("VEL_AXIS_PCT", 1.0)
        lim = [self.model.vmax[i] * pct / ad[i] for i in range(6) if ad[i] > 1e-6]
        if self.track is not None and abs(de) > 1e-6:
            lim.append(self.track["vmax"] * pct / abs(de))
        vmax = float(min(lim))
        acc = vmax / 0.25
        efun = (lambda s: e0 + de * s) if abs(de) > 1e-9 else None
        return Motion("ptp", 1.0, vmax, acc, lambda s: q0 + dq * s, target=q1, efun=efun, e_target=e1)

    def _cart_motion(self, kind, Tpath, L, ang, e0=None, e1=None):
        """Tpath: s(0..1)->Flanschmatrix im Fuss-/Achsensystem. Mit E1 wird der Schlitten mitgefahren."""
        e0 = self.e1 if e0 is None else e0
        e1 = e0 if e1 is None else e1
        n = int(max(8, min(600, L / 4.0, 600)))
        n = max(n, int(ang / 1.5), int(abs(e1 - e0) / 8.0), 8)
        qs = [self.q.copy()]
        es = [e0]
        for i in range(1, n + 1):
            u = i / n
            e = e0 + (e1 - e0) * u
            T = inv(self.carriage(e)) @ Tpath(u)
            q = self.model.ik(T, qs[-1])
            if q is None:
                raise PlanError(f"{kind.upper()}: Bahn verlaesst den Arbeitsraum bei {100 * i // n}%")
            if np.max(np.abs(q - qs[-1])) > 40.0:
                raise PlanError(f"{kind.upper()}: Singularitaet / Achssprung bei {100 * i // n}%")
            qs.append(q)
            es.append(e)
        qs = np.array(qs)
        es = np.array(es)
        vcp = self.sv["VEL_CP"] * 1000.0
        acc = max(self.sv["ACC_CP"], 0.05) * 1000.0
        vori = self.sv.get("VEL_ORI1", 200.0)
        if ang > 1e-6 and L > 1e-6:
            vcp = min(vcp, vori * L / ang)
        elif L < 1e-6 and ang > 1e-6:
            L, vcp = ang, vori
        ds = max(L, 1e-6) / n
        dqmax = np.abs(np.diff(qs, axis=0)).max(axis=0) / ds
        lim = np.min(np.where(dqmax > 1e-9, self.model.vmax / np.maximum(dqmax, 1e-9), 1e9))
        vcp = min(vcp, lim)
        if self.track is not None and abs(e1 - e0) > 1e-6:
            vcp = min(vcp, self.track["vmax"] * max(L, 1e-6) / abs(e1 - e0))
        Ls = max(L, 1e-6)

        def qfun(s):
            f = min(max(s / Ls, 0), 1) * n
            i = min(int(f), n - 1)
            return qs[i] + (qs[i + 1] - qs[i]) * (f - i)

        def efun(s):
            f = min(max(s / Ls, 0), 1) * n
            i = min(int(f), n - 1)
            return es[i] + (es[i + 1] - es[i]) * (f - i)
        return Motion(kind, Ls, vcp, acc, qfun, target=qs[-1],
                      efun=efun if abs(e1 - e0) > 1e-9 else None, e_target=e1)

    def _flange_root(self):
        return self.carriage() @ self.model.fk(self.q)

    def plan_lin(self, tgt, rel=False):
        e1 = self._e_target(tgt)
        if tgt[0] == "axis":
            T1 = self.carriage(e1) @ self.model.fk(np.array(tgt[1][:6]))
        else:
            tg = tgt
            if rel:
                cur = np.array(self.sv["POS_ACT"])
                tg = ("pos", list(cur + np.array(tgt[1][:6])), None, None)
            T1 = self.target_root(tg)
        T0 = self._flange_root()
        return self._lin_between(T0, T1, e1)

    def _lin_between(self, T0, T1, e1=None):
        p0, p1 = T0[:3, 3], T1[:3, 3]
        L = float(np.linalg.norm(p1 - p0))
        R0, R1 = T0[:3, :3], T1[:3, :3]
        ang = _rot_angle(R0.T @ R1)

        def Tpath(u):
            T = np.eye(4)
            T[:3, :3] = _slerp(R0, R1, u)
            T[:3, 3] = p0 + (p1 - p0) * u
            return T
        return self._cart_motion("lin", Tpath, L, ang * R2D, self.e1, e1)

    def plan_circ(self, aux, tgt):
        e1 = self._e_target(tgt)
        T0 = self._flange_root()
        Ta = self.target_root(aux)
        T1 = self.target_root(tgt)
        p0, pa, p1 = T0[:3, 3], Ta[:3, 3], T1[:3, 3]
        n = np.cross(pa - p0, p1 - p0)
        if np.linalg.norm(n) < 1e-6:
            return self._lin_between(T0, T1, e1)
        n = n / np.linalg.norm(n)
        a, b = pa - p0, p1 - p0
        axb = np.cross(a, b)
        c = p0 + (np.cross(axb, a) * (b @ b) + np.cross(b, axb) * (a @ a)) / (2 * (axb @ axb))
        r = float(np.linalg.norm(p0 - c))
        ea = (p0 - c) / r
        eb = np.cross(n, ea)

        def ang_of(p):
            v = p - c
            return math.atan2(v @ eb, v @ ea)
        ta = ang_of(pa) % (2 * math.pi)
        t1 = ang_of(p1) % (2 * math.pi)
        if t1 < ta:
            t1 += 2 * math.pi
        total = t1
        L = r * total
        R0, R1 = T0[:3, :3], T1[:3, :3]
        ang = _rot_angle(R0.T @ R1) * R2D

        def Tpath(u):
            th = total * u
            T = np.eye(4)
            T[:3, :3] = _slerp(R0, R1, u)
            T[:3, 3] = c + r * (math.cos(th) * ea + math.sin(th) * eb)
            return T
        return self._cart_motion("circ", Tpath, L, ang, self.e1, e1)

    # ---- Programm
    def load_program(self, src):
        self.src = src
        self.reset_program()

    def reset_program(self):
        self.gen = None
        self.interp = None
        self.motion = None
        self.wait_fn = None
        self.wait_until = None
        self.state = "idle"
        self.cur_line = 0
        self.collision = None
        self.safety_msg = ""
        self._paused_state = 'running'
        self._pause_at = None
        self.wait_started = None
        self.pending_stop = None
        self.pulses.clear()

    def reset(self):
        self.reset_program()
        self.update_sv()

    def start(self, step=False):
        if self.busy():
            return False
        if self.state == 'paused':
            self.resume(step)
            return True
        self.reset_program()
        self._wn = 0
        self.w._sync_world_initial()
        self.w.world_paused = False
        if self.w.script_host:
            self.w.script_host.start()
        self.w._robot_initial.setdefault(id(self), (self.q.copy(), self.e1))
        try:
            self.update_sv()
            self.sv["TOOL"], self.sv["BASE"] = {}, {}
            self.sv["VEL_AXIS_PCT"] = 1.0
            self.interp = Interp(self.src, self.io, self.sv, self.frame_tables())
            for wmsg in self.interp.warnings[:30]:
                self.say(f"Hinweis: {wmsg}")
            self.gen = self.interp.run()
        except XrlError as e:
            self.state = "error"
            self.say(f"Syntaxfehler: {e}")
            return
        self.step_mode = step
        self.state = "running"
        self.run_t = 0.0
        self.line_time = {}
        self.cycle_times = []
        self._last_tick = None
        self.trail.clear()
        self.collision = None
        self.say("Programm gestartet" + (" (Einzelschritt)" if step else ""))
        return True

    def pause(self):
        if self.state in ("running", "wait"):
            self._paused_state = self.state
            self._pause_at = self.t
            self.state = "paused"

    def resume(self, step=False):
        if self.state == "paused":
            self.step_mode = step
            elapsed = self.t - self._pause_at if self._pause_at is not None else 0.
            if self.wait_until is not None:
                self.wait_until += elapsed
            self.pulses = [(t + elapsed, n, value) for t, n, value in self.pulses]
            if self.wait_started is not None:
                self.wait_started += elapsed
            self.state = self._paused_state
            self._pause_at = None
            self.w.world_paused = False
        elif self.state in ("idle", "error", "stopped"):
            self.start(step)

    def stop(self, kind=0):
        """STOP 0: sofortiges Anhalten mit maximaler Verzoegerung. Gibt den Anhalteweg aus."""
        if self.state == "idle":
            return
        if self.motion and not self.motion.done:
            self.pending_stop = {"kind": kind, "s0": self.motion.s, "v0": self.motion.v}
            self.state = "stopping"
            return
        self.reset_program()
        self.state = "stopped"
        self.say("Programm gestoppt")

    def flush_warnings(self):
        if self.interp is not None:
            new = self.interp.warnings[getattr(self, "_wn", 0):]
            for wmsg in new[:20]:
                self.say(f"Hinweis: {wmsg}")
            self._wn = len(self.interp.warnings)

    def _fetch(self):
        guard = 0
        while guard < 2000:
            guard += 1
            try:
                ev = next(self.gen)
            except StopIteration:
                self.state = "idle"
                self.gen = None
                self.say(f"Programm beendet nach {self.run_t:.2f} s")
                return
            except XrlError as e:
                self.state = "error"
                self.say(f"Laufzeitfehler: {e}")
                return
            k = ev[0]
            if k == "line":
                self.cur_line = ev[1]
                if self.step_mode or self.cur_line in getattr(self, 'breakpoints', set()):
                    self._paused_state = 'running'
                    self._pause_at = self.t
                    self.state = "paused"
                    self.w.pause_all()
                    return
                continue
            if k == "tick":
                if self._last_tick is not None:
                    self.cycle_times.append(self.run_t - self._last_tick)
                self._last_tick = self.run_t
                continue
            if k in ("ptp", "lin"):
                try:
                    self.motion = self.plan_ptp(ev[1], ev[2]) if k == "ptp" else self.plan_lin(ev[1], ev[2])
                except PlanError as e:
                    if k == "lin" and "Singular" in str(e):
                        try:
                            self.motion = self.plan_ptp(ev[1], ev[2])
                            self.say(f"Zeile {self.cur_line}: LIN durch Handgelenk-Singularität – als Achsbewegung ausgeführt")
                            return
                        except PlanError:
                            pass
                    self.state = "error"
                    self.say(f"Zeile {self.cur_line}: {e}")
                    return
                return
            if k == "circ":
                try:
                    self.motion = self.plan_circ(ev[1], ev[2])
                except PlanError as e:
                    self.state = "error"
                    self.say(f"Zeile {self.cur_line}: {e}")
                    return
                return
            if k == "wait":
                self.wait_until = self.t + ev[1]
                self.wait_started = self.t
                self.state = "wait"
                return
            if k == "waitfor":
                self.wait_fn = ev[1]
                self.wait_started = self.t
                self.state = "wait"
                lines = self.src.splitlines()
                condition = lines[self.cur_line - 1].strip() if 0 < self.cur_line <= len(lines) else "WAIT FOR"
                self.say(f"Zeile {self.cur_line}: Warte auf Bedingung: {condition} – E/A prüfen")
                return
            if k == "pulse":
                self.io.set_out(ev[1], ev[2])
                self.pulses.append((self.t + ev[3], ev[1], not ev[2]))
                continue
            if k == "msg":
                self.say(ev[1])
                continue
            if k == "halt":
                self._paused_state = 'running'
                self._pause_at = self.t
                self.state = "paused"
                self.w.pause_all()
                self.say("HALT - Programm angehalten")
                return

    def busy(self):
        return self.state in ("running", "wait", "stopping")

    # ---- Zeitschritt (von der Welt aufgerufen; Weltzeit wurde bereits erhoeht)
    def step(self, dt):
        if self.state == 'paused':
            return
        if self.busy():
            self.run_t += dt
        for p in list(self.pulses):
            if self.t >= p[0]:
                self.io.set_out(p[1], p[2])
                self.pulses.remove(p)
        if self.state == "running" and self.motion is None and self.gen is not None:
            self._fetch()
        if self.state == "wait":
            if self.wait_until is not None and self.t >= self.wait_until:
                self.wait_until = None
                self.wait_started = None
                self.state = "running"
            elif self.wait_fn is not None:
                try:
                    if self.wait_fn():
                        self.wait_fn = None
                        self.wait_started = None
                        self.state = "running"
                except Exception as e:
                    self.state = "error"
                    self.say(f"Fehler in WAIT FOR: {e}")
            if self.state == "running" and self.motion is None:
                self._fetch()
        if self.motion is not None and self.state in ("running", "stopping"):
            decel = max(self.motion.acc * 6.0, 1e-6) if self.state == "stopping" else None
            q, done = self.motion.step(dt, self.override, decel)
            self.q = np.array(q)
            if self.motion.efun is not None:
                self.e1 = float(self.motion.efun(self.motion.s))
            if self.state == "stopping" and done:
                dist = self.motion.s - self.pending_stop["s0"]
                self.stop_dist = dist
                self.say(f"STOP 0: Anhalteweg {dist:.1f} {'mm' if self.motion.kind != 'ptp' else '(Bahnparameter)'}")
                self.motion = None
                self.reset_program()
                self.state = "stopped"
            elif done and self.state == "running":
                self.q = np.array(self.motion.target)
                if self.motion.e_target is not None:
                    self.e1 = float(self.motion.e_target)
                self.motion = None
                self._fetch()
            self._after_move(dt)
        elif self.state == "stopping":
            self.reset_program()
            self.state = "stopped"
        self.update_sv()

    def _after_move(self, dt):
        tcp = self.tcp_world()[:3, 3]
        if not self.trail or np.linalg.norm(tcp - self.trail[-1]) > 5:
            self.trail.append(tcp.copy())
            if len(self.trail) > 6000:
                self.trail = self.trail[-6000:]
        self._energy(dt)
        if self.w.record_swept:
            for p in self.capsule_points(8):
                self.w.swept.add(tuple((np.floor(p / 40.0)).astype(int)))
        c = self.check_collision()
        if c and self.collision is None:
            self.collision = c
            self.say(f"KOLLISION: {c}")
            if self.stop_on_collision and self.state == "running":
                self.stop(0)
        elif not c:
            self.collision = None if self.state != "stopped" else self.collision
        sz = self.check_safety()
        if sz and self.state == "running":
            self.safety_msg = sz
            self.say(f"SICHERHEIT: {sz} -> STOP 0")
            self.stop(0)

    def _energy(self, dt):
        m = self.model
        k = m.reach / 1000.0
        masses = np.array([30, 25, 15, 6, 3, 1.5]) * k * k
        f = m.frames(self.q)
        z = [f[1][2, 3] + 100, (f[2][:3, 3] + f[3][:3, 3])[2] / 2, (f[3][:3, 3] + f[4][:3, 3])[2] / 2,
             f[4][2, 3], f[5][2, 3], f[6][2, 3]]
        U = float(np.sum(masses * 9.81 * np.array(z) / 1000.0))
        dU = (U - self._last_u) / dt if (self._last_u is not None and dt > 0) else 0.0
        self._last_u = U
        w = np.abs(self.q - self.q_prev_frame) / max(dt, 1e-6) * D2R
        self.q_prev_frame = self.q.copy()
        P = 80.0 * k + max(dU, 0) + float(np.sum(w * w)) * 3.0 * k + max(-dU, 0) * 0.1
        self.power_w = P
        self.energy_wh += P * dt / 3600.0

    # ---- Greifer (pro Roboter)
    def _grip_candidate(self, tcp):
        best, distance = None, float("inf")
        for o in self.scene:
            if not o.graspable or o.attached:
                continue
            # Abstand zur gedrehten Werkstück-Hülle statt einer Kugel um dessen Mittelpunkt.
            p = (inv(o.matrix()) @ np.array([*tcp[:3, 3], 1.0]))[:3]
            half = np.asarray(o.size, float) / 2
            closest = np.clip(p, [-half[0], -half[1], 0], [half[0], half[1], 2 * half[2]])
            d = float(np.linalg.norm(p - closest))
            if d < distance:
                best, distance = o, d
        return best, distance

    def gripper_info(self):
        held = next((o for o in self.scene if o.attached and o.attached_to == self.name), None)
        nearest, distance = self._grip_candidate(self.tcp_world()) if held is None else (None, 0.0)
        conflicts = [link["dst"][0] for link in self.w.links
                     if tuple(link["src"]) == (self.name, f"Outputs_Port_{self.tool.grip_out}")]
        return {"output": int(self.tool.grip_out), "command": bool(self.tool.grip_out and self.io.get_out(self.tool.grip_out)),
                "holding": held is not None, "part": held.name if held else "",
                "nearest": nearest.name if nearest else "", "distance": distance,
                "conflicts": conflicts}

    def update_gripper(self):
        g = bool(self.tool.grip_out and self.io.get_out(self.tool.grip_out))
        tcp = self.tcp_world()
        holding = any(o.attached and o.attached_to == self.name for o in self.scene)
        # Ein gesetzter Greifbefehl bleibt aktiv, wenn das Teil erst später in Reichweite kommt.
        if g and not holding:
            best, bd = self._grip_candidate(tcp)
            if best is not None and bd <= self.tool.grip_range:
                # Gripping transfers ownership from a fixture to the TCP. Do not
                # restore an old hierarchy transform when the part is released.
                best.parent, best.local = None, None
                best.attached = True
                best.attached_to = self.name
                best.rel = inv(tcp) @ best.matrix()
                self.say(f"Objekt '{best.name}' gegriffen")
        if not g and holding:
            for o in self.scene:
                if o.attached and o.attached_to == self.name:
                    o.attached = False
                    o.attached_to = None
                    self.say(f"Objekt '{o.name}' losgelassen")
        self.prev_grip = g
        for o in self.scene:
            if o.attached and o.attached_to == self.name and o.rel is not None:
                p = mat_to_pose(tcp @ o.rel)
                o.pos, o.rot = list(map(float, p[:3])), list(map(float, p[3:]))

    # ---- Kollision / Sicherheit
    def capsules(self):
        m = self.model
        f = [self.robroot() @ x for x in m.frames(self.q)]
        k = m.reach / 1000.0
        o = lambda i: f[i][:3, 3]
        tcpm = f[6] @ self.tool_mat()
        return [
            (o(0), o(1) + np.array([0, 0, m.d1 * 0.1]), 95 * k, "Sockel"),
            (o(1), o(2), 80 * k, "Karussell"),
            (o(2), o(3), 65 * k, "Oberarm"),
            (o(3), o(4), 55 * k, "Unterarm"),
            (o(4), f[6][:3, 3], 45 * k, "Handgelenk"),
            (f[6][:3, 3], _tip(f[6][:3, 3], tcpm[:3, 3]), self.tool.radius, "Werkzeug"),
        ]

    def capsule_points(self, per=6):
        pts = []
        for p, q, r, nm in self.capsules():
            for t in np.linspace(0, 1, per):
                pts.append(p + (q - p) * t)
        return pts

    def check_collision(self):
        if not self.w.collision_enabled:
            return None
        def ignored(name):
            return ((self.name, name) in self.w.collision_ignore or
                    (name, self.name) in self.w.collision_ignore)
        caps = self.capsules()
        for p, q, r, nm in caps[2:]:
            if not ignored("Boden") and min(p[2], q[2]) - r * 0.5 < self.w.GROUND_Z - 1:
                return f"{nm} <-> Boden"
        for o in self.scene:
            if ignored(o.name) or not o.obstacle or o.attached or o.kind in ("sensor", "spawner", "sink", "zone", "conveyor_arc", "group"):
                continue
            M = o.matrix() @ tr(0, 0, o.size[2] / 2)
            half = o.half()
            for p, q, r, nm in caps:
                n = max(3, int(np.linalg.norm(q - p) / max(r, 20)) + 2)
                pts = np.array([p + (q - p) * t for t in np.linspace(0, 1, n)])
                if np.min(pts_box_dist(pts, M, half)) < r * 0.9:
                    return f"{nm} <-> {o.name}"
        for i in range(len(caps)):
            for j in range(i + 2, len(caps)):
                a, b = caps[i], caps[j]
                if not ignored(self.name) and seg_seg_dist(a[0], a[1], b[0], b[1]) < (a[2] + b[2]) * 0.8:
                    return f"{a[3]} <-> {b[3]} (Selbstkollision)"
        # andere Roboter
        for other in self.w.robots:
            if other is self or ignored(other.name):
                continue
            for a in caps:
                for b in other.capsules():
                    if seg_seg_dist(a[0], a[1], b[0], b[1]) < (a[2] + b[2]) * 0.9:
                        return f"{a[3]} <-> {other.name}/{b[3]}"
        return None

    def check_safety(self):
        for z in self.safety:
            if not z.get("active", True):
                continue
            lo, hi = np.array(z["min"], float), np.array(z["max"], float)
            for p in [self.tcp_world()[:3, 3]] + [c[1] for c in self.capsules()]:
                inside = np.all(p >= lo) and np.all(p <= hi)
                if z.get("type", "verbot") == "verbot" and inside:
                    return f"Verbotszone '{z['name']}' verletzt"
                if z.get("type") == "arbeitsraum" and not inside:
                    return f"Arbeitsraum '{z['name']}' verlassen"
        return None

    # ---- Analyse
    def reach_cloud(self, pts_target=9000, orient=(0, 0, 180)):
        m = self.model
        R = m.reach
        step = max(R / 18.0, 40.0)
        ok, bad = [], []
        T0 = pose_to_mat(0, 0, 0, *orient)
        tool_inv = inv(self.tool_mat())
        xs = np.arange(-R, R + 1, step)
        zs = np.arange(-R * 0.4, R * 1.1, step)
        for x in xs:
            for y in xs:
                if x * x + y * y > R * R:
                    continue
                for z in zs:
                    T = T0.copy()
                    T[:3, 3] = (x, y, z)
                    q = m.ik(T @ tool_inv, HOME)
                    (ok if q is not None else bad).append((x, y, z))
        Rr = self.robroot()
        W, t = Rr[:3, :3], Rr[:3, 3]
        tf = lambda L: (np.array(L).reshape(-1, 3) @ W.T + t) if L else np.zeros((0, 3))
        return tf(ok), tf(bad)

    def reachable(self, pose_world, orient=None):
        """Ist ein Weltpunkt (Werkzeug nach unten) erreichbar? Mit Linearachse: irgendeine E1-Stellung."""
        T = np.eye(4)
        T[:3, :3] = pose_to_mat(0, 0, 0, *(orient or (0, 0, 180)))[:3, :3]
        T[:3, 3] = pose_world
        es = [self.e1] if self.track is None else list(np.linspace(*self.e_limits(), 11))
        for e in es:
            if self.model.ik(inv(self.robroot(e)) @ T @ inv(self.tool_mat()), HOME) is not None:
                return True
        return False

    # ---- Speichern
    def to_dict(self):
        return {
            "name": self.name, "model": self.model_key, "root": self.root_pose, "base": self.base,
            "tool": self.tool.to_dict(), "q": list(map(float, self.q)), "e1": self.e1, "track": self.track,
            "program": self.src, "waypoints": self.waypoints, "tool_table": self.tool_table,
            "statements": self.statements, "mode": self.mode,
            "breakpoints": sorted(getattr(self, 'breakpoints', set())),
            "base_table": self.base_table, "sv": {k: self.sv[k] for k in ("VEL_CP", "ACC_CP", "VEL_ORI1")},
        }

    def from_dict(self, d):
        self.name = d.get("name", self.name)
        self.tool_table = d.get("tool_table", {})
        self.base_table = d.get("base_table", {})
        self.set_model(d.get("model") if d.get("model") in MODELS else self.model_key)
        self.set_root(d.get("root", [0] * 6))
        self.base = d.get("base", [0] * 6)
        self.tool = Tool()
        self.tool.__dict__.update(d.get("tool", {}))
        self.q = np.array(d.get("q", list(HOME)), float)
        self.track = d.get("track")
        self.e_limits()
        self.e1 = float(d.get("e1", 0.0))
        self.src = d.get("program", self.src)
        self.breakpoints = {int(n) for n in d.get('breakpoints', []) if isinstance(n, int) and n > 0}
        self.waypoints = d.get("waypoints", [])
        self.statements = d.get("statements", [])
        self.mode = d.get("mode", "xrl")
        self.sv.update(d.get("sv", {}))
        self.reset()


# ------------------------------------------------------------------ Halle / Welt
class Simulation:
    GROUND_Z = 0.0
    SETTINGS = {"collision_enabled": True, "stop_on_collision": True,
                "limit_warn_pct": 3.0, "show_limit_colors": False,
                "stop_at_limits": False, "limit_messages": False}
    _OWN = {"io", "scene", "t", "speed_factor", "override", "log", "message", "safety", "swept", "record_swept",
            "world_paused", "_world_scene", "_consumed_parts", "_world_initial", "_robot_initial", "stop_on_collision", "imported_models", "robots", "active_idx", "on_message", "stats", "_t_last_stat"}

    def __init__(self):
        d = self.__dict__
        d["_world_scene"] = None
        d["_consumed_parts"] = []
        d["world_paused"] = False
        d["_world_initial"] = {}
        d["_robot_initial"] = {}
        d["io"] = IO()
        d["links"] = []
        d["rng"] = random.Random(0)
        d["script_host"] = None
        d["run_scripts"] = False
        d["scene"] = []
        d["t"] = 0.0
        d["speed_factor"] = 1.0
        d["override"] = 1.0
        d["log"] = []
        d['log_revision'] = 0
        d['pending_dt'] = 0.
        d['max_substeps'] = 128
        d['frame_budget_ms'] = None
        d['performance'] = {'step_ms': 0., 'substeps': 0, 'backlog_s': 0., 'actual_speed': 0.}
        d['_support_index'] = None
        d["message"] = ""
        d["safety"] = []
        d["swept"] = set()
        d["record_swept"] = False
        d["stop_on_collision"] = True
        d.update(self.SETTINGS)
        d["collision_ignore"] = set()
        d["recorder"] = None
        d["dimensions"] = []
        d["imported_models"] = {}
        d["robots"] = []
        d["active_idx"] = 0
        d["on_message"] = None
        d["stats"] = {"created": 0, "consumed": 0, "t0": 0.0}
        self.robots.append(Robot(self, "Roboter 1"))

    # ---- Weiterleitung an den aktiven Roboter
    @property
    def active(self):
        return self.robots[min(self.active_idx, len(self.robots) - 1)]

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        robots = self.__dict__.get("robots")
        if not robots:
            raise AttributeError(name)
        return getattr(self.active, name)

    def __setattr__(self, name, value):
        if name in Simulation._OWN or name in self.__dict__ or hasattr(type(self), name):
            object.__setattr__(self, name, value)
        elif hasattr(self.active, name):
            setattr(self.active, name, value)
        else:
            object.__setattr__(self, name, value)

    # ---- Roboterverwaltung
    def add_robot(self, model_key=None, root=(0, 0, 0, 0, 0, 0), name=None):
        r = Robot(self, name or f"Roboter {len(self.robots) + 1}", model_key or self.active.model_key)
        r.set_root(root)
        r.src = DEFAULT_PROGRAM.replace("DEF demo()", f"DEF {_ident(r.name)}()")
        self.robots.append(r)
        self.active_idx = len(self.robots) - 1
        return r

    def remove_robot(self, idx):
        if len(self.robots) > 1 and 0 <= idx < len(self.robots):
            del self.robots[idx]
            self.active_idx = max(0, min(self.active_idx, len(self.robots) - 1))

    def clear_robots(self):
        self.robots[:] = [Robot(self, "Roboter 1")]
        self.active_idx = 0

    def set_active(self, idx):
        if 0 <= idx < len(self.robots):
            self.active_idx = idx

    # ---- Meldungen
    def say(self, m):
        self.log.append(f"[{self.t:7.2f}s] {m}")
        if len(self.log) > 800:
            del self.log[:-500]
        self.message = m
        self.log_revision += 1

    # ---- gemeinsame Steuerung
    def start_all(self, step=False):
        if self.any_busy():
            return False
        if any(r.state == 'paused' for r in self.robots):
            for r in self.robots:
                if r.state == 'paused':
                    r.resume(step)
            self.world_paused = False
            return True
        self.world_paused = False
        self.stats.update(created=0, consumed=0, t0=self.t)
        for s in self.scene:
            s.consumed = 0
        for r in self.robots:
            r.start(step)
        return True

    def stop_all(self):
        self.world_paused = True
        for r in self.robots:
            r.stop(0)

    def pause_all(self):
        self.world_paused = True
        self.pending_dt = 0.
        for r in self.robots:
            r.pause()

    def any_busy(self):
        return any(r.busy() for r in self.robots)

    def wire_links(self):
        """Bind persisted endpoints; legacy scenes retain the shared robot bus."""
        self._refresh_links()
        objects = {o.name: o for o in self.scene}
        robots = {r.name: r for r in self.robots}
        if self.links:
            for i, r in enumerate(self.robots):
                r._signal_io = self.io if i == 0 else getattr(r, "_signal_io", IO())
        channels = {}
        used = {int(n) for o in self.scene for n in
                [o.io, o.trigger, o.detected, *o.color_outs.values(), *o.inputs.values()] if IO.is_virtual(int(n))}
        def channel(endpoint):
            if endpoint not in channels:
                o = objects.get(endpoint[0])
                signal = endpoint[1]
                existing = 0
                if o:
                    if o.kind == "sensor":
                        existing = o.io
                    elif o.kind == "color_sensor":
                        existing = o.color_outs.get(signal, o.trigger if signal == "ColorTrigger" else o.detected)
                    elif o.kind == "lamp":
                        existing = o.inputs.get(signal, 0)
                    else:
                        existing = o.trigger if o.kind == "spawner" else o.io
                n = int(existing) if IO.is_virtual(int(existing)) else next((n for n in range(2001, IO.N) if n not in used), None)
                if n is None:
                    raise ValueError("Zu viele virtuelle Signale (maximal 2096)")
                channels[endpoint] = n
                used.add(n)
            return channels[endpoint]
        for link in self.links:
            src, dst = tuple(link["src"]), tuple(link["dst"])
            so, do = objects.get(src[0]), objects.get(dst[0])
            out = re.fullmatch(r"Outputs_Port_(\d+)", src[1]) if src[0] in robots else None
            inp = re.fullmatch(r"Inputs_Port_(\d+)", dst[1]) if dst[0] in robots else None
            if so:
                n = channel(src)
                if so.kind == "sensor":
                    so.io = n
                elif so.kind == "color_sensor":
                    if signal_color(src[1]) is not None:
                        so.color_outs[src[1]] = n
                    else:
                        so.detected = n
                # A sole robot-input connection keeps the familiar sensor.io=N.
                targets = [x for x in self.links if tuple(x["src"]) == src]
                if so.kind == "sensor" and inp and len(targets) == 1 and robots[dst[0]] is self.robots[0]:
                    so.io = int(inp[1])
            if do:
                sources = [x for x in self.links if tuple(x["dst"]) == dst]
                n = int(out[1]) if out and len(sources) == 1 and do.kind != "lamp" else channel(dst)
                if do.kind in ("conveyor", "conveyor_arc"):
                    do.io = n
                elif do.kind in ("spawner", "color_sensor"):
                    do.trigger = n
                elif do.kind == "lamp":
                    do.inputs[dst[1]] = n
        for o in self.scene:
            if o.kind == "color_sensor":
                for name in o.color_outs:
                    if not o.color_outs[name]:
                        o.color_outs[name] = channel((o.name, name))
                if not o.detected:
                    o.detected = channel((o.name, "ColorDetected"))

    def _source_signal(self, endpoint, native=False):
        if self.script_host and not native:
            return self.script_host.source(endpoint)
        name, signal = endpoint
        port = re.fullmatch(r"Outputs_Port_(\d+)", signal)
        if port:
            robot = getattr(self, '_robots_lookup', {}).get(name)
            if robot is None or robot.name != name:
                robot = next((r for r in self.robots if r.name == name), None)
            return bool(robot and robot.io.get_out(int(port[1])))
        o = getattr(self, '_objects_lookup', {}).get(name)
        if o is None or o.name != name:
            o = next((o for o in self.scene if o.name == name), None)
        if o is None:
            return False
        n = o.io if o.kind == "sensor" else o.color_outs.get(signal, o.detected)
        return self.io.get_in(int(n))

    def _route_links(self):
        if self.script_host:
            self.script_host.route()
        values = {}
        for link in self.links:
            dst = tuple(link["dst"])
            values[dst] = values.get(dst, False) or self._source_signal(link["src"])
        for (name, signal), value in values.items():
            port = re.fullmatch(r"Inputs_Port_(\d+)", signal)
            if port:
                r = self._robots_lookup.get(name)
                if r:
                    r.io.set_in(int(port[1]), value)
                continue
            o = self._objects_lookup.get(name)
            if o:
                n = o.inputs.get(signal, 0) if o.kind == "lamp" else o.trigger if o.kind in ("spawner", "color_sensor") else o.io
                if IO.is_virtual(int(n)):
                    self.io.set_out(int(n), value)
                    self.io.set_in(int(n), value)

    def _driven(self, o, n):
        links = getattr(self, '_links_by_target', {}).get(o.name, [])
        return any(self._source_signal(x["src"]) for x in links) if links else self.io.get_out(int(n)) or (IO.is_virtual(int(n)) and self.io.get_in(int(n)))

    def _beam_part(self, sensor):
        m, half = inv(sensor.matrix()), sensor.half()
        for o in self.scene:
            if o.graspable and not o.attached:
                local = (m @ np.array([*o.pos[:2], o.pos[2] + o.size[2] / 2, 1.]))[:3]
                if np.all(np.abs(local) <= half):
                    return o
        return None

    # ---- Zeitschritt
    def tick(self, dt_real):
        from editing import update_hierarchy
        if not math.isfinite(dt_real) or dt_real < 0 or not math.isfinite(self.speed_factor) or self.speed_factor <= 0:
            raise ValueError('Zeitschritt und Zeitraffer müssen endliche positive Werte sein')
        if self.world_paused and not any(r.state == 'stopping' for r in self.robots):
            return
        self.pending_dt += dt_real * self.speed_factor
        n = min(max(1, int(math.ceil(self.pending_dt / .01))), self.max_substeps)
        if self.pending_dt <= 0:
            return
        h = min(.01, self.pending_dt / n)
        started, before, count = time.perf_counter(), self.t, 0
        for _ in range(n):
            self.pending_dt = max(0., self.pending_dt - h)
            self.t += h
            count += 1
            self._update_world(h)
            for r in self.robots:
                self._check_limits(r)
                r.step(h)
                self._check_limits(r)
            update_hierarchy(self)
            if self.script_host:
                self.script_host.update()
            if self.recorder and self.recorder.active:
                self.recorder.sample(self)
            if self.world_paused and not any(r.state == 'stopping' for r in self.robots):
                self.pending_dt = 0.
                break
            if self.frame_budget_ms and (time.perf_counter() - started) * 1000 >= self.frame_budget_ms:
                break
        self._support_index = None
        self.performance.update(step_ms=(time.perf_counter() - started) * 1000, substeps=count,
                                backlog_s=self.pending_dt, actual_speed=(self.t - before) / max(dt_real, 1e-9))

    def _check_limits(self, robot):
        limits = robot.model.limits
        margin = (limits[:, 1] - limits[:, 0]) * max(0., self.limit_warn_pct) / 100.
        near = set(np.flatnonzero((robot.q <= limits[:, 0] + margin) |
                                  (robot.q >= limits[:, 1] - margin)).tolist())
        entered = near - robot.near_limits
        robot.near_limits = near
        if self.limit_messages and entered:
            robot.say('Achsgrenze nahe: ' + ', '.join(f'A{i+1}' for i in sorted(entered)))
        if self.stop_at_limits and near and robot.state in ('running', 'wait', 'stopping'):
            robot.reset_program()
            robot.state = 'stopped'
            robot.say('Achsgrenze nahe -> Roboter gestoppt')

    def reset_world(self):
        """Rewind runtime state while retaining objects, programs and configuration."""
        self._sync_world_initial()
        for r in self.robots:
            r.reset()
            initial = self._robot_initial.get(id(r))
            if initial:
                r.q = initial[0].copy()
                r.e1 = initial[1]
            r.trail.clear()
            r.run_t = 0.0
            r.energy_wh = 0.0
            r.line_time.clear()
            r.cycle_times.clear()
            r.update_sv()
        # Keep original object references, including parts consumed by sinks.
        self._sync_world_initial()
        originals = [o for o in self.scene + self._consumed_parts
                     if not getattr(o, "_runtime_created", False)]
        self._consumed_parts.clear()
        for o in originals:
            initial = self._world_initial.get(id(o))
            if initial:
                o.pos, o.rot = copy.deepcopy(initial[1])
            o.attached = False
            o.attached_to = None
            o.rel = None
            o.timer = 0.0
            o.spawned = o.consumed = 0
            o._trigger_high = False
            o.lit_color = None
        self.scene[:] = originals
        self.io.inp[:] = [False] * self.io.N
        self.io.out[:] = [False] * self.io.N
        for r in self.robots:
            r.io.inp[:] = [False] * r.io.N
            r.io.out[:] = [False] * r.io.N
        self.rng.seed(0)
        self.t = 0.0
        self.pending_dt = 0.
        self._support_index = None
        self.stats.update(created=0, consumed=0, t0=0.0)
        self.swept.clear()
        self.message = "Simulation zurückgesetzt"
        self.world_paused = True
        if self.script_host:
            self.script_host.reset()

    def _sync_world_initial(self):
        if self._world_scene is not self.scene:
            self._world_scene = self.scene
            self._world_initial.clear()
            self._robot_initial.clear()
            self._consumed_parts.clear()

    def _refresh_links(self):
        self._robots_lookup = {r.name: r for r in self.robots}
        self._objects_lookup = {o.name: o for o in self.scene}
        self._links_by_target = {}
        for link in self.links:
            self._links_by_target.setdefault(link['dst'][0], []).append(link)

    def _update_world(self, dt):
        self._sync_world_initial()
        if self.world_paused:
            return
        self._refresh_links()
        from spatial import SupportIndex
        self._support_index = SupportIndex(self.scene)
        for r in self.robots:
            self._robot_initial.setdefault(id(r), (r.q.copy(), r.e1))
        for o in self.scene:
            if not getattr(o, "_runtime_created", False):
                self._world_initial.setdefault(id(o), (o, copy.deepcopy((o.pos, o.rot))))
        for r in self.robots:
            r.update_gripper()
        scene = self.scene
        self._route_links()
        # Foerderer (gerade)
        for b in scene:
            if b.kind != "conveyor":
                continue
            if getattr(b, "stopped", False) or not ((b.io == 0) or self._driven(b, b.io)):   # Interagieren: von Hand angehalten
                continue
            Mb = b.matrix()
            Mi = b.inverse_matrix()
            half = b.half()
            for o in scene:
                if o is b or o.attached or o.parent or not o.graspable:
                    continue
                L = (Mi @ np.array([*o.pos, 1.0]))[:3]
                if abs(L[0]) <= half[0] and abs(L[1]) <= half[1] and abs(o.pos[2] - b.top_z()) < 3:
                    d = Mb[:3, 0] * b.speed * dt
                    o.pos[0] += float(d[0])
                    o.pos[1] += float(d[1])
        # Kurvenfoerderer
        for b in scene:
            if b.kind != "conveyor_arc":
                continue
            if getattr(b, "stopped", False) or not ((b.io == 0) or self._driven(b, b.io)):   # Interagieren: von Hand angehalten
                continue
            M = b.matrix()
            Mi = inv(M)
            c = b.arc_center()
            for o in scene:
                if o is b or o.attached or o.parent or not o.graspable:
                    continue
                if abs(o.pos[2] - b.top_z()) > 3 or not b.on_arc(o.pos):
                    continue
                L = (Mi @ np.array([*o.pos, 1.0]))[:3]
                v = L[:2] - c
                r = max(float(np.hypot(*v)), 1.0)
                dphi = b.speed * dt / r * (-1 if b.turn_right else 1)
                cs, sn = math.cos(dphi), math.sin(dphi)
                L[:2] = c + np.array([cs * v[0] - sn * v[1], sn * v[0] + cs * v[1]])
                W = (M @ np.array([*L, 1.0]))[:3]
                o.pos[0], o.pos[1] = float(W[0]), float(W[1])
                o.rot[0] += math.degrees(dphi)
        # Schwerkraft
        for o in scene:
            if o.graspable and not o.attached and not o.parent:
                # Beim Loslassen kann die Näherung des Greifers unter z=0 liegen.
                # Freie Teile dürfen dadurch nicht dauerhaft unter dem Hallenboden bleiben.
                o.pos[2] = max(0., o.pos[2])
                floor = self.support_z(o)
                if o.pos[2] > floor + 0.01:
                    o.pos[2] = max(floor, o.pos[2] - 3000 * dt * dt * 50 - 400 * dt)
        # Sensoren
        for s in scene:
            if s.kind == "sensor" and s.io:
                hit = self._beam_part(s) is not None
                self.io.set_in(int(s.io), hit)
                if IO.is_virtual(int(s.io)):
                    self.io.set_out(int(s.io), hit)
        self._route_links()
        for s in scene:
            if s.kind != "color_sensor" or s.scripted:
                continue
            part = self._beam_part(s)
            enabled = not s.trigger or self._driven(s, s.trigger)
            choices = {name: rgb for name in s.color_outs if (rgb := signal_color(name)) is not None}
            match = min(choices, key=lambda name: np.linalg.norm(np.array(color_rgb(part.color)) - choices[name])) if part and enabled and choices else None
            for name, n in s.color_outs.items():
                self.io.set_in(int(n), name == match)
                if IO.is_virtual(int(n)):
                    self.io.set_out(int(n), name == match)
            self.io.set_in(int(s.detected), bool(part and enabled))
            if IO.is_virtual(int(s.detected)):
                self.io.set_out(int(s.detected), bool(part and enabled))
        self._route_links()
        for s in scene:
            if s.kind == "lamp" and not s.scripted:
                s.lit_color = next((signal_color(name) for name, n in s.inputs.items()
                                    if self.io.get_in(int(n)) or self.io.get_out(int(n))), None)
        # Senken: Teile im Volumen werden entfernt und gezaehlt
        for s in [x for x in scene if x.kind == "sink"]:
            if s.io and not self.io.get_out(int(s.io)):
                continue
            Ms = inv(s.matrix())
            half = s.half()
            for o in list(scene):
                if o.graspable and not o.attached:
                    L = (Ms @ np.array([*o.pos[:2], o.pos[2] + o.size[2] / 2, 1.0]))[:3]
                    if np.all(np.abs(L) <= half):
                        scene.remove(o)
                        if self.script_host:
                            self.script_host.remove(o)
                        if not getattr(o, "_runtime_created", False):
                            self._consumed_parts.append(o)
                        s.consumed += 1
                        self.stats["consumed"] += 1
        # Erzeuger
        for s in [x for x in scene if x.kind == "spawner"]:
            s.timer += dt
            running = (s.io == 0) or self.io.get_out(int(s.io))
            high = bool(s.trigger and self._driven(s, s.trigger))
            due = high and not s._trigger_high if s.trigger else s.timer >= s.interval
            s._trigger_high = high
            if running and due and s.spawned < s.max_parts:
                free = all(np.linalg.norm(np.array(o.pos[:2]) - np.array(s.pos[:2])) > max(o.size[:2]) + 10
                           for o in scene if o.graspable and not o.attached)
                if free or s.trigger:
                    s.timer = 0
                    s.spawned += 1
                    self.stats["created"] += 1
                    part = SceneObj(f"{s.name}_teil{s.spawned}", "workpiece", s.pos[:2] + [s.pos[2]], (0, 0, 0),
                                    list(s.part_size), self.rng.choice(s.colors) if s.colors and not (self.script_host and s.product_templates) else s.part_color, False, True)
                    part._runtime_created = True
                    scene.append(part)
                    if self.script_host and s.product_templates:
                        template = s.product_templates[(s.spawned - 1) % len(s.product_templates)]
                        self.script_host.clone(part, template)
        self._support_index = None

    def support_z(self, o):
        z = 0.0
        candidates = self._support_index.query(*o.pos[:2]) if self._support_index is not None else self.scene
        for b in candidates:
            if b is o or b.attached or b.kind in ("sensor", "color_sensor", "lamp", "spawner", "sink", "zone"):
                continue
            if b.kind == "conveyor_arc":
                if b.on_arc([o.pos[0], o.pos[1], b.pos[2]]):
                    z = max(z, b.top_z())
                continue
            if not (b.obstacle or b.kind == "conveyor"):
                continue
            L = (b.inverse_matrix() @ np.array([*o.pos[:2], b.pos[2] + 1, 1.0]))[:3]
            h = b.half()
            if abs(L[0]) <= h[0] and abs(L[1]) <= h[1]:
                z = max(z, b.top_z())
        return z

    def throughput(self):
        """Durchsatz-Kennzahlen seit Start"""
        dt = max(self.t - self.stats["t0"], 1e-6)
        wip = sum(1 for o in self.scene if o.graspable)
        return {"erzeugt": self.stats["created"], "fertig": self.stats["consumed"], "im_umlauf": wip,
                "pro_stunde": self.stats["consumed"] / dt * 3600.0, "laufzeit": dt}

    def swept_boxes(self):
        return [np.array(v) * 40.0 + 20.0 for v in self.swept]

    # ---- Speichern
    def to_dict(self):
        a = self.active
        d = a.to_dict()           # Felder des aktiven Roboters weiter oben (rueckwaertskompatibel)
        d.update({
            "format": 2, "robots": [r.to_dict() for r in self.robots], "active": self.active_idx,
            "scene": [o.to_dict() for o in self.scene], "safety": self.safety,
            "imported_models": {**self.imported_models, **self._own_models()},
            "io_names": [[k[0], k[1], v] for k, v in self.io.names.items()],
            "opcua_clients": list(getattr(self, "opcua_clients", None) or []),
            "links": copy.deepcopy(self.links),
            "run_scripts": self.run_scripts,
            "robot_vc_data": {r.name: getattr(r, 'vc_data', {}) for r in self.robots},
            "dimensions": copy.deepcopy(self.dimensions),
            "collision_ignore": [list(pair) for pair in sorted(self.collision_ignore)],
            **{key: getattr(self, key) for key in self.SETTINGS},
        })
        return d

    def _own_models(self):
        """Eigene Roboter (Roboter-Editor) im Projekt mitspeichern, damit es auf anderen PCs laeuft"""
        out = {}
        for r in self.robots:
            m = r.model
            if getattr(m, "maker", None) == "Eigene":
                out[r.model_key] = {"dims": [m.a1, m.d1, m.a2, m.a3, m.d4, m.d6],
                                    "limits": [list(map(float, l)) for l in m.limits],
                                    "vmax": [float(v) for v in m.vmax], "payload": float(m.payload or 0),
                                    "cad": dict(getattr(m, "cad", None) or {}), "paint": getattr(m, "paint", None)}
        return out

    def from_dict(self, d):
        from kinematics import RobotModel
        self.recorder = None
        self.dimensions = copy.deepcopy(d.get('dimensions', []))
        self.collision_ignore = {tuple(pair) for pair in d.get('collision_ignore', [])}
        for key, default in self.SETTINGS.items():
            setattr(self, key, d.get(key, default))
        self.imported_models = d.get("imported_models", {})
        for k, p in self.imported_models.items():
            MODELS[k] = RobotModel(k, *p["dims"], p["limits"], p["vmax"], p.get("payload", 0))
            MODELS[k].cad = dict(p.get("cad") or {})
            MODELS[k].paint = p.get("paint")
            if p.get("cad") is not None or p.get("paint") is not None:
                MODELS[k].maker = "Eigene"
        self.robots[:] = []
        for rd in d.get("robots") or [d]:
            r = Robot(self, rd.get("name", f"Roboter {len(self.robots) + 1}"))
            r.from_dict(rd)
            self.robots.append(r)
        self.active_idx = min(d.get("active", 0), len(self.robots) - 1)
        self.scene = [SceneObj.from_dict(x) for x in d.get("scene", [])]
        self.safety = d.get("safety", [])
        self.io.names = {(a, int(b)): c for a, b, c in d.get("io_names", [])}
        self.opcua_clients = list(d.get("opcua_clients", []) or [])
        self.links = [{"src": tuple(x["src"]), "dst": tuple(x["dst"])} for x in d.get("links", [])]
        self.wire_links()
        self.run_scripts = bool(d.get('run_scripts', False))
        for r in self.robots:
            r.vc_data = d.get('robot_vc_data', {}).get(r.name, {})
        self.init_scripts()
        from editing import update_hierarchy
        update_hierarchy(self)

    def init_scripts(self):
        from vc_runtime import ScriptHost
        self.script_host = None
        for o in self.scene:
            o.scripted = False
        if self.run_scripts and any(getattr(o, 'vc_data', {}).get('scripts') or
                                    any(t.get('scripts') for t in getattr(o, 'product_templates', []))
                                    for o in self.scene + self.robots):
            self.script_host = ScriptHost(self)


def _tip(p, q, keep=30.0):
    """Werkzeugspitze (letzte 30 mm) nicht als Kollisionskoerper - Prozesskontakt ist gewollt"""
    d = q - p
    L = float(np.linalg.norm(d))
    return q if L < 1e-6 else p + d * max(0.0, (L - min(keep, 0.5 * L)) / L)


def _ident(name):
    s = "".join(ch if ch.isalnum() else "_" for ch in name)
    return s if s and not s[0].isdigit() else "p_" + s


def _rot_angle(R):
    return math.acos(max(-1.0, min(1.0, (np.trace(R) - 1) / 2)))


def _slerp(R0, R1, u):
    Rd = R0.T @ R1
    ang = _rot_angle(Rd)
    if ang < 1e-9:
        return R0.copy()
    ax = np.array([Rd[2, 1] - Rd[1, 2], Rd[0, 2] - Rd[2, 0], Rd[1, 0] - Rd[0, 1]])
    nrm = np.linalg.norm(ax)
    if nrm < 1e-9:
        ax = np.sqrt(np.maximum((np.diag(Rd) + 1) / 2, 0))
    else:
        ax = ax / nrm
    K = np.array([[0, -ax[2], ax[1]], [ax[2], 0, -ax[0]], [-ax[1], ax[0], 0]])
    th = ang * u
    Ru = np.eye(3) + math.sin(th) * K + (1 - math.cos(th)) * (K @ K)
    return R0 @ Ru


DEFAULT_PROGRAM = """; Ximaj RoboSim - Beispielprogramm (XRL)
DEF demo()
  DECL INT i
  DECL POS pHome, pAbove, pPick
  pHome  = {X 450, Y 0, Z 600, A 0, B 0, C 180}
  pAbove = {X 450, Y 250, Z 350, A 0, B 0, C 180}
  pPick  = {X 450, Y 250, Z 45, A 0, B 0, C 180}
  $VEL_CP = 1.0
  PTP pHome
  FOR i = 1 TO 3
    PTP pAbove
    LIN pPick
    $OUT[1] = TRUE
    WAIT SEC 0.3
    LIN pAbove
    PTP {X 450, Y -250, Z 350, A 0, B 0, C 180}
    LIN {X 450, Y -250, Z 45, A 0, B 0, C 180}
    $OUT[1] = FALSE
    WAIT SEC 0.3
    LIN {X 450, Y -250, Z 350, A 0, B 0, C 180}
  ENDFOR
  PTP pHome
END
"""
