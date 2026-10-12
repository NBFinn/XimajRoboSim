"""Klickt jede Schaltflaeche des Menuebands einmal (Dialoge werden automatisch abgebrochen) und meldet Fehler."""
import sys, os, traceback
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'ximaj_robosim'))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt6.QtWidgets import (QApplication, QDialog, QMessageBox, QInputDialog, QFileDialog, QToolButton, QCheckBox,
                             QRadioButton, QColorDialog)
from PyQt6.QtCore import QTimer
app = QApplication(sys.argv)
errors = []
sys.excepthook = lambda et, ev, tb: errors.append("".join(traceback.format_exception(et, ev, tb)))

# Dialoge nicht blockieren lassen
QDialog.exec = lambda self: int(os.environ.get("DLG_OK", "0"))
QMessageBox.exec = lambda self: QMessageBox.StandardButton.No
QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok)
for n in ("warning", "critical"):
    setattr(QMessageBox, n, staticmethod(lambda *a, **k: (errors.append("WARNUNG: " + str(a[2] if len(a) > 2 else a)),
                                                           QMessageBox.StandardButton.Ok)[1]))
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.No)
QInputDialog.getItem = staticmethod(lambda *a, **k: ("", False))
QInputDialog.getText = staticmethod(lambda *a, **k: ("", False))
QInputDialog.getInt = staticmethod(lambda *a, **k: (0, False))
QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: ("", ""))
QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: ("", ""))
QFileDialog.getExistingDirectory = staticmethod(lambda *a, **k: "")
QColorDialog.getColor = staticmethod(lambda *a, **k: __import__("PyQt6.QtGui", fromlist=["QColor"]).QColor())

import theme, main, catalog, tempfile
_tmp = tempfile.mkdtemp()
catalog.user_dirs = lambda: [_tmp]              # Test schreibt nichts in den echten Katalog
app.setStyleSheet(theme.stylesheet())
w = main.MainWindow()
import tempfile, pathlib; w.autosave.directory = pathlib.Path(tempfile.mkdtemp())  # nicht in echte Nutzerdaten
w.resize(1600, 950)
w.show()
e = [e for e in catalog.CATALOG if e["kind"] == "cell"][1]
catalog.apply(w.sim, e)
w.sync_from_sim()
w.viewer.selected = w.sim.scene[0]
w.viewer.selection = [w.sim.scene[0]]
skip = {"Beenden", "Start", "Online-Aufzeichnung"}
count = 0


def run():
    global count
    rb = w.ribbon.rb
    for title, page in rb.pages.items():
        rb.select(title)
        for gname, g in page.groups.items():
            for text, wd in list(g.items.items()):
                if text in skip:
                    continue
                n0 = len(errors)
                try:
                    if isinstance(wd, (QCheckBox, QRadioButton)):
                        wd.click()
                        wd.click() if isinstance(wd, QCheckBox) else None
                    elif isinstance(wd, QToolButton):
                        if wd.menu():
                            for a in wd.menu().actions():
                                if a.text() and not a.isSeparator():
                                    a.trigger()
                        else:
                            wd.click()
                            if wd.isCheckable() and wd.isChecked():
                                wd.click()
                    count += 1
                except Exception:
                    errors.append(traceback.format_exc())
                app.processEvents()
                if len(errors) > n0:
                    errors[-1] = f"[{title} › {gname} › {text}]\n" + errors[-1]
    w.ribbon.bs.show_stage()
    w.ribbon._fill_backstage()
    w.ribbon.bs.hide_stage()
    print(f"{count} Bedienelemente ausgelöst, {len(errors)} Fehler")
    for e in errors[:30]:
        print("-" * 60)
        print(e[-1500:])
    w._saved_snapshot = w.history.current  # keine Rückfrage beim Beenden
    app.quit()


QTimer.singleShot(800, run)
app.exec()
