"""Maus-Interaktion in der 3D-Ansicht: Achsenkreuz ziehen, Drehring, Messen, Rahmenauswahl, Jog am TCP."""
import sys, os, traceback
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'ximaj_robosim'))
import numpy as np
from PyQt6.QtGui import QSurfaceFormat
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer, Qt, QPoint
from PyQt6.QtTest import QTest
fmt = QSurfaceFormat(); fmt.setSamples(4); fmt.setDepthBufferSize(24); fmt.setStencilBufferSize(8)
QSurfaceFormat.setDefaultFormat(fmt)
app = QApplication(sys.argv)
errors = []
sys.excepthook = lambda et, ev, tb: errors.append("".join(traceback.format_exception(et, ev, tb)))
import theme, main, catalog
w = main.MainWindow(); w.resize(1500, 950); w.show()
import tempfile, pathlib; w.autosave.directory = pathlib.Path(tempfile.mkdtemp())  # nicht in echte Nutzerdaten
v = w.viewer
res = {}


def drag(a, b, mod=Qt.KeyboardModifier.NoModifier):
    a, b = QPoint(int(a[0]), int(a[1])), QPoint(int(b[0]), int(b[1]))
    QTest.mousePress(v, Qt.MouseButton.LeftButton, mod, a)
    for k in range(1, 11):
        QTest.mouseMove(v, a + (b - a) * k / 10)
        app.processEvents()
    QTest.mouseRelease(v, Qt.MouseButton.LeftButton, mod, b)
    app.processEvents()


def run():
    try:
        o = next(x for x in w.sim.scene if x.kind in ("box", "conveyor"))
        v.selected, v.selection = o, [o]
        w.ribbon.set_mode("move")
        v.snap_always = False
        p0 = np.array(o.pos, float)
        org, R, L = v._gizmo_frame()
        a, _ = v._project(org + R[:, 0] * L * 0.8)
        c, _ = v._project(org)
        drag(a, a + (a - c) * 0.8)
        res["x verschoben"] = round(o.pos[0] - p0[0], 1)
        res["y/z unverändert"] = bool(abs(o.pos[1] - p0[1]) < 1e-6 and abs(o.pos[2] - p0[2]) < 1e-6)
        r0 = o.rot[0]
        org, R, L = v._gizmo_frame()
        rp, _ = v._project(org + L * 0.8 * np.array([0.7071, -0.7071, 0]))
        rq, _ = v._project(org + L * 0.8 * np.array([0.7071, 0.7071, 0]))
        drag(rp, rq)
        res["gedreht (°)"] = round(o.rot[0] - r0, 1)
        # Messen
        w.ribbon.set_mode("measure")
        for P in (org, org + np.array([1000.0, 0, 0])):
            q, _ = v._project(P)
            QTest.mouseClick(v, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(int(q[0]), int(q[1])))
            app.processEvents()
        res["Messung (mm)"] = round(v.measure_result["dist"], 1) if v.measure_result else None
        # Rahmenauswahl
        w.ribbon.set_mode("select")
        drag((5, 5), (v.width() - 5, v.height() - 5), Qt.KeyboardModifier.ShiftModifier)
        res["Rahmenauswahl"] = len(v.selection)
        # Jog am TCP
        w.ribbon.set_mode("jog")
        r = w.sim.active
        t0 = r.tcp_world()[:3, 3].copy()
        org, R, L = v._gizmo_frame()
        a, _ = v._project(org + R[:, 2] * L * 0.8)
        c, _ = v._project(org)
        drag(a, a + (a - c) * 0.5)
        res["TCP dZ (mm)"] = round(r.tcp_world()[2, 3] - t0[2], 1)
        v.grab().save(os.path.join(HERE, "..", "ui_gizmo.png"))
    except Exception:
        errors.append(traceback.format_exc())
    print(res)
    print("Fehler:", len(errors))
    for e in errors[:5]:
        print(e[-1200:])
    w._saved_snapshot = w.history.current  # keine Rückfrage beim Beenden
    app.quit()


QTimer.singleShot(1500, run)
app.exec()
