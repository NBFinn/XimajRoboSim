import sys, os, time, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'ximaj_robosim'))
import numpy as np
import cad
from sim import Simulation, SceneObj
step = r"C:\Users\FinnStetter\OneDrive - Ximaj IT-Solutions GmbH\Microsoft Teams-Chatdateien\Abschlussprojekt.step"
t0 = time.time()
V, F = cad.load_cad(step, tol=0.5)
print(f"STEP: {len(F)} Dreiecke, {time.time() - t0:.1f}s, Maße mm: {np.round(V.max(0) - V.min(0))}, z0={V[:, 2].min():.1f}")
V2, F2 = cad.simplify(V, F, 20000)
print(f"vereinfacht: {len(F2)} Dreiecke")
# DXF erzeugen und lesen
import ezdxf
p = os.path.join(tempfile.gettempdir(), "xrs_test.dxf")
d = ezdxf.new(); d.header["$INSUNITS"] = 4; msp = d.modelspace()
msp.add_lwpolyline([(0, 0), (8000, 0), (8000, 5000), (0, 5000)], close=True); msp.add_circle((4000, 2500), 600)
d.saveas(p)
lines, lo, hi = cad.load_dxf(p)
print("DXF:", len(lines), "Linien, Bereich", lo, hi)
# HTML-Export
s = Simulation()
s.scene = [SceneObj("Tisch", "box", (500, 0, 0), (0, 0, 0), (600, 1000, 20), "#64748b", True, False)]
h = os.path.join(tempfile.gettempdir(), "xrs_test.html")
n = cad.export_html(s, h)
print("HTML:", n // 1024, "KB")
