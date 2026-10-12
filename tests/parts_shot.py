"""Alle Katalogteile nebeneinander zur Sichtpruefung: python tests/parts_shot.py -> parts_*.png"""
import sys, os, tempfile, pathlib
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'ximaj_robosim'))
from PyQt6.QtGui import QSurfaceFormat
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer
import numpy as np
fmt = QSurfaceFormat(); fmt.setSamples(8); fmt.setDepthBufferSize(24); fmt.setStencilBufferSize(8)
QSurfaceFormat.setDefaultFormat(fmt)
app = QApplication(sys.argv)
import theme, catalog, main
app.setStyleSheet(theme.stylesheet())

w = main.MainWindow(); w.resize(1600, 1000); w.show()
w.autosave.directory = pathlib.Path(tempfile.mkdtemp())  # nicht in echte Nutzerdaten
s, v = w.sim, w.viewer
v.show_frames = False; v.show_trail = False
s.robots[0].pos = [-6000, -6000, 0]
s.scene = []
items = [e for e in catalog.CATALOG if e["kind"] == "obj" and e["cat"] in ("Fördertechnik", "Zellenbau", "Werkstücke")
         and "Käfig" not in e["name"]]
x = y = 0.0
row_h = 0.0
for e in items:
    objs = catalog.apply(s, e, at=(x, y, 0.0))
    span = max(max(o.size[0], o.size[1]) for o in objs) + 500
    row_h = max(row_h, span)
    x += span
    if x > 7000:
        x, y, row_h = 0.0, y + row_h, 0.0
s.io.set_out(2, True)
VIEWS = {"total": (np.array([3500, 2500, 300]), 11000, 35, 30),
         "foerder": (np.array([1500, 0, 300]), 4200, 30, 22),
         "zelle": (np.array([4500, 2600, 500]), 6000, 40, 22)}
small = [o for o in s.scene if o.kind in ("sensor", "color_sensor", "lamp", "spawner", "sink")]
VIEWS["klein"] = (np.mean([o.pos for o in small], axis=0) + np.array([0, 0, 150]), 2600, 25, 20)
roll = next(o for o in s.scene if getattr(o, "style", "") == "roller")
VIEWS["rollen"] = (np.array(roll.pos) + np.array([0, 0, 400]), 2200, 60, 28)
jobs = list(VIEWS)


def step():
    if not jobs:
        w._saved_snapshot = w.history.current
        app.quit()
        return
    n = jobs.pop(0)
    v.center, v.dist, v.az, v.el = VIEWS[n]
    v.update()
    QTimer.singleShot(500, lambda: (v.grab().save(os.path.join(HERE, "..", f"parts_{n}.png")), print("saved", n, flush=True), step()))


QTimer.singleShot(1200, step)
app.exec()
