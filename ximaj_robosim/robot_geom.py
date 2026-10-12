"""Own-design cast robot housings, in millimetres and link-local frames.

Meshes contain independent cap vertices and smooth curved-surface normals.
Only NumPy is required; the dimension-keyed cache is shared across robots.
"""
from functools import lru_cache
import numpy as np


def _skin(rings):
    """Close CCW rings with separately shaded planar end caps."""
    rings = np.asarray(rings, dtype=float)
    count, segments, _ = rings.shape
    verts = rings.reshape(-1, 3)
    faces = []
    for j in range(count - 1):
        for i in range(segments):
            a, b = j * segments + i, j * segments + (i + 1) % segments
            faces.extend(((a, b, b + segments), (a, b + segments, a + segments)))
    faces = np.asarray(faces, dtype=np.uint32)
    triangles = verts[faces]
    area = np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])
    normals = np.zeros_like(verts)
    for corner in range(3):
        np.add.at(normals, faces[:, corner], area)
    normals /= np.linalg.norm(normals, axis=1)[:, None]
    all_verts, all_normals, all_faces = [verts], [normals], [faces]
    offset = len(verts)
    for ring, sign in ((rings[0], -1), (rings[-1], 1)):
        all_verts.append(np.vstack((ring, ring.mean(axis=0))))
        all_normals.append(np.tile((0, 0, sign), (segments + 1, 1)))
        cap = [(offset + segments, offset + i, offset + (i + 1) % segments)
               for i in range(segments)]
        if sign < 0:
            cap = [(a, c, b) for a, b, c in cap]
        all_faces.append(np.asarray(cap, dtype=np.uint32))
        offset += segments + 1
    return (np.ascontiguousarray(np.vstack(all_verts), dtype=np.float32),
            np.ascontiguousarray(np.vstack(all_normals), dtype=np.float32),
            np.ascontiguousarray(np.vstack(all_faces), dtype=np.uint32))


def revolve(profile, segments=40):
    """Revolve positive (radius, z) pairs around +z, ordered bottom to top."""
    theta = np.arange(segments) * (2 * np.pi / segments)
    return _skin([np.column_stack((r * np.cos(theta), r * np.sin(theta),
                                  np.full(segments, z))) for r, z in profile])


def loft(sections, segments=32, corner=0.25):
    """Rounded rectangles: sections are (z, width, height, center_x, center_y).

    Corner is the radius as a fraction of the smaller half dimension.
    Four equally sampled corner arcs keep corresponding vertices aligned.
    """
    if segments < 8 or segments % 4:
        raise ValueError("loft segments must be a multiple of four >= 8")
    rings = []
    for z, width, height, cx, cy in sections:
        hx, hy = width / 2, height / 2
        radius = min(hx, hy) * corner
        ring = []
        for quadrant, (sx, sy) in enumerate(((1, 1), (-1, 1), (-1, -1), (1, -1))):
            angles = quadrant * np.pi / 2 + np.linspace(0, np.pi / 2, segments // 4)
            ring.extend((cx + sx * (hx - radius) + radius * np.cos(t),
                         cy + sy * (hy - radius) + radius * np.sin(t), z) for t in angles)
        rings.append(ring)
    return _skin(rings)


def rounded_box(size, center=(0, 0, 0), bevel=None):
    """Rounded rectangular shell with chamfered top/bottom and flat caps."""
    x, y, z = size
    cx, cy, cz = center
    b = min(size) * 0.12 if bevel is None else bevel
    b = min(b, min(size) * 0.45)
    return loft([(cz - z / 2, x - 2*b, y - 2*b, cx, cy),
                 (cz - z / 2 + b, x, y, cx, cy),
                 (cz + z / 2 - b, x, y, cx, cy),
                 (cz + z / 2, x - 2*b, y - 2*b, cx, cy)])


def hub(radius, length, fillet=None, segments=40, steps=5):
    """Capsule-like cylinder with quarter-circle rim fillets, along +z."""
    f = min(radius * 0.16 if fillet is None else fillet, radius * 0.45, length * 0.45)
    profile = []
    for t in np.linspace(0, np.pi / 2, steps):
        profile.append((radius - f + f*np.sin(t), f - f*np.cos(t)))
    for t in np.linspace(0, np.pi / 2, steps):
        profile.append((radius - f + f*np.cos(t), length - f + f*np.sin(t)))
    return revolve(profile, segments)


_Y_AXIS = np.array(((1, 0, 0), (0, 0, 1), (0, -1, 0)), dtype=float)


def _placed(mesh, center=(0, 0, 0), axis_y=False):
    v, n, f = mesh
    if axis_y:
        v, n = v @ _Y_AXIS.T, n @ _Y_AXIS.T
    return (np.ascontiguousarray(v + np.asarray(center), dtype=np.float32),
            np.ascontiguousarray(n, dtype=np.float32), f)


def build_robot_meshes(model):
    """Return seven lists of (vertices, unit normals, triangles, material).

    Cached arrays are read-only; callers may freely alter the returned lists.
    """
    dims = tuple(float(getattr(model, key)) for key in ('a1', 'd1', 'a2', 'a3', 'd4', 'd6', 'reach'))
    dims += (float(getattr(model, 'payload', 10) or 10),)
    return [list(link) for link in _build(dims)]


@lru_cache(maxsize=32)
def _build(dims):
    a1, d1, a2, a3, d4, d6, reach, payload = dims
    # Schwerlastroboter wirken kraeftiger: Staerke waechst mit der Traglast (log), Hand bleibt schlank
    heavy = float(np.clip(1 + 0.22 * np.log10(max(payload, 1) / 10), 0.85, 1.45))
    s, rb, w = reach / 1000, max(60, 105 * reach / 1000) * heavy, max(45, 85 * reach / 1000) * heavy
    links = [[] for _ in range(7)]

    def add(frame, mesh, mat='body', center=(0, 0, 0), axis_y=False):
        links[frame].append((*_placed(mesh, center, axis_y), mat))

    def motor(frame, r, L, start, axis_y=False, sign=1, fins=5):
        """Servomotor mit Flansch, Kuehlrippen, Deckel und Steckergehaeuse entlang z (oder y)"""
        ax = 1 if axis_y else 2

        def seg(t, l, radius, mat, fillet=None, n=32, steps=3):
            c = list(start)
            c[ax] += t if sign > 0 else -(t + l)
            add(frame, hub(radius, l, fillet, n, steps), mat, tuple(c), axis_y)

        seg(0, .08*L, 1.10*r, 'metal')
        seg(.08*L, .80*L, r, 'dark', .08*r)
        for k in range(fins):
            seg(.16*L + k * .62*L / max(fins - 1, 1), .035*L, 1.07*r, 'dark', .01*r, 24, 2)
        seg(.88*L, .12*L, .82*r, 'dark', .25*r)
        c = list(start)
        c[ax] += sign * .55*L
        side = 0 if axis_y else 1      # Stecker seitlich
        c[side] += 1.0*r
        add(frame, rounded_box((.55*r, .55*r, .55*r) if not axis_y else (.55*r, .55*r, .55*r)), 'dark', tuple(c))

    plate = 18*s + 8
    add(0, rounded_box((2.6*rb, 2.6*rb, plate), (0, 0, plate/2)), 'dark')
    for x in (-rb, rb):
        for y in (-rb, rb):
            add(0, hub(0.10*rb, 0.075*rb, None, 16, 3), 'metal', (x, y, plate))
    add(0, revolve([(1.12*rb, plate*.75), (1.12*rb, max(plate, .06*d1)),
                    (1.02*rb, .20*d1), (1.02*rb, .22*d1)]), 'dark')
    add(0, hub(1.16*rb, .02*d1), 'trim', (0, 0, .22*d1))
    add(0, rounded_box((.42*rb, .80*rb, .50*rb)), 'dark', (-1.30*rb, 0, plate + .25*rb))      # Anschlusskasten
    for y in (-.2*rb, .2*rb):
        add(0, hub(.11*rb, .16*rb, None, 16, 3), 'metal', (-1.30*rb, y, plate + .50*rb))                # Steckverbinder
    add(0, rounded_box((.30*rb, .02*rb, .26*rb)), 'warn', (0, -1.13*rb, .11*d1))           # Warnschild

    add(1, hub(rb, .38*d1, .12*rb), center=(0, 0, .24*d1))
    add(1, loft([(.52*d1, 1.6*rb, 1.65*rb, 0, 0),
                 (.70*d1, 1.5*rb, 1.55*rb, .35*a1, 0),
                 (.92*d1, 1.25*rb, 1.35*rb, a1, 0),
                 (d1 + .20*rb, .95*rb, 1.25*rb, a1, 0)], corner=.55))
    add(1, rounded_box((.70*rb, .95*rb, .85*rb)), center=(-.85*rb, 0, .49*d1))
    motor(1, .27*rb, .62*rb, (-.85*rb, 0, .49*d1 + .42*rb))                                  # Motor A1
    for side in (-1, 1):
        add(1, hub(.61*rb, .18*rb), center=(a1, side*.70*rb-.09*rb, d1), axis_y=True)
        add(1, hub(.43*rb, .045*rb), 'metal', (a1, side*.82*rb-.0225*rb, d1), True)
    motor(1, .34*rb, .72*rb, (a1, -.84*rb, d1 - .05*rb), axis_y=True, sign=-1)               # Motor A2
    add(1, rounded_box((.02*rb, .26*rb, .22*rb)), 'warn', (a1 - .62*rb, .5*rb, .82*d1))

    add(2, loft([(0, 1.28*w, 1.05*w, 0, 0),
                 (.15*a2, 1.18*w, .92*w, 0, 0),
                 (.77*a2, .84*w, .77*w, 0, 0),
                 (a2, .92*w, .84*w, 0, 0)], corner=.60))
    for z, radius in ((0, .70*w), (a2, .57*w)):
        add(2, hub(radius, 1.08*w), center=(0, -.54*w, z), axis_y=True)
    add(2, rounded_box((.44*w, .055*w, .64*a2)), 'trim', (0, .46*w, .43*a2))
    motor(2, .30*w, .62*w, (0, .54*w, a2 - .05*w), axis_y=True, sign=1, fins=4)             # Motor A3
    add(2, rounded_box((.06*w, .50*w, .20*a2)), 'dark', (-.62*w, 0, .45*a2))                  # Kabelfuehrung

    add(3, hub(.62*w, 1.22*w), center=(0, -.61*w, 0), axis_y=True)
    if abs(a3) > .15*w:      # grosser Unterarmversatz: Ellbogengehaeuse bis zur Unterarmachse fuehren
        add(3, rounded_box((abs(a3) + 1.0*w, 1.10*w, 1.10*w)), center=(-a3/2, 0, 0))
    add(3, hub(.38*w, .07*w), 'metal', (0, .61*w, 0), True)
    add(3, rounded_box((1.12*w, 1.02*w, 1.40*w)), center=(-a3, 0, -.24*w))
    add(3, rounded_box((.94*w, .88*w, .12*w)), 'dark', (-a3, 0, -.98*w))
    for dx, dy in ((-.22*w, -.22*w), (-.22*w, .22*w), (.22*w, 0)):                          # Motoren A4-A6
        motor(3, .17*w, .55*w, (-a3 + dx, dy, -1.03*w), sign=-1, fins=4)
    add(3, revolve([(.41*w, .10*w), (.42*w, .42*w),
                    (.34*w, .68*d4), (.29*w, d4-.45*w)]), center=(-a3, 0, 0))
    add(3, hub(.385*w, .035*d4), 'trim', (-a3, 0, .55*d4))

    add(4, rounded_box((.64*w, 1.03*w, .32*w)), center=(0, 0, -.39*w))
    for side in (-1, 1):
        add(4, loft([(-.46*w, .61*w, .23*w, 0, side*.40*w),
                     (-.14*w, .66*w, .23*w, 0, side*.40*w),
                     (.17*w, .43*w, .23*w, 0, side*.40*w)], corner=.65))
        add(4, hub(.22*w, .04*w), 'metal', (0, side*.53*w-.02*w, 0), True)

    add(5, hub(.30*w, .69*w), center=(0, -.345*w, 0), axis_y=True)
    add(5, revolve([(.28*w, 0), (.31*w, .17*d6),
                    (.23*w, .70*d6), (.21*w, d6-10)]))
    add(5, hub(.24*w, .065*d6), 'dark', (0, 0, .78*d6))

    flange = .25*w
    add(6, hub(flange, 10, 1.2), 'metal', (0, 0, -10))
    for theta in np.arange(6) * np.pi/3:
        add(6, hub(.027*w, .8, .15, 12, 2), 'dark',
            (.71*flange*np.cos(theta), .71*flange*np.sin(theta), -.8))
    add(6, rounded_box((.09*w, .075*w, 1.1)), 'trim', (.90*flange, 0, -.55))
    for link in links:
        for verts, normals, faces, _ in link:
            for array in (verts, normals, faces):
                array.setflags(write=False)
    return tuple(tuple(link) for link in links)
