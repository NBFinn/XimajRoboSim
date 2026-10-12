"""Screenshot des Hauptfensters (und Startbild) zur Design-Pruefung."""
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
sys.excepthook = lambda et, ev, tb: __import__("traceback").print_exception(et, ev, tb)
import theme, main, catalog
app.setStyleSheet(theme.stylesheet())
sp = main.make_splash()
sp.pixmap().save(os.path.join(HERE, "..", "ui_splash.png"))
w = main.MainWindow(); w.resize(1600, 950); w.show()
import tempfile, pathlib; w.autosave.directory = pathlib.Path(tempfile.mkdtemp())  # nicht in echte Nutzerdaten
e = [e for e in catalog.CATALOG if e["kind"] == "cell"][1]
catalog.apply(w.sim, e); w.sync_from_sim(); w.editor.setPlainText(w.sim.src)
v = w.viewer
v.dist, v.az, v.el, v.center = 4200, 40, 28, np.array([650.0, 0, 350])


def snap():
    w.grab().save(os.path.join(HERE, "..", "ui_main.png"))
    print("ok")
    w._saved_snapshot = w.history.current  # keine Rückfrage beim Beenden
    app.quit()


QTimer.singleShot(2500, snap)
app.exec()
