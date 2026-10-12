"""Debug: bis zum ersten Planungsfehler laufen und Ziel/IK ausgeben.  python tests/dbg_motion.py <Projekt>"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'ximaj_robosim'))
import numpy as np
from sim import Simulation, PlanError
import vcmx_import
from kinematics import mat_to_pose, inv
f = r"C:\Users\FinnStetter\OneDrive - Ximaj IT-Solutions GmbH\Dokumente\KUKA\iiQWorks.Sim 1.3\My Models\{}.vcmx".format(sys.argv[1])
s = Simulation()
r = vcmx_import.import_file(s, f)
s.load_program(r["main_program"])
s.stop_on_collision = False
rb = s.active
for name in ("plan_lin", "plan_ptp"):
    orig = getattr(rb, name)

    def wrap(tgt, rel=False, _o=orig, _n=name):
        try:
            return _o(tgt, rel)
        except PlanError as e:
            print(f"{_n} FEHLER: {e}\n  Ziel: {tgt}\n  q: {np.round(rb.q, 1)}  E1: {rb.e1}  Track: {rb.track}")
            if tgt[0] == "pos":
                e = rb._e_target(tgt)
                T = rb.target_flange_robot(tgt, e)
                print("  Flansch-Ziel (Roboter):", np.round(mat_to_pose(T), 1), " Abstand:", round(float(np.linalg.norm(T[:3, 3])), 0),
                      " Reichweite:", round(rb.model.reach))
                for sol in rb.model.ik_all(T):
                    print("   IK:", [None if v is None else round(v, 1) for v in sol[:6]])
            raise
    setattr(rb, name, wrap)
s.start()
for i in range(3000):
    s.tick(1 / 60)
    if s.state in ("idle", "error", "stopped"):
        break
print(s.state, s.message)
lines = r["main_program"].splitlines()
print("Zeile:", lines[s.cur_line - 1][:160] if s.cur_line else "")
print("Limits:", rb.model.limits.tolist())
