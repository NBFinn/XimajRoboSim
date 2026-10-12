"""Qt-free scene editing; transforms use millimetres and ABC degrees."""
import copy as _copy
import math
import numpy as np
from kinematics import MODELS, pose_to_mat, mat_to_pose, inv
from sim import SceneObj


def _descendants(sim, objs):
    names = {o.name for o in objs}
    while True:
        more = {o.name for o in sim.scene if o.parent in names}
        if more <= names:
            return [o for o in sim.scene if o.name in names]
        names |= more


def _unique(sim, name, reserved=()):
    used = {o.name for o in sim.scene} | {r.name for r in sim.robots} | set(reserved)
    candidate, n = name, 2
    while candidate in used:
        candidate = f"{name} ({n})"
        n += 1
    return candidate


def _parent_world(sim, ref):
    for o in sim.scene:
        if o.name == ref:
            return o.matrix()
    for r in sim.robots:
        if ref == r.name + "@flange":
            return r.flange_world()
        if ref == r.name + "@base":
            return r.robroot()
    raise ValueError(f"Unbekannter Bezug: {ref}")


def _pose(obj, matrix):
    p = mat_to_pose(matrix)
    obj.pos, obj.rot = p[:3].tolist(), p[3:].tolist()


def _edited(sim, obj):
    if obj.parent:
        obj.local = (inv(_parent_world(sim, obj.parent)) @ obj.matrix()).tolist()
    update_hierarchy(sim)


def update_hierarchy(sim):
    objects = {o.name: o for o in sim.scene}
    done, visiting = set(), set()
    def visit(o):
        if o.name in done:
            return
        if o.name in visiting:
            raise ValueError("Zyklische Objekthierarchie")
        visiting.add(o.name)
        if o.parent and o.local is not None and not o.attached:
            if o.parent in objects:
                visit(objects[o.parent])
            try:
                _pose(o, _parent_world(sim, o.parent) @ np.asarray(o.local, float))
            except ValueError as exc:
                if o.parent in objects:
                    raise exc
                # Missing parent in an older project: retain its world pose.
        visiting.remove(o.name)
        done.add(o.name)
    for o in sim.scene:
        visit(o)


def attach(sim, child, parent_ref):
    if parent_ref in {o.name for o in _descendants(sim, [child])}:
        raise ValueError("Zyklische Objekthierarchie")
    local = inv(_parent_world(sim, parent_ref)) @ child.matrix()
    child.parent, child.local = parent_ref, local.tolist()
    update_hierarchy(sim)


def detach(sim, obj):
    update_hierarchy(sim)
    obj.parent, obj.local = None, None


def copy(sim, objs):
    result = []
    for o in _descendants(sim, objs):
        d = _copy.deepcopy(o.to_dict())
        if o.mesh is not None:
            d['_mesh'] = [a.copy() for a in o.mesh]
        if o.lines:
            d['_lines'] = _copy.deepcopy(o.lines)
        result.append(d)
    return result


def paste(sim, clip, offset=(200, 200, 0)):
    clip = _copy.deepcopy(clip)
    names = {}
    for d in clip:
        names[d['name']] = _unique(sim, d['name'], names.values())
    result = []
    for d in clip:
        old = d['name']
        o = SceneObj.from_dict(d)
        o.name = names[old]
        o.pos = (np.asarray(o.pos) + offset).tolist()
        o.parent = names.get(o.parent)
        if o.parent is None:
            o.local = None
        if '_mesh' in d:
            o.mesh = tuple(d['_mesh'])
        if '_lines' in d:
            o.lines = d['_lines']
        result.append(o)
    sim.scene.extend(result)
    update_hierarchy(sim)
    return result


def delete(sim, objs):
    removed = _descendants(sim, objs)
    names = {o.name for o in removed}
    sim.scene[:] = [o for o in sim.scene if o.name not in names]
    sim.links[:] = [l for l in sim.links if all(l[k][0] not in names for k in ('src', 'dst'))]
    sim.dimensions[:] = [d for d in sim.dimensions if not names.intersection(d.get('objects', []))
                        and d.get('obj') not in names]
    sim.wire_links()
    if sim.script_host:
        for o in removed:
            sim.script_host.remove(o)
    update_hierarchy(sim)


def bounds(o):
    if o.mesh is not None:
        pts = o.mesh[0]
    else:
        pts = np.array([[x, y, z] for x in (-o.size[0]/2, o.size[0]/2)
                        for y in (-o.size[1]/2, o.size[1]/2) for z in (0, o.size[2])])
    world = np.asarray(pts) @ o.matrix()[:3, :3].T + o.pos
    return world.min(axis=0), world.max(axis=0)


def group(sim, objs, name=None):
    objs = list(objs)
    if not objs:
        raise ValueError("Keine Objekte ausgewählt")
    bb = [bounds(o) for o in objs]
    lo, hi = np.min([b[0] for b in bb], axis=0), np.max([b[1] for b in bb], axis=0)
    g = SceneObj(_unique(sim, name or 'Gruppe'), 'group', ((lo+hi)/2).tolist(), size=(hi-lo).tolist(), obstacle=False)
    g.visible = False
    sim.scene.append(g)
    for o in objs:
        attach(sim, o, g.name)
    return g


def ungroup(sim, group):
    children = [o for o in sim.scene if o.parent == group.name]
    for o in children:
        detach(sim, o)
        if group.parent:
            attach(sim, o, group.parent)
    delete(sim, [group])
    return children


def move(sim, obj, dx, dy, dz, da=0, db=0, dc=0, frame='world'):
    if frame not in ('world', 'local'):
        raise ValueError("Unbekanntes Koordinatensystem")
    delta = pose_to_mat(dx, dy, dz, da, db, dc)
    if frame == 'local':
        _pose(obj, obj.matrix() @ delta)
    else:
        m = obj.matrix()
        m[:3, 3] += [dx, dy, dz]
        m[:3, :3] = delta[:3, :3] @ m[:3, :3]
        _pose(obj, m)
    _edited(sim, obj)


def set_origin(sim, obj, where='bottom_center'):
    if obj.mesh is None:
        if where == 'bottom_center':
            return None
        return 'Dieser Ursprung ist für das parametrische Objekt nicht darstellbar.'
    verts, faces = obj.mesh
    lo, hi = verts.min(axis=0), verts.max(axis=0)
    if isinstance(where, str):
        if where not in ('bottom_center', 'center', 'top_center'):
            raise ValueError("Unbekannter Ursprung")
        shift = (lo+hi)/2
        shift[2] = {'bottom_center': lo[2], 'center': shift[2], 'top_center': hi[2]}[where]
    else:
        shift = np.asarray(where, float)
    obj.mesh = (verts-shift, faces)
    obj.mesh_offset = (np.asarray(obj.mesh_offset)+shift).tolist()
    obj.pos = (np.asarray(obj.pos)+obj.matrix()[:3, :3] @ shift).tolist()
    obj._glcache = None
    # Descendants keep their geometry in place when only the reference changes.
    for child in sim.scene:
        if child.parent == obj.name:
            child.local = (inv(obj.matrix()) @ child.matrix()).tolist()
    _edited(sim, obj)


def snap(sim, obj, target, face='top'):
    if face not in ('top', 'bottom', 'left', 'right', 'front', 'back'):
        raise ValueError("Unbekannte Fläche")
    axis, sign = {'top': (2, 1), 'bottom': (2, -1), 'left': (0, -1),
                  'right': (0, 1), 'front': (1, -1), 'back': (1, 1)}[face]
    lo = np.array([-target.size[0]/2, -target.size[1]/2, 0.])
    hi = lo + target.size
    if target.mesh is not None:
        lo, hi = target.mesh[0].min(axis=0), target.mesh[0].max(axis=0)
    pts = obj.mesh[0] if obj.mesh is not None else np.array(
        [[x, y, z] for x in (-obj.size[0]/2, obj.size[0]/2)
         for y in (-obj.size[1]/2, obj.size[1]/2) for z in (0, obj.size[2])])
    relative = inv(target.matrix()) @ obj.matrix()
    pts = pts @ relative[:3, :3].T + relative[:3, 3]
    own_lo, own_hi = pts.min(axis=0), pts.max(axis=0)
    center = (lo+hi)/2
    delta = center - (own_lo+own_hi)/2
    delta[axis] = (hi[axis] if sign > 0 else lo[axis]) - (own_lo[axis] if sign > 0 else own_hi[axis])
    obj.pos = (np.asarray(obj.pos)+target.matrix()[:3, :3] @ delta).tolist()
    _edited(sim, obj)


def align(sim, obj, target, mode='rotation'):
    if mode == 'rotation':
        obj.rot = list(target.rot)
    elif mode in ('x', 'y', 'z'):
        i = 'xyz'.index(mode)
        obj.pos[i] = target.pos[i]
    else:
        raise ValueError("Unbekannte Ausrichtung")
    _edited(sim, obj)


def conveyor_ends(o):
    """Return world start, end and end heading (degrees)."""
    if o.kind == 'conveyor_arc':
        a = math.radians(o.angle)
        sign = -1 if o.turn_right else 1
        start = [0, 0, o.size[2]]
        end = [o.radius*math.sin(a), sign*o.radius*(1-math.cos(a)), o.size[2]]
        heading = o.rot[0]+sign*o.angle
    elif o.kind == 'conveyor':
        start, end = [-o.size[0]/2, 0, o.size[2]], [o.size[0]/2, 0, o.size[2]]
        heading = o.rot[0]
    else:
        raise ValueError("Kein Förderband")
    m = o.matrix()
    return (m @ [*start, 1])[:3], (m @ [*end, 1])[:3], heading


def pnp(sim, obj, radius=400):
    supported = ('conveyor', 'conveyor_arc', 'sensor', 'spawner', 'sink', 'color_sensor')
    if obj.kind not in supported:
        return 'Für dieses Objekt ist Plug & Play nicht verfügbar.'
    belts = [o for o in sim.scene if o is not obj and o.kind in supported[:2]]
    probe = conveyor_ends(obj)[0] if obj.kind in supported[:2] else np.asarray(obj.pos)
    candidates = []
    for belt in belts:
        _, end, heading = conveyor_ends(belt)
        occupied = any(np.linalg.norm(conveyor_ends(b)[0]-end) < 5 for b in belts if b is not belt)
        if not occupied and np.linalg.norm(probe-end) <= radius:
            candidates.append((float(np.linalg.norm(probe-end)), end, heading))
    if not candidates:
        return 'Kein freies Förderbandende in Reichweite.'
    _, end, heading = min(candidates, key=lambda x: x[0])
    obj.rot = [heading, 0., 0.]
    start = conveyor_ends(obj)[0] if obj.kind in supported[:2] else np.asarray(obj.pos)
    obj.pos = (np.asarray(obj.pos)+end-start).tolist()
    _edited(sim, obj)
    return None


def measure(p, q):
    d = np.asarray(q, float)-np.asarray(p, float)
    return dict(dist=float(np.linalg.norm(d)), dx=float(d[0]), dy=float(d[1]), dz=float(d[2]))


def angle(a, vertex, b):
    u, v = np.asarray(a)-vertex, np.asarray(b)-vertex
    norm = np.linalg.norm(u)*np.linalg.norm(v)
    if norm == 0:
        raise ValueError("Winkel benötigt zwei Richtungen")
    return float(np.degrees(np.arccos(np.clip(np.dot(u, v)/norm, -1, 1))))


def add_dimension(sim, kind, pts):
    count = {'linear': 2, 'angle': 3}
    points = np.asarray(pts, float)
    if kind not in count or points.shape != (count[kind], 3) or not np.isfinite(points).all():
        raise ValueError("Ungültige Bemaßung")
    value = measure(*points)['dist'] if kind == 'linear' else angle(*points)
    d = dict(type=kind, pts=points.tolist(), label=f"{value:.1f} {'mm' if kind == 'linear' else '°'}")
    sim.dimensions.append(d)
    return d


def move_robot_frame(sim, robot, pose6, mode='reference'):
    if mode not in ('reference', 'world'):
        raise ValueError("Unbekannter Bezugsmodus")
    update_hierarchy(sim)
    children = [o for o in sim.scene if o.parent == robot.name+'@base']
    robot.set_root(pose6)
    if mode == 'world':
        for o in children:
            o.local = (inv(robot.robroot()) @ o.matrix()).tolist()
    update_hierarchy(sim)


def swap_robot(sim, robot, model_key):
    model = MODELS[model_key]
    robot.model_key, robot.model = model_key, model
    robot.q = np.clip(robot.q, model.limits[:, 0], model.limits[:, 1])
    robot.reset_program()
    robot.update_sv()
    update_hierarchy(sim)
