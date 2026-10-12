"""Bahn-, Punkt- und Flaechenprozess erzeugen und den Bahnprozess ausfuehren."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'ximaj_robosim'))
import statements as stm
import processes as pr
from sim import Simulation, SceneObj

s = Simulation()
s.set_model("XR-15 (1.5 m, 12 kg)")
r = s.active
r.tool.tcp = [0, 0, 250, 0, 0, 0]
r.tool.radius = 15
r.tool.grip_out = 0
part = SceneObj("Werkstück", "box", (850, 0, 0), (20, 0, 0), (300, 200, 150), "#94a3b8", True, False)
cyl = SceneObj("Rohr", "cylinder", (800, -450, 0), (0, 0, 0), (160, 160, 200), "#94a3b8", True, False)
s.scene = [part, cyl]
for name, fn, kw in (("Bahn (Box)", pr.path_process, dict(o=part, tilt=40, offset=0, out_nr=7)),
                     ("Bahn (Zylinder)", pr.path_process, dict(o=cyl, tilt=40, out_nr=7)),
                     ("Punkte Kontur", pr.point_process, dict(o=part, mode="kontur", spacing=120, out_nr=8)),
                     ("Punkte Raster", pr.point_process, dict(o=part, mode="raster", grid=(3, 2))),
                     ("Fläche", pr.surface_process, dict(o=part, width=60, overlap=20, standoff=120, out_nr=9))):
    res = fn(r, **kw)
    print(f"{name:16s}", res["report"], "| Bausteine:", len(res["stmts"]))
res = pr.path_process(r, cyl, tilt=40, out_nr=7)
r.statements, r.mode = res["stmts"], "statements"
src, lm = stm.generate(r.statements, "naht")
r.load_program(src)
s.stop_on_collision = False
s.start_all()
for i in range(60 * 120):
    s.tick(1 / 60)
    if not s.any_busy():
        break
print("Ausführung:", r.state, "| Laufzeit", round(r.run_t, 1), "s |", s.message, "| Kollision:", r.collision)
