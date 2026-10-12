"""Nahaufnahmen des Roboters zur Sichtpruefung: python tests/robot_shot.py [Modell ...] -> robot_<Modell>_<Pose>.png"""
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
import theme, kinematics, main
app.setStyleSheet(theme.stylesheet())

names = [next(k for k in kinematics.MODELS if k == a or k.startswith(a + " ")) for a in (sys.argv[1:] or ["XR-11"])]
POSES = {"home": [0, -90, 90, 0, 90, 0], "work": [35, -60, 110, 40, 55, -30]}
w = main.MainWindow(); w.resize(1500, 1000); w.show()
s, v = w.sim, w.viewer
v.show_frames = False; v.show_trail = False
jobs = [(n, p) for n in names for p in POSES]


def step():
    if not jobs:
        app.quit()
        return
    n, p = jobs.pop(0)
    s.active.set_model(n)
    if os.environ.get("CADTEST"):                    # Pruefung der CAD-Glieder mit Testdateien
        s.active.model.cad = {"2": os.path.join(os.environ["CADTEST"], "link2.stl"), "3": os.path.join(os.environ["CADTEST"], "link3.stl")}
        s.active.model.paint = "#f07d00"
    s.active.q = np.array(POSES[p], float)
    R = s.active.model.reach
    v.dist, v.az, v.el = R * 1.7, 35, 15
    v.center = np.array([R * 0.25, 0, R * 0.5]); s.scene = []
    v.update()
    QTimer.singleShot(400, lambda: (v.grab().save(os.path.join(HERE, "..", f"robot_{n.split()[0]}_{p}.png")), print("saved", n, p, flush=True), step()))


QTimer.singleShot(800, step)
app.exec()
