"""Read-only diagnostics for the model and robot programs."""
import re
import numpy as np
import xrl
from kinematics import pose_to_mat, inv
from editing import bounds, conveyor_ends


def analyze(sim):
    findings = []
    def report(level, text, obj=None):
        findings.append(dict(level=level, text=text, obj=obj))
    names = {o.name for o in sim.scene} | {r.name for r in sim.robots}
    linked = set()
    for link in sim.links:
        for key in ('src', 'dst'):
            name = link[key][0]
            linked.add(name)
            if name not in names:
                report('Fehler', f'Signalverbindung verweist auf fehlendes Objekt: {name}', name)
    for r in sim.robots:
        if not r.src.strip():
            report('Warnung', 'Roboter hat kein Programm.', r.name)
        else:
            try:
                xrl.Parser(xrl.tokenize(r.src)).program()
            except xrl.XrlError as exc:
                report('Fehler', f'XRL-Syntaxfehler: {exc}', r.name)
        for point in r.waypoints:
            p = point.get('pos', [])
            if len(p) < 6:
                report('Fehler', f'Ungültiger eingelehrter Punkt: {point.get("name", "?")}', r.name)
                continue
            target = r.base_world() @ pose_to_mat(*p[:6]) @ inv(r.tool_mat())
            # Conservative distance rejection avoids expensive IK for absurd coordinates.
            reach = r.model.reach + abs(r.model.a1) + abs(r.model.d1)
            es = [r.e1] if r.track is None else np.linspace(*r.e_limits(), 11)
            reachable = False
            for e in es:
                t = inv(r.robroot(e)) @ target
                if np.linalg.norm(t[:3, 3]) <= reach and r.model.ik(t, r.q) is not None:
                    reachable = True
                    break
            if not reachable:
                report('Fehler', f'Eingelehrter Punkt {point.get("name", "?")} ist nicht erreichbar.', r.name)
        collision = r.check_collision()
        if collision:
            report('Fehler', f'Aktuelle Kollision: {collision}', r.name)
        if not r.tool.grip_out and re.search(r'\$OUT\s*\[', r.src, re.I):
            report('Warnung', 'Programm verwendet Ausgänge, aber das Werkzeug hat keinen Greiferausgang; Greiferbelegung prüfen.', r.name)
    obstacles = []
    parents = {o.name: o.parent for o in sim.scene}
    def related(a, b):
        def ancestors(name):
            seen = set()
            while name in parents and parents[name] and name not in seen:
                seen.add(name)
                name = parents[name]
                yield name
        return a.name in ancestors(b.name) or b.name in ancestors(a.name)
    for o in sim.scene:
        if o.pos[2] < -1:
            report('Warnung', 'Objekt liegt unter dem Boden.', o.name)
        if o.kind in ('sensor', 'color_sensor', 'spawner', 'conveyor', 'conveyor_arc') and not any(
                [o.io, o.trigger, o.detected, *o.inputs.values(), *o.color_outs.values()]) and o.name not in linked:
            report('Warnung' if o.kind in ('sensor', 'color_sensor') else 'Hinweis',
                   'Keine Signalverbindung vorhanden; Signalbelegung prüfen.', o.name)
        if o.obstacle and o.kind != 'group':
            obstacles.append((o, *bounds(o)))
    for i, (a, lo, hi) in enumerate(obstacles):
        for b, blo, bhi in obstacles[i+1:]:
            if related(a, b) or (a.graspable and b.kind.startswith('conveyor')) or (b.graspable and a.kind.startswith('conveyor')):
                continue
            if (a.name, b.name) in sim.collision_ignore or (b.name, a.name) in sim.collision_ignore:
                continue
            if np.all(np.minimum(hi, bhi)-np.maximum(lo, blo) > 5):
                report('Warnung', f'Hindernisse überlappen: {a.name} und {b.name}.', a.name)
    belts = [(o, conveyor_ends(o)) for o in sim.scene if o.kind in ('conveyor', 'conveyor_arc')]
    for a, (_, end, heading) in belts:
        candidates = [(float(np.linalg.norm(end-start)), b) for b, (start, _, _) in belts
                      if b is not a and np.dot(start-end, [np.cos(np.radians(heading)), np.sin(np.radians(heading)), 0]) >= -1]
        if candidates:
            dist, b = min(candidates, key=lambda c: c[0])
            if 5 < dist <= 300:
                report('Hinweis', f'Förderbandlücke {dist:.1f} mm zu {b.name}; Plug & Play verwenden.', a.name)
    if sim.script_host:
        for line in sim.log:
            if 'Skriptfehler ' in line:
                report('Fehler', line, None)
        for error in getattr(sim.script_host, 'errors', []):
            report('Fehler', f'Skriptfehler: {error}', None)
    return findings
