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
import theme, main, catalog, viewer
from OpenGL.GL import glColor4f, glGetIntegerv, GL_STENCIL_BITS, glGetError
w = main.MainWindow(); w.resize(1500, 1000); w.show()
e = [e for e in catalog.CATALOG if e["kind"] == "cell"][1]
catalog.apply(w.sim, e); w.sync_from_sim()
v = w.viewer
v.dist, v.az, v.el, v.center = 4500, 35, 35, np.array([700.0, 0, 300])
orig = v._col


def col(*c):
    if v._shadow:
        glColor4f(1, 0, 0, 1)
    else:
        orig(*c)


v._col = col
calls = {"n": 0}
osp = v._shadow_pass


def sp():
    calls["n"] += 1
    osp()


v._shadow_pass = sp


def snap():
    v.makeCurrent()
    try:
        print("Stencil-Bits:", glGetIntegerv(GL_STENCIL_BITS))
    except Exception as ex:
        print("Stencil-Abfrage:", ex)
    print("Schattenaufrufe:", calls["n"], "shadows:", v.shadows, "light:", v.light_mode)
    v.grabFramebuffer().save(os.path.join(HERE, "..", "render.png"))
    app.quit()


QTimer.singleShot(2000, snap)
app.exec()
