"""Prozess-Generatoren: Bahn-, Punkt- und Flaechenprozesse aus der Bauteilgeometrie.

Ergebnis ist jeweils ein dict:
  stmts     – Statement-Bausteine (siehe statements.py) fuer den aktiven Roboter
  preview   – Polylinien (Welt) zur Anzeige
  coverage  – Streifen (Welt) fuer die Abdeckungsanzeige [(p0, p1, breite)]
  report    – Kennzahlen (Laenge, Punkte, Zeit, nicht erreichbar)
"""
import math
import numpy as np

import statements as stm
from kinematics import pose_to_mat, mat_to_pose, inv


# ------------------------------------------------------------------ Geometrie
def object_mesh(o):
    """Bauteil als trimesh in Weltkoordinaten"""
    import trimesh
    if o.kind == "mesh" and o.mesh is not None:
        m = trimesh.Trimesh(o.mesh[0].copy(), o.mesh[1].copy(), process=False)
    elif o.kind == "cylinder":
        m = trimesh.creation.cylinder(radius=o.size[0] / 2, height=o.size[2], sections=72)
        m.apply_translation([0, 0, o.size[2] / 2])
    else:
        m = trimesh.creation.box(extents=o.size)
        m.apply_translation([0, 0, o.size[2] / 2])
    m.apply_transform(o.matrix())
    return m


def contour(o, height_from_top=2.0):
    """Groesste geschlossene Kontur (Welt, CCW von oben) in Hoehe 'oberkante - height_from_top'"""
    m = object_mesh(o)
    ztop = float(m.bounds[1][2])
    z = ztop - max(0.2, height_from_top)
    loops = slice_loops(np.asarray(m.vertices), np.asarray(m.faces), z)
    if not loops:
        return None, ztop
    loop = max(loops, key=lambda a: abs(_area(a)))
    if np.linalg.norm(loop[0] - loop[-1]) < 1e-6:
        loop = loop[:-1]
    if _area(loop) < 0:
        loop = loop[::-1]
    return loop, ztop


def slice_loops(V, F, z, tol=1e-6):
    """Schnitt eines Dreiecksnetzes mit der Ebene Z=z -> Liste geschlossener Polylinien (Nx3). Reines NumPy."""
    d = V[:, 2] - z
    d = np.where(np.abs(d) < tol, tol, d)              # Ecken genau auf der Ebene leicht verschieben
    tri = F
    s = np.sign(d[tri])
    cut = ~((s[:, 0] == s[:, 1]) & (s[:, 1] == s[:, 2]))
    segs = []
    for t in tri[cut]:
        pts = []
        for a, b in ((t[0], t[1]), (t[1], t[2]), (t[2], t[0])):
            if (d[a] > 0) != (d[b] > 0):
                f = d[a] / (d[a] - d[b])
                pts.append(V[a] + (V[b] - V[a]) * f)
        if len(pts) == 2:
            segs.append(pts)
    if not segs:
        return []
    key = lambda p: (round(float(p[0]), 3), round(float(p[1]), 3))
    adj = {}
    for i, (p, q) in enumerate(segs):
        adj.setdefault(key(p), []).append((i, 1))
        adj.setdefault(key(q), []).append((i, 0))
    used = [False] * len(segs)
    loops = []
    for i0 in range(len(segs)):
        if used[i0]:
            continue
        used[i0] = True
        loop = [segs[i0][0], segs[i0][1]]
        cur = segs[i0][1]
        for _ in range(len(segs)):
            nxt = None
            for j, end in adj.get(key(cur), []):
                if not used[j]:
                    nxt = (j, end)
                    break
            if nxt is None:
                break
            j, end = nxt
            used[j] = True
            cur = segs[j][end]
            loop.append(cur)
        arr = np.array(loop)
        arr[:, 2] = z
        # doppelte Punkte entfernen
        keep = [0] + [k for k in range(1, len(arr)) if np.linalg.norm(arr[k] - arr[k - 1]) > 1e-4]
        arr = arr[keep]
        if len(arr) >= 3:
            loops.append(arr)
    return loops


def _area(p):
    x, y = p[:, 0], p[:, 1]
    return 0.5 * float(np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y))


def offset_loop(loop, d):
    """Geschlossene CCW-Kontur um d nach aussen versetzen (2D, Z bleibt)"""
    if abs(d) < 1e-9:
        return loop.copy()
    n = len(loop)
    out = []
    for i in range(n):
        p0, p1, p2 = loop[i - 1], loop[i], loop[(i + 1) % n]
        e1 = p1[:2] - p0[:2]
        e2 = p2[:2] - p1[:2]
        n1 = np.array([e1[1], -e1[0]]) / (np.linalg.norm(e1) or 1)
        n2 = np.array([e2[1], -e2[0]]) / (np.linalg.norm(e2) or 1)
        nb = n1 + n2
        ln = np.linalg.norm(nb)
        nb = nb / ln if ln > 1e-9 else n1
        cosh = max(0.3, float(nb @ n1))
        q = p1.copy()
        q[:2] = p1[:2] + nb * d / cosh
        out.append(q)
    return np.array(out)


def resample(loop, ds, closed=True):
    pts = np.vstack([loop, loop[:1]]) if closed else loop
    seg = np.linalg.norm(np.diff(pts, axis=0), axis=1)
    L = float(seg.sum())
    if L < 1e-6:
        return loop.copy(), 0.0
    n = max(int(round(L / ds)), 3)
    s = np.concatenate([[0], np.cumsum(seg)])
    out = []
    for t in np.linspace(0, L, n, endpoint=not closed):
        i = min(np.searchsorted(s, t, side="right") - 1, len(seg) - 1)
        f = (t - s[i]) / (seg[i] or 1)
        out.append(pts[i] + (pts[i + 1] - pts[i]) * f)
    return np.array(out), L


def tool_pose(p, tangent, outward, tilt_deg=0.0, travel_deg=0.0):
    """Werkzeug-Pose (Welt-Matrix): Z zeigt nach unten, um tilt zur Aussenseite geneigt, X in Bahnrichtung"""
    t = tilt_deg * math.pi / 180
    z = np.array([0, 0, -1.0]) * math.cos(t) - np.array([outward[0], outward[1], 0]) * math.sin(t)
    if abs(travel_deg) > 1e-6:
        a = travel_deg * math.pi / 180
        z = z * math.cos(a) + np.array([tangent[0], tangent[1], 0]) * math.sin(a)
    z /= np.linalg.norm(z)
    x = np.array([tangent[0], tangent[1], 0.0])
    x = x - z * (x @ z)
    if np.linalg.norm(x) < 1e-9:
        x = np.array([1.0, 0, 0]) - z * z[0]
    x /= np.linalg.norm(x)
    y = np.cross(z, x)
    M = np.eye(4)
    M[:3, 0], M[:3, 1], M[:3, 2], M[:3, 3] = x, y, z, p
    return M


# ------------------------------------------------------------------ Hilfen Roboter
def _to_base(robot, M_world):
    """Weltmatrix -> Pose [X,Y,Z,A,B,C] im BASE-System des Roboters"""
    return [round(float(v), 2) for v in mat_to_pose(inv(robot.base_world()) @ M_world)]


def _reachable(robot, M_world):
    T = inv(robot.robroot()) @ M_world @ inv(robot.tool_mat())
    return robot.model.ik(T, robot.q) is not None


def _spin_fit(robot, poses, spin_free=True):
    """Drehung um die Werkzeugachse frei waehlen: je Pose erreichbare Variante nahe der vorherigen Stellung.
    -> (angepasste Posen, Anzahl nicht erreichbar)"""
    from kinematics import rz
    q_ref = robot.q.copy()
    out, bad = [], 0
    angles = [0] + [s * a for a in range(20, 181, 20) for s in (1, -1)] if spin_free else [0]
    prev_ang = 0
    for M in poses:
        best = None
        for a in sorted(angles, key=lambda x: abs(((x - prev_ang) + 180) % 360 - 180)):
            Mr = M @ rz(math.radians(a))
            T = inv(robot.robroot()) @ Mr @ inv(robot.tool_mat())
            q = robot.model.ik(T, q_ref)
            if q is not None and np.max(np.abs(q - q_ref)[:3]) < 120:
                best = (Mr, q, a)
                break
        if best is None:
            out.append(M)
            bad += 1
        else:
            out.append(best[0])
            q_ref, prev_ang = best[1], best[2]
    return out, bad


def _lift(M, dz):
    N = M.copy()
    N[2, 3] += dz
    return N


# ------------------------------------------------------------------ Bahnprozess
def path_process(robot, o, height_from_top=2.0, offset=0.0, tilt=45.0, travel=10.0, spacing=25.0,
                 approach=80.0, speed=0.15, out_nr=0, reverse=False, spin_free=True):
    loop, ztop = contour(o, height_from_top)
    if loop is None:
        raise ValueError("Am Bauteil wurde in dieser Höhe keine Kontur gefunden.")
    loop = offset_loop(loop, offset)
    pts, L = resample(loop, spacing, closed=True)
    if reverse:
        pts = pts[::-1]
    n = len(pts)
    poses = []
    for i in range(n):
        tan = pts[(i + 1) % n] - pts[i - 1]
        tan = tan / (np.linalg.norm(tan) or 1)
        outward = np.array([tan[1], -tan[0], 0]) * (-1 if reverse else 1)
        poses.append(tool_pose(pts[i], tan, outward, tilt, travel))
    poses.append(poses[0].copy())            # Kontur schliessen
    poses, bad = _spin_fit(robot, poses, spin_free)
    stmts = [stm.new("COMMENT", text=f"Bahnprozess an {o.name}: {L:.0f} mm, {n} Punkte")]
    stmts.append(stm.new("PTP", pos=_to_base(robot, _lift(poses[0], approach)), vel=100, name="Anfahrt"))
    stmts.append(stm.new("LIN", pos=_to_base(robot, poses[0]), vel=0.5, name="Start"))
    if out_nr:
        stmts.append(stm.new("SET_OUT", nr=out_nr, value=True))
    for M in poses[1:]:
        stmts.append(stm.new("LIN", pos=_to_base(robot, M), vel=speed, name=""))
    if out_nr:
        stmts.append(stm.new("SET_OUT", nr=out_nr, value=False))
    stmts.append(stm.new("LIN", pos=_to_base(robot, _lift(poses[-1], approach)), vel=0.5, name="Abfahrt"))
    t = L / 1000.0 / max(speed, 1e-6) + 2 * approach / 500.0 + 1.5
    return {"stmts": stmts, "preview": [np.vstack([pts, pts[:1]])], "coverage": [],
            "report": {"Bahnlänge (mm)": round(L), "Bahnpunkte": n, "Prozesszeit ca. (s)": round(t, 1),
                       "nicht erreichbar": bad}}


# ------------------------------------------------------------------ Punktprozess
def point_process(robot, o, mode="kontur", spacing=60.0, height_from_top=2.0, offset=0.0, grid=(3, 3),
                  approach=60.0, dwell=0.3, out_nr=0, tilt=0.0, spin_free=True):
    if mode == "kontur":
        loop, ztop = contour(o, height_from_top)
        if loop is None:
            raise ValueError("Am Bauteil wurde keine Kontur gefunden.")
        loop = offset_loop(loop, offset)
        pts, L = resample(loop, spacing, closed=True)
        n = len(pts)
        poses = []
        for i in range(n):
            tan = pts[(i + 1) % n] - pts[i - 1]
            tan = tan / (np.linalg.norm(tan) or 1)
            poses.append(tool_pose(pts[i], tan, np.array([tan[1], -tan[0], 0]), tilt))
    else:
        m = object_mesh(o)
        ztop = float(m.bounds[1][2])
        M = o.matrix()
        nx, ny = max(1, int(grid[0])), max(1, int(grid[1]))
        poses = []
        for j in range(ny):
            xs = range(nx) if j % 2 == 0 else range(nx - 1, -1, -1)       # Maeander = kurze Wege
            for i in xs:
                lx = (i + 0.5) / nx * o.size[0] - o.size[0] / 2
                ly = (j + 0.5) / ny * o.size[1] - o.size[1] / 2
                p = (M @ np.array([lx, ly, 0, 1.0]))[:3]
                p[2] = ztop
                poses.append(tool_pose(p, M[:3, 0], M[:3, 1], 0.0))
    poses, bad = _spin_fit(robot, poses, spin_free)
    stmts = [stm.new("COMMENT", text=f"Punktprozess an {o.name}: {len(poses)} Punkte")]
    for k, Mp in enumerate(poses):
        stmts.append(stm.new("PTP" if k == 0 else "LIN", pos=_to_base(robot, _lift(Mp, approach)),
                             vel=100 if k == 0 else 1.0, name=f"Pkt{k + 1}_oben"))
        stmts.append(stm.new("LIN", pos=_to_base(robot, Mp), vel=0.3, name=f"Pkt{k + 1}"))
        if out_nr:
            stmts.append(stm.new("PULSE", nr=out_nr, sec=max(dwell, 0.05)))
        stmts.append(stm.new("WAIT_TIME", sec=dwell))
        stmts.append(stm.new("LIN", pos=_to_base(robot, _lift(Mp, approach)), vel=1.0, name=""))
    t = len(poses) * (2 * approach / 300.0 + dwell + 0.4)
    return {"stmts": stmts, "preview": [np.array([Mp[:3, 3] for Mp in poses])], "points": True, "coverage": [],
            "report": {"Prozesspunkte": len(poses), "Prozesszeit ca. (s)": round(t, 1), "nicht erreichbar": bad}}


# ------------------------------------------------------------------ Flaechenprozess
def surface_process(robot, o, width=50.0, overlap=20.0, standoff=150.0, margin=0.0, speed=0.3, out_nr=0,
                    direction_deg=0.0):
    loop, ztop = contour(o, 1.0)
    if loop is None:
        raise ValueError("Keine Oberfläche gefunden.")
    loop = offset_loop(loop, -abs(margin)) if margin else loop
    step = width * (1 - overlap / 100.0)
    c = loop[:, :2].mean(axis=0)
    a = math.radians(direction_deg + o.rot[0])
    R = np.array([[math.cos(a), -math.sin(a)], [math.sin(a), math.cos(a)]])
    P = (loop[:, :2] - c) @ R                       # Kontur im Rasterkoordinatensystem
    ymin, ymax = P[:, 1].min(), P[:, 1].max()
    lines = []
    span = max(ymax - ymin - width, 0.0)
    nl = int(math.ceil(span / max(step, 1e-6))) + 1 if span > 0 else 1
    ys = np.linspace(ymin + width / 2, ymax - width / 2, nl) if span > 0 else [0.5 * (ymin + ymax)]
    for k, y in enumerate(ys):
        xs = []
        for i in range(len(P)):
            p0, p1 = P[i], P[(i + 1) % len(P)]
            if (p0[1] - y) * (p1[1] - y) < 0:
                xs.append(p0[0] + (y - p0[1]) * (p1[0] - p0[0]) / (p1[1] - p0[1]))
        xs.sort()
        for j in range(0, len(xs) - 1, 2):
            seg = [xs[j], xs[j + 1]] if k % 2 == 0 else [xs[j + 1], xs[j]]
            lines.append([(seg[0], y), (seg[1], y)])
    # ueberstrichener Anteil quer zur Bahn (Vereinigung der Streifen)
    iv = sorted((float(y) - width / 2, float(y) + width / 2) for y in ys)
    cov_len, cur = 0.0, None
    for lo_, hi_ in iv:
        lo_, hi_ = max(lo_, ymin), min(hi_, ymax)
        if cur and lo_ <= cur[1]:
            cur[1] = max(cur[1], hi_)
        else:
            if cur:
                cov_len += cur[1] - cur[0]
            cur = [lo_, hi_]
    if cur:
        cov_len += cur[1] - cur[0]
    cov_frac = cov_len / max(ymax - ymin, 1e-6)
    if not lines:
        raise ValueError("Fläche zu klein für die gewählte Bahnbreite.")
    toW = lambda q: np.array([*(R @ np.array(q) + c), ztop + standoff])
    poses, cov, L = [], [], 0.0
    for (q0, q1) in lines:
        p0, p1 = toW(q0), toW(q1)
        tan = (p1 - p0) / (np.linalg.norm(p1 - p0) or 1)
        poses.append((tool_pose(p0, tan, np.array([-tan[1], tan[0], 0])), tool_pose(p1, tan, np.array([-tan[1], tan[0], 0]))))
        cov.append((p0 - np.array([0, 0, standoff - 1.0]), p1 - np.array([0, 0, standoff - 1.0]), width))
        L += float(np.linalg.norm(p1 - p0))
    stmts = [stm.new("COMMENT", text=f"Flächenprozess an {o.name}: {len(lines)} Bahnen")]
    stmts.append(stm.new("PTP", pos=_to_base(robot, _lift(poses[0][0], 100)), vel=100, name="Anfahrt"))
    for i, (A, Bm) in enumerate(poses):
        stmts.append(stm.new("LIN", pos=_to_base(robot, A), vel=1.0 if i else 0.5, name=f"B{i + 1}"))
        if out_nr:
            stmts.append(stm.new("SET_OUT", nr=out_nr, value=True))
        stmts.append(stm.new("LIN", pos=_to_base(robot, Bm), vel=speed, name=""))
        if out_nr:
            stmts.append(stm.new("SET_OUT", nr=out_nr, value=False))
    stmts.append(stm.new("LIN", pos=_to_base(robot, _lift(poses[-1][1], 100)), vel=0.5, name="Abfahrt"))
    area = abs(_area(loop))
    bad =sum((0 if _reachable(robot, A) else 1) + (0 if _reachable(robot, Bm) else 1) for A, Bm in poses)
    t = L / 1000.0 / max(speed, 1e-6) + len(lines) * 0.6 + 2
    return {"stmts": stmts, "preview": [np.array([p for A, Bm in poses for p in (A[:3, 3], Bm[:3, 3])])],
            "coverage": cov,
            "report": {"Bahnen": len(lines), "Bahnlänge (mm)": round(L), "Fläche (cm²)": round(area / 100),
                       "Abdeckung (%)": round(float(min(100.0, cov_frac * 100)), 1),
                       "Prozesszeit ca. (s)": round(t, 1), "nicht erreichbar": bad}}
