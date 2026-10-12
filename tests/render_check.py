"""Rendert Projekte zur Sichtpruefung: python tests/render_check.py <Projektname|zelle> [ausgabe.png]"""
import sys, os
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'ximaj_robosim'))
from PyQt6.QtGui import QSurfaceFormat
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer
import numpy as np

fmt = QSurfaceFormat(); fmt.setSamples(8); fmt.setDepthBufferSize(24); fmt.setStencilBufferSize(8)
QSurfaceFormat.setDefaultFormat(fmt)
app = QApplication(sys.argv)
import theme, main, vcmx_import, catalog
app.setStyleSheet(theme.stylesheet())
w = main.MainWindow(); w.resize(1900, 1100); w.show()
name = sys.argv[1] if len(sys.argv) > 1 else "Untitled"
out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, "..", "render.png")
v = w.viewer
if name.startswith("zelle"):
    e = [e for e in catalog.CATALOG if e["kind"] == "cell"][int(name[-1]) if name[-1].isdigit() else 0]
    catalog.apply(w.sim, e)
    w.sync_from_sim()
    v.dist, v.az, v.el, v.center = 3800, 35, 28, np.array([600.0, 0, 300])
else:
    f = os.path.join(r"C:\Users\FinnStetter\OneDrive - Ximaj IT-Solutions GmbH\Dokumente\KUKA\iiQWorks.Sim 1.3\My Models", name + ".vcmx")
    vcmx_import.import_file(w.sim, f)
    w.sync_from_sim()
    xs = [o.pos[0] for o in w.sim.scene] or [0]
    ys = [o.pos[1] for o in w.sim.scene] or [0]
    v.center = np.array([np.mean(xs), np.mean(ys), 300.0])
    v.dist, v.az, v.el = 13000, -95, 38


def snap():
    v.grabFramebuffer().save(out)
    print("gespeichert", out, v.width(), v.height())
    app.quit()


QTimer.singleShot(2500, snap)
app.exec()
