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
import theme, main, processes as pr
from sim import SceneObj
app.setStyleSheet(theme.stylesheet())
w = main.MainWindow(); w.resize(1600, 950); w.show()
s = w.sim
s.set_model("XR-15 (1.5 m, 12 kg)")
s.tool.tcp = [0, 0, 250, 0, 0, 0]
part = SceneObj("Blech", "box", (900, 0, 0), (15, 0, 0), (500, 350, 120), "#94a3b8", True, False)
rohr = SceneObj("Rohr", "cylinder", (850, -650, 0), (0, 0, 0), (180, 180, 250), "#94a3b8", True, False)
s.scene = [part, rohr]
res = pr.surface_process(s.active, part, width=70, overlap=15, standoff=150)
naht = pr.path_process(s.active, rohr, tilt=40)
res["preview"] += naht["preview"]
w.viewer.proc_preview = res
s.active.statements = naht["stmts"]
s.active.mode = "statements"
w.sync_from_sim()
w.bottom.setCurrentIndex(0)
v = w.viewer
v.dist, v.az, v.el, v.center = 3200, 20, 40, np.array([800.0, -250, 200])


def snap():
    w.grab().save(os.path.join(HERE, "..", "ui_main.png"))
    print("ok", res["report"])
    app.quit()


QTimer.singleShot(2500, snap)
app.exec()
