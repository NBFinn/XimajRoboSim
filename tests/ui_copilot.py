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
import theme, main, copilot
app.setStyleSheet(theme.stylesheet())
w = main.MainWindow(); w.resize(1700, 1000); w.show()
cmds = ["Hilfe", "Roboter XR-15", "füge ein Förderband 3 m bei x 1200 y -900 hinzu", "Palette bei 900, 700",
        "neuer Roboter XR-9 bei x 2600 y 0", "Linearachse 3 m", "Senke bei x 2800 y -900", "drehe palette um 90 grad",
        "verschiebe tisch nach x 600 y 100", "Zaun um die Zelle", "Geschwindigkeit 60 %", "Zeit 2x",
        "lösche teil1", "was ist das wetter"]
for c in cmds:
    print(f"> {c}\n  {copilot.execute(w, c).splitlines()[0]}")
v = w.viewer
v.dist, v.az, v.el, v.center = 9500, 35, 40, np.array([1300.0, 0, 300])


def snap():
    w.grab().save(os.path.join(HERE, "..", "ui_main.png"))
    app.quit()


QTimer.singleShot(2500, snap)
app.exec()
