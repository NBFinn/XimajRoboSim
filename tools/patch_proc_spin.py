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


patch("processes.py", [
    ('''def _lift(M, dz):''', '''def _spin_fit(robot, poses, spin_free=True):
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


def _lift(M, dz):'''),
    # Bahnprozess
    ('''    poses.append(poses[0].copy())            # Kontur schliessen
    stmts = [stm.new("COMMENT", text=f"Bahnprozess an {o.name}: {L:.0f} mm, {n} Punkte")]''',
     '''    poses.append(poses[0].copy())            # Kontur schliessen
    poses, bad = _spin_fit(robot, poses, spin_free)
    stmts = [stm.new("COMMENT", text=f"Bahnprozess an {o.name}: {L:.0f} mm, {n} Punkte")]'''),
    ('''    stmts.append(stm.new("LIN", pos=_to_base(robot, _lift(poses[-1], approach)), vel=0.5, name="Abfahrt"))
    bad = sum(0 if _reachable(robot, M) else 1 for M in poses)
    t = L / 1000.0 / max(speed, 1e-6) + 2 * approach / 500.0 + 1.5''', '''    stmts.append(stm.new("LIN", pos=_to_base(robot, _lift(poses[-1], approach)), vel=0.5, name="Abfahrt"))
    t = L / 1000.0 / max(speed, 1e-6) + 2 * approach / 500.0 + 1.5'''),
    ('''                 approach=80.0, speed=0.15, out_nr=0, reverse=False):''',
     '''                 approach=80.0, speed=0.15, out_nr=0, reverse=False, spin_free=True):'''),
    # Punktprozess
    ('''    stmts = [stm.new("COMMENT", text=f"Punktprozess an {o.name}: {len(poses)} Punkte")]''',
     '''    poses, bad = _spin_fit(robot, poses, spin_free)
    stmts = [stm.new("COMMENT", text=f"Punktprozess an {o.name}: {len(poses)} Punkte")]'''),
    ('''    bad = sum(0 if _reachable(robot, Mp) else 1 for Mp in poses)
    t = len(poses) * (2 * approach / 300.0 + dwell + 0.4)''', '''    t = len(poses) * (2 * approach / 300.0 + dwell + 0.4)'''),
    ('''                  approach=60.0, dwell=0.3, out_nr=0, tilt=0.0):''',
     '''                  approach=60.0, dwell=0.3, out_nr=0, tilt=0.0, spin_free=True):'''),
])
print("ok")
