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
import theme, main
app.setStyleSheet(theme.stylesheet())
w = main.MainWindow(); w.resize(1600, 950); w.show()
w.add_robot("XR-20 (2.0 m, 16 kg)")
w.sim.active.set_track(e_min=0, e_max=4000, vmax=1500)
w.sim.active.e1 = 1500
w.sync_from_sim()
w.left_tabs = w.findChildren(main.QTabWidget)[0]
w.left_tabs.setCurrentIndex(2)
v = w.viewer
v.dist, v.az, v.el, v.center = 7500, 35, 30, np.array([1500.0, 1200, 400])


def snap():
    w.grab().save(os.path.join(HERE, "..", "ui_main.png"))
    print("ok", [r.name for r in w.sim.robots])
    app.quit()


QTimer.singleShot(2500, snap)
app.exec()
