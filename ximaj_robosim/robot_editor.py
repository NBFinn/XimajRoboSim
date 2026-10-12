"""Roboter-Editor: eigene 6-Achs-Roboter anlegen, aus Vorlagen ableiten, speichern und loeschen."""
import math
import os
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QGridLayout, QComboBox, QLineEdit,
                             QDoubleSpinBox, QLabel, QPushButton, QGroupBox, QMessageBox, QFileDialog, QColorDialog)
from PyQt6.QtGui import QColor

import robot_library
from kinematics import MODELS, RobotModel

DIMS = [("a1", "Schulterversatz X", "Abstand A1-Achse → A2-Achse waagerecht"),
        ("d1", "Schulterhöhe", "Fußunterkante → A2-Achse"),
        ("a2", "Oberarm", "A2-Achse → A3-Achse"),
        ("a3", "Unterarmversatz", "Versatz des Unterarms über der A3-Achse"),
        ("d4", "Unterarm", "A3-Achse → Handwurzelpunkt"),
        ("d6", "Hand", "Handwurzelpunkt → Flansch")]


LINKS = ["Fuß (fest)", "Karussell A1", "Schwinge A2", "Arm A3", "Hand A4", "Hand A5", "Flansch A6"]


def _spin(lo, hi, val, dec=1, step=1.0):
    s = QDoubleSpinBox()
    s.setRange(lo, hi)
    s.setDecimals(dec)
    s.setSingleStep(step)
    s.setValue(val)
    return s


def entry_from_model(key, m):
    return {"key": key, "maker": getattr(m, "maker", "Eigene"), "model": key,
            "dims": [m.a1, m.d1, m.a2, m.a3, m.d4, m.d6], "limits": [list(map(float, l)) for l in m.limits],
            "vmax": [float(v) for v in m.vmax], "payload": float(m.payload or 0), "reach": float(m.reach)}


def row_widget(*ws):
    from PyQt6.QtWidgets import QWidget
    w = QWidget()
    h = QHBoxLayout(w)
    h.setContentsMargins(0, 0, 0, 0)
    for x in ws:
        h.addWidget(x)
    return w


class RobotEditor(QDialog):
    """Bearbeitet Eintraege der Benutzerbibliothek; Herstellervorlagen dienen nur als Ausgangspunkt."""

    def __init__(self, parent=None, start_key=None):
        super().__init__(parent)
        self.setWindowTitle("Roboter-Editor")
        self.saved_key = None
        L = QVBoxLayout(self)
        top = QFormLayout()
        self.tpl = QComboBox()
        self.tpl.addItems(list(MODELS))
        if start_key in MODELS:
            self.tpl.setCurrentText(start_key)
        self.tpl.currentTextChanged.connect(self.load_template)
        top.addRow("Vorlage", self.tpl)
        self.name = QLineEdit()
        self.name.setPlaceholderText("z. B. Mein Roboter 1400")
        top.addRow("Name", self.name)
        L.addLayout(top)

        g = QGroupBox("Kinematik (mm)")
        f = QFormLayout(g)
        self.dim = {}
        for k, label, tip in DIMS:
            s = _spin(-5000, 5000, 0, 1, 5)
            s.setToolTip(tip)
            s.valueChanged.connect(self.check)
            self.dim[k] = s
            f.addRow(f"{label} ({k})", s)
        L.addWidget(g)

        g2 = QGroupBox("Achsen")
        grid = QGridLayout(g2)
        for c, h in enumerate(("", "min °", "max °", "v max °/s")):
            grid.addWidget(QLabel(h), 0, c)
        self.lo, self.hi, self.vm = [], [], []
        for i in range(6):
            grid.addWidget(QLabel(f"A{i + 1}"), i + 1, 0)
            for c, lst, rng in ((1, self.lo, (-400, 400)), (2, self.hi, (-400, 400)), (3, self.vm, (1, 2000))):
                s = _spin(*rng, 0, 1, 5)
                s.valueChanged.connect(self.check)
                grid.addWidget(s, i + 1, c)
                lst.append(s)
        L.addWidget(g2)
        pf = QFormLayout()
        self.payload = _spin(0, 5000, 10, 1, 1)
        pf.addRow("Traglast (kg)", self.payload)
        self.paint = None
        self.b_paint = QPushButton("Standard (Ximaj-Blau)")
        self.b_paint.clicked.connect(self.pick_paint)
        pf.addRow("Lackfarbe", self.b_paint)
        L.addLayout(pf)

        g3 = QGroupBox("CAD-Geometrie je Glied (optional)")
        g3l = QGridLayout(g3)
        hint = QLabel("STEP/IGES/STL/OBJ/GLB je Glied, exportiert in Nullstellung (alle Achsen 0°) im "
                      "Roboterfuß-Koordinatensystem in mm – z. B. die CAD-Daten, die der Hersteller "
                      "für Ihren Roboter bereitstellt. Leere Glieder werden automatisch modelliert.")
        hint.setWordWrap(True)
        hint.setObjectName("muted")
        g3l.addWidget(hint, 0, 0, 1, 3)
        self.cad = {}
        self.cad_lbl = []
        for i, nm in enumerate(LINKS):
            g3l.addWidget(QLabel(nm), i + 1, 0)
            lb = QLabel("–")
            lb.setObjectName("muted")
            self.cad_lbl.append(lb)
            g3l.addWidget(lb, i + 1, 1)
            bb = QPushButton("Datei …")
            bb.clicked.connect(lambda _=False, k=i: self.pick_cad(k))
            bx = QPushButton("✕")
            bx.setFixedWidth(34)
            bx.clicked.connect(lambda _=False, k=i: self.set_cad(k, None))
            g3l.addWidget(row_widget(bb, bx), i + 1, 2)
        L.addWidget(g3)

        self.info = QLabel()
        self.info.setWordWrap(True)
        self.info.setObjectName("muted")
        L.addWidget(self.info)
        b = QHBoxLayout()
        self.b_del = QPushButton("Eigenen Roboter löschen")
        self.b_del.setObjectName("danger")
        self.b_del.clicked.connect(self.delete)
        b_save = QPushButton("Speichern")
        b_save.setObjectName("primary")
        b_save.clicked.connect(self.save)
        b_close = QPushButton("Schließen")
        b_close.clicked.connect(self.reject)
        b.addWidget(self.b_del)
        b.addStretch(1)
        b.addWidget(b_close)
        b.addWidget(b_save)
        L.addLayout(b)
        self.load_template(self.tpl.currentText())

    def _user_keys(self):
        return {e.get("key") for e in robot_library.load_user()}

    def load_template(self, key):
        m = MODELS.get(key)
        if m is None:
            return
        own = key in self._user_keys()
        self.name.setText(key if own else f"{key} (Kopie)")
        for k, _, _ in DIMS:
            self.dim[k].setValue(float(getattr(m, k)))
        for i in range(6):
            self.lo[i].setValue(float(m.limits[i][0]))
            self.hi[i].setValue(float(m.limits[i][1]))
            self.vm[i].setValue(float(m.vmax[i]))
        self.payload.setValue(float(m.payload or 0))
        self.cad = {}
        for k in range(7):
            self.set_cad(k, (getattr(m, "cad", None) or {}).get(str(k)))
        self.set_paint(getattr(m, "paint", None))
        self.b_del.setEnabled(own)
        self.check()

    def entry(self):
        dims = [self.dim[k].value() for k, _, _ in DIMS]
        a1, d1, a2, a3, d4, d6 = dims
        return {"key": self.name.text().strip(), "maker": "Eigene", "model": self.name.text().strip(), "dims": dims,
                "limits": [[self.lo[i].value(), self.hi[i].value()] for i in range(6)],
                "vmax": [s.value() for s in self.vm], "payload": self.payload.value(),
                "cad": dict(self.cad), "paint": self.paint,
                "reach": a2 + math.hypot(a3, d4) + d6}

    def check(self):
        e = self.entry()
        errs = robot_library.validate(e)
        if not e["key"]:
            errs.insert(0, "Name fehlt.")
        if errs:
            self.info.setText("⚠ " + " ".join(errs))
        else:
            self.info.setText(f"Reichweite (Handwurzel + Hand): {e['reach']:.0f} mm · Höhe A2-Achse {e['dims'][1]:.0f} mm")
        return errs

    def save(self):
        e = self.entry()
        if self.check():
            return
        key = e["key"]
        builtin = key in MODELS and key not in self._user_keys()
        if builtin:
            QMessageBox.warning(self, "Roboter-Editor", "Dieser Name gehört zu einem mitgelieferten Modell. Bitte einen eigenen Namen wählen.")
            return
        robot_library.save_user(e)
        m = RobotModel(key, *e["dims"], e["limits"], e["vmax"], e["payload"])
        m.maker = "Eigene"
        m.cad = dict(e["cad"])
        m.paint = e["paint"]
        MODELS[key] = m
        self.saved_key = key
        self.accept()

    def pick_cad(self, k):
        fn, _ = QFileDialog.getOpenFileName(self, f"CAD für {LINKS[k]}", "",
                                            "CAD (*.step *.stp *.iges *.igs *.stl *.obj *.ply *.glb *.gltf *.3mf)")
        if fn:
            self.set_cad(k, fn)

    def set_cad(self, k, path):
        if path:
            self.cad[str(k)] = path
        else:
            self.cad.pop(str(k), None)
        self.cad_lbl[k].setText(os.path.basename(path) if path else "–")
        self.cad_lbl[k].setToolTip(path or "")

    def pick_paint(self):
        c = QColorDialog.getColor(QColor(self.paint or "#0e74bb"), self, "Lackfarbe")
        if c.isValid():
            self.set_paint(c.name())

    def set_paint(self, hexcol):
        self.paint = hexcol
        self.b_paint.setText(hexcol or "Standard (Ximaj-Blau)")
        self.b_paint.setStyleSheet(f"background:{hexcol}; color:#fff;" if hexcol else "")

    def delete(self):
        key = self.tpl.currentText()
        if key not in self._user_keys():
            return
        if QMessageBox.question(self, "Roboter-Editor", f"„{key}“ aus der eigenen Bibliothek löschen?") != QMessageBox.StandardButton.Yes:
            return
        robot_library.delete_user(key)
        self.saved_key = None
        self.accept()
