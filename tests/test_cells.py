import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'ximaj_robosim'))
import catalog
from sim import Simulation

for e in catalog.CATALOG:
    if e["kind"] != "cell":
        continue
    s = Simulation()
    catalog.apply(s, e)
    s.speed_factor = 1
    s.start()
    for i in range(60 * 150):
        s.tick(1 / 60)
        if s.state in ("idle", "error", "stopped"):
            break
    print(e["name"], "->", s.state, round(s.t, 1), "|", s.message)
    placed = [(o.name, round(o.pos[0]), round(o.pos[1]), round(o.pos[2])) for o in s.scene if o.graspable]
    print("   ", placed[:8])
    errs = [l for l in s.log if "KOLL" in l or "nicht" in l or "fehler" in l.lower()]
    print("   Probleme:", errs[:3])
