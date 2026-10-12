"""Ximaj RoboSim - Hauptprogramm (Ximaj IT Solutions)."""
import sys
import os

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import update as upd
_APPLIED = upd.apply_pending()      # ausstehendes Update VOR allen weiteren Imports einspielen

import io as _io
import json
import contextlib
import threading
import traceback
import numpy as np

from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QRegularExpression
from PyQt6.QtGui import (QAction, QColor, QFont, QSyntaxHighlighter, QTextCharFormat, QTextFormat, QTextCursor,
                         QPainter, QPixmap, QIcon)
from PyQt6.QtWidgets import (QApplication, QMainWindow, QDockWidget, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QPushButton, QListWidget, QListWidgetItem, QDoubleSpinBox, QSpinBox, QComboBox, QCheckBox, QTabWidget,
                             QPlainTextEdit, QFileDialog, QMessageBox, QSlider, QGroupBox, QFormLayout, QGridLayout,
                             QTableWidget, QTableWidgetItem, QToolBar, QMenu, QColorDialog, QLineEdit, QProgressBar,
                             QScrollArea, QDialog, QDialogButtonBox, QTextEdit, QHeaderView, QSizePolicy, QAbstractItemView)

import theme
from version import VERSION
from kinematics import MODELS, HOME, pose_to_mat, mat_to_pose, inv, rx, ry, rz
from sim import Simulation, SceneObj, Tool, DEFAULT_PROGRAM
from viewer import Viewer
from opcua_srv import OpcUaService, AVAILABLE as OPC_AVAILABLE
import xrl
import catalog
import statements as stm
import processes as proc
import cad
import copilot
import vcmx_import
import modeling
import part_geom
from history import History, Autosave, tracked
import project_store
from code_editor import CodeEditor

B = theme.BRAND
SETTINGS = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "XimajRoboSim", "settings.json")


def load_settings():
    try:
        return json.load(open(SETTINGS, encoding="utf8"))
    except Exception:
        return {}


def save_settings(d):
    try:
        os.makedirs(os.path.dirname(SETTINGS), exist_ok=True)
        project_store.atomic_json(SETTINGS, d)
    except Exception:
        pass


# ------------------------------------------------------------------ Editor
class XrlHighlighter(QSyntaxHighlighter):
    def __init__(self, doc):
        super().__init__(doc)
        self.rules = []

        def fmt(color, bold=False):
            f = QTextCharFormat()
            f.setForeground(QColor(color))
            if bold:
                f.setFontWeight(700)
            return f
        kw = "|".join(sorted(xrl.KEYWORDS - {"TRUE", "FALSE"}, key=len, reverse=True))
        self.rules.append((QRegularExpression(rf"\b({kw})\b", QRegularExpression.PatternOption.CaseInsensitiveOption),
                           fmt(B["accent_dark"], True)))
        self.rules.append((QRegularExpression(r"\b(TRUE|FALSE)\b", QRegularExpression.PatternOption.CaseInsensitiveOption),
                           fmt("#c4a7ff")))
        self.rules.append((QRegularExpression(r"\$[A-Za-z_][A-Za-z_0-9]*"), fmt("#5eead4")))
        self.rules.append((QRegularExpression(r"\b\d+(\.\d+)?\b"), fmt("#fbbf24")))
        self.rules.append((QRegularExpression(r"[;&].*$"), fmt("#7f93b3")))

    def highlightBlock(self, text):
        for rx_, f in self.rules:
            it = rx_.globalMatch(text)
            while it.hasNext():
                m = it.next()
                self.setFormat(m.capturedStart(), m.capturedLength(), f)


# ------------------------------------------------------------------ Hilfen
def spin(lo, hi, val, dec=1, step=1.0, suffix="", cb=None, w=None):
    s = QDoubleSpinBox()
    s.setRange(lo, hi)
    s.setDecimals(dec)
    s.setSingleStep(step)
    s.setValue(val)
    if suffix:
        s.setSuffix(suffix)
    s.setKeyboardTracking(False)
    if cb:
        s.valueChanged.connect(cb)
    if w:
        s.setMaximumWidth(w)
    return s


def row(*widgets):
    w = QWidget()
    l = QHBoxLayout(w)
    l.setContentsMargins(0, 0, 0, 0)
    for x in widgets:
        l.addWidget(x)
    return w


class MainWindow(QMainWindow):
    update_found = pyqtSignal(dict)
    update_progress = pyqtSignal(float)
    update_done = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._restoring = True
        self._change_depth = 0
        self.settings = load_settings()
        catalog.load_user_catalog()
        self.sim = Simulation()
        self.sim.scene = default_scene()
        self.sim.tool.grip_out = 1
        self.opc = OpcUaService(self.sim)
        self.project_path = None
        self.jog = None
        self.recording = False
        self.frames = []
        self._rec_t = 0
        self.last_info = None
        self._ui_t = 0
        self.setWindowTitle(f"{B['product']} {VERSION} - {B['company']}")
        self.resize(1700, 1000)
        self.viewer = Viewer(self.sim)
        self.viewer.light_mode = bool(self.settings.get("light_mode", False))   # Standard: dunkle Ximaj-Halle
        self.viewer.picked.connect(self.on_pick)
        self.setCentralWidget(self.viewer)
        self._build_menu()
        self._build_toolbar()
        self._build_docks()
        import ui_ribbon
        self.ribbon = ui_ribbon.RibbonUI(self)          # Menueband ersetzt die klassische Menueleiste
        self.statusBar().showMessage(f"{B['product']} {VERSION}  |  {B['tagline']}")
        self.update_found.connect(self.on_update_found)
        self.update_progress.connect(lambda f: self.up_bar.setValue(int(f * 100)))
        self.update_done.connect(self.on_update_done)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.on_tick)
        self.timer.start(16)
        import time
        self._t_last = time.perf_counter()
        self.sim.on_message = None
        self.refresh_scene_list()
        self.history = History(self.sim)
        self.autosave = Autosave()
        self._saved_snapshot = self.history.current
        self._restoring = False
        self.editor.textChanged.connect(self._program_changed)
        self.autosave_timer = QTimer(self)
        self.autosave_timer.timeout.connect(self._autosave)
        self.autosave_timer.start(120000)
        self._update_history_ui()
        import upgrade_ui
        upgrade_ui.install(self)
        QTimer.singleShot(350, self._recover_autosave)
        if _APPLIED:
            self.log_msg(f"Update auf Version {_APPLIED} wurde eingespielt.")
        if self.settings.get("opcua_autostart"):
            self.toggle_opc()
        if len(sys.argv) > 1 and sys.argv[1].lower().endswith(".xrsim") and os.path.exists(sys.argv[1]):
            QTimer.singleShot(300, lambda: self.open_project(sys.argv[1]))
        if self.settings.get("auto_update", True):
            QTimer.singleShot(2500, lambda: self.check_updates(silent=True))

    def _program_changed(self):
        if self._restoring:
            return
        self.sim.src = self.editor.toPlainText()
        self.mark_changed()

    @property
    def dirty(self):
        return self.history.current != self._saved_snapshot

    def mark_changed(self):
        if self._restoring or self._change_depth or not hasattr(self, 'history'):
            return
        self.history.snapshot()
        self._update_history_ui()

    def _update_history_ui(self):
        self.setWindowTitle(f"{B['product']} {VERSION} - {B['company']}" + (' *' if self.dirty else ''))
        self.ribbon.update_history()

    def _restore_history(self, redo=False):
        self._restoring = True
        try:
            if (self.history.redo() if redo else self.history.undo()):
                self.jog = None
                self.viewer.selected, self.viewer.selection = None, []
                self.editor.setPlainText(self.sim.src)
                self.sync_from_sim()
                self.opc_clients_load()
        finally:
            self._restoring = False
            self._update_history_ui()

    def undo(self):
        self._restore_history()

    def redo(self):
        self._restore_history(True)

    def _clean_history(self):
        self.history = History(self.sim)
        self._saved_snapshot = self.history.current
        self._update_history_ui()

    def _autosave(self):
        if self.dirty and self.history.current:
            try:
                self.autosave.write(self.history.current, self.project_path)
            except OSError as err:
                self.log_msg(f'Automatische Sicherung fehlgeschlagen: {err}')

    def _recover_autosave(self):
        candidates = self.autosave.candidates()
        if not candidates:
            return
        path, payload = candidates[0]
        if QMessageBox.question(self, 'Automatische Sicherung',
                'Eine neuere automatische Sicherung wurde gefunden. Wiederherstellen?',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes) != QMessageBox.StandardButton.Yes:
            return
        self._restoring = True
        try:
            self.sim.reset_world()
            self.sim.from_dict(payload['project'])
            self.project_path = payload.get('project_path')
            self.viewer.selected, self.viewer.selection = None, []
            self.editor.setPlainText(self.sim.src)
            self.sync_from_sim()
            self.opc_clients_load()
            self.history = History(self.sim)
            self._saved_snapshot = None
        except Exception as err:
            QMessageBox.warning(self, 'Wiederherstellung', f'Sicherung konnte nicht geladen werden: {err}')
        finally:
            self._restoring = False
            self._update_history_ui()

    def _confirm_discard(self):
        if not self.dirty:
            return True
        box = QMessageBox(self)
        box.setWindowTitle('Ungespeicherte Änderungen')
        box.setText('Möchten Sie die Änderungen am Projekt speichern?')
        save = box.addButton('Speichern', QMessageBox.ButtonRole.AcceptRole)
        discard = box.addButton('Verwerfen', QMessageBox.ButtonRole.DestructiveRole)
        cancel = box.addButton('Abbrechen', QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(save)
        box.setEscapeButton(cancel)
        box.exec()
        if box.clickedButton() is save:
            return bool(self.save_project())
        return box.clickedButton() is discard

    # ---------------------------------------------------------------- Menue / Toolbar
    def _act(self, menu, text, fn, key=None):
        a = QAction(text, self)
        a.triggered.connect(lambda: fn())
        if key:
            a.setShortcut(key)
        menu.addAction(a)
        return a

    def _build_menu(self):
        mb = self.menuBar()
        m = mb.addMenu("&Datei")
        self._act(m, "Neues Projekt", self.new_project, "Ctrl+N")
        self._act(m, "Projekt öffnen …", self.open_project, "Ctrl+O")
        self._act(m, "Projekt speichern", self.save_project, "Ctrl+S")
        self._act(m, "Altes Projekt importieren (.vcmx / .vcm) …", self.import_vcmx, "Ctrl+I")
        self._act(m, "Projekt speichern unter …", lambda: self.save_project(True))
        m.addSeparator()
        self._act(m, "Programm importieren (.xrl/.src) …", self.import_program)
        self._act(m, "Programm exportieren (.xrl/.src) …", self.export_program)
        self._act(m, "Konfiguration exportieren (Werkzeug/Basis/Punkte) …", self.export_config)
        self._act(m, "Konfiguration importieren …", self.import_config)
        m.addSeparator()
        self._act(m, "CAD-Modell importieren (STEP/IGES/STL/OBJ/PLY/GLB/3MF) …", self.import_cad)
        self._act(m, "2D-Hallenlayout importieren (DXF) …", self.import_dxf)
        self._act(m, "Szene als 3D-Datei exportieren (GLB/OBJ/STL) …", self.export_scene3d)
        self._act(m, "3D-Präsentation exportieren (HTML, im Browser drehbar) …", self.export_html)
        self._act(m, "Screenshot speichern …", self.save_screenshot)
        self._act(m, "Video aufnehmen/stoppen (MP4 oder GIF)", self.toggle_record, "Ctrl+R")
        m.addSeparator()
        self._act(m, "Beenden", self.close, "Ctrl+Q")
        v = mb.addMenu("&Ansicht")
        self.view_menu = v
        for n, k in (("Isometrisch", "iso"), ("Vorne", "front"), ("Seite", "side"), ("Oben", "top")):
            self._act(v, n, lambda k=k: self.viewer.view(k))
        v.addSeparator()
        for txt, attr in (("Helle Hallenansicht", "light_mode"), ("Schatten", "shadows"),
                          ("TCP-Spur", "show_trail"), ("Koordinatensysteme", "show_frames"),
                          ("Erreichbarkeits-Wolke", "show_reach"), ("Swept Volume", "show_swept")):
            a = QAction(txt, self, checkable=True)
            a.setChecked(getattr(self.viewer, attr))
            a.toggled.connect(lambda c, at=attr: (setattr(self.viewer, at, c), self.viewer.update()))
            v.addAction(a)
        pm = mb.addMenu("&Prozesse")
        self._act(pm, "Bahnprozess (Schweißen, Kleben, Dichten) …", lambda: self.process_dialog("bahn"))
        self._act(pm, "Punktprozess (Punktschweißen, Inspektion) …", lambda: self.process_dialog("punkt"))
        self._act(pm, "Flächenprozess (Lackieren, Polieren, Entgraten) …", lambda: self.process_dialog("flaeche"))
        pm.addSeparator()
        self._act(pm, "Prozessvorschau ausblenden", lambda: (setattr(self.viewer, "proc_preview", None), self.viewer.update()))
        h = mb.addMenu("&Hilfe")
        self._act(h, "Nach Updates suchen …", lambda: self.check_updates(False))
        self._act(h, "Auf vorherige Version zurücksetzen …", self.do_rollback)
        self._act(h, "Über Ximaj RoboSim", self.about)

    def _build_toolbar(self):
        tb = QToolBar("Simulation")
        tb.setObjectName("simbar")
        tb.setMovable(False)
        self.addToolBar(tb)
        brand = QLabel(f" {B['product'].upper()} ")
        brand.setObjectName("simbrand")
        tb.addWidget(brand)
        def btn(text, fn, name=None, tip=None):
            b = QPushButton(text)
            if name:
                b.setObjectName(name)
            if tip:
                b.setToolTip(tip)
            b.clicked.connect(lambda: fn())
            tb.addWidget(b)
            return b
        btn("▶ Start", self.run_prog, "primary", "Programm starten / fortsetzen (F5)")
        btn("⏯ Schritt", self.step_prog, None, "Einzelschritt (F10)")
        btn("⏸ Pause", lambda: self.sim.pause_all())
        btn("■ Stop 0", lambda: self.sim.stop_all(), "danger", "STOP 0 – alle Roboter sofort anhalten (maximale Verzögerung)")
        btn("↺ Reset", self.reset_all)
        tb.addSeparator()
        tb.addWidget(QLabel(" Override "))
        self.ovr = QSlider(Qt.Orientation.Horizontal)
        self.ovr.setRange(1, 100)
        self.ovr.setValue(100)
        self.ovr.setMaximumWidth(140)
        self.ovr_l = QLabel("100 %")
        self.ovr.valueChanged.connect(lambda v: (setattr(self.sim, "override", v / 100.0), self.ovr_l.setText(f"{v} %")))
        tb.addWidget(self.ovr)
        tb.addWidget(self.ovr_l)
        tb.addWidget(QLabel("   Simulationszeit "))
        self.spd = QComboBox()
        for t in ("0.25x", "0.5x", "1x", "2x", "5x", "10x", "20x"):
            self.spd.addItem(t)
        self.spd.setCurrentText("1x")
        self.spd.currentTextChanged.connect(lambda t: setattr(self.sim, "speed_factor", float(t[:-1])))
        tb.addWidget(self.spd)
        self.col_stop = QCheckBox(" Stop bei Kollision")
        self.col_stop.setChecked(True)
        self.col_stop.toggled.connect(lambda c: setattr(self.sim, "stop_on_collision", c))
        tb.addSeparator()
        tb.addWidget(self.col_stop)
        self.state_l = QLabel("")
        tb.addSeparator()
        tb.addWidget(self.state_l)
        tb.addSeparator()
        self.opc_ind = QPushButton("OPC UA: aus")
        self.opc_ind.setFlat(True)
        self.opc_ind.setToolTip("OPC-UA-Server und -Clients (Klick öffnet die Einstellungen)")
        self.opc_ind.clicked.connect(lambda: self.ribbon.focus_bottom("Konnektivität"))
        tb.addWidget(self.opc_ind)
        tb.addSeparator()
        self.cop_in = QLineEdit()
        self.cop_in.setPlaceholderText("✦ Copilot: z. B. „füge ein Förderband 3 m bei x 1500 y -800 hinzu“")
        self.cop_in.setMinimumWidth(380)

        self.cop_in.returnPressed.connect(self.copilot_run)
        tb.addWidget(self.cop_in)
        for k, fn in (("F5", self.run_prog), ("F10", self.step_prog)):
            a = QAction(self)
            a.setShortcut(k)
            a.triggered.connect(lambda _, f=fn: f())
            self.addAction(a)

    # ---------------------------------------------------------------- Docks
    def _dock(self, title, widget, area):
        d = QDockWidget(title, self)
        d.setObjectName("dock_" + title)
        sa = QScrollArea()                      # Inhalt scrollbar -> Leiste frei schmal/breit ziehbar
        sa.setWidgetResizable(True)
        sa.setFrameShape(QScrollArea.Shape.NoFrame)
        sa.setMinimumSize(0, 0)
        sa.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        if isinstance(widget, QTabWidget):
            widget.setUsesScrollButtons(True)
            widget.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            widget.setAutoFillBackground(True)
        widget.setMinimumWidth(0)
        sa.setWidget(widget)
        d.setWidget(sa)
        d.setMinimumWidth(100)
        d.setMinimumHeight(80)
        d.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetMovable | QDockWidget.DockWidgetFeature.DockWidgetFloatable
                      | QDockWidget.DockWidgetFeature.DockWidgetClosable)
        self.addDockWidget(area, d)
        return d

    def _build_docks(self):
        L, R, Bo = Qt.DockWidgetArea.LeftDockWidgetArea, Qt.DockWidgetArea.RightDockWidgetArea, Qt.DockWidgetArea.BottomDockWidgetArea
        left = QTabWidget()
        self.left_tabs = left
        left.addTab(self._catalog_tab(), "Katalog")
        left.addTab(self._scene_tab(), "Szene")
        left.addTab(self._robot_tab(), "Roboter")
        left.addTab(self._safety_tab(), "Sicherheit")
        self.modeling_panel = modeling.panel(self)
        left.addTab(self.modeling_panel, "Modellieren")
        self.dock_l = self._dock("Aufbau", left, L)
        right = QTabWidget()
        right.addTab(self._jog_tab(), "Verfahren")
        right.addTab(self._io_tab(), "E/A")
        self.dock_r = self._dock("Bedienung", right, R)
        bottom = QTabWidget()
        bottom.addTab(self._statements_tab(), "Statements")
        bottom.addTab(self._editor_tab(), "Programm (XRL)")
        bottom.addTab(self._log_tab(), "Meldungen")
        bottom.addTab(self._points_tab(), "Punkte")
        bottom.addTab(self._analysis_tab(), "Analyse")
        bottom.addTab(self._script_tab(), "Python-Skript")
        bottom.addTab(self._connect_tab(), "Konnektivität (OPC UA)")
        bottom.addTab(self._update_tab(), "Update / Info")
        # Jede Seite kann unabhängig scrollen; breite inaktive Seiten vergrößern die aktive Seite nicht.
        pages = [(bottom.widget(i), bottom.tabText(i)) for i in range(bottom.count())]
        for _ in pages:
            bottom.removeTab(0)
        for page, title in pages:
            area = QScrollArea()
            area.setWidgetResizable(True)
            area.setFrameShape(QScrollArea.Shape.NoFrame)
            area.setWidget(page)
            bottom.addTab(area, title)
        self.bottom = bottom
        self.dock_b = self._dock("Werkzeuge", bottom, Bo)
        QTimer.singleShot(0, lambda: self.resizeDocks([self.dock_l, self.dock_r], [340, 320], Qt.Orientation.Horizontal))
        self.resizeDocks([self.dock_b], [300], Qt.Orientation.Vertical)
        self.view_menu.addSeparator()
        for d in (self.dock_l, self.dock_r, self.dock_b):
            self.view_menu.addAction(d.toggleViewAction())
        self._act(self.view_menu, "Fensteranordnung zurücksetzen", self.reset_layout)
        st = self.settings.get("window_state")
        if st:
            from PyQt6.QtCore import QByteArray
            QTimer.singleShot(50, lambda: self.restoreState(QByteArray.fromHex(st.encode())))

    def reset_layout(self):
        for d, a in ((self.dock_l, Qt.DockWidgetArea.LeftDockWidgetArea), (self.dock_r, Qt.DockWidgetArea.RightDockWidgetArea),
                     (self.dock_b, Qt.DockWidgetArea.BottomDockWidgetArea)):
            d.setFloating(False)
            self.addDockWidget(a, d)
            d.show()
        self.resizeDocks([self.dock_l, self.dock_r], [340, 320], Qt.Orientation.Horizontal)
        self.resizeDocks([self.dock_b], [300], Qt.Orientation.Vertical)

    # ----- Katalog
    def _catalog_tab(self):
        from PyQt6.QtWidgets import QTreeWidget, QTreeWidgetItem
        w = QWidget()
        l = QVBoxLayout(w)
        self.cat_search = QLineEdit()
        self.cat_search.setPlaceholderText("Katalog durchsuchen …")
        self.cat_search.textChanged.connect(self.fill_catalog)
        l.addWidget(self.cat_search)
        self.cat_tree = QTreeWidget()
        self.cat_tree.setHeaderHidden(True)
        self.cat_tree.itemSelectionChanged.connect(self.cat_selected)
        self.cat_tree.itemDoubleClicked.connect(lambda *_: self.cat_insert())
        l.addWidget(self.cat_tree, 1)
        self.cat_desc = QLabel("")
        self.cat_desc.setWordWrap(True)
        self.cat_desc.setObjectName("muted")
        l.addWidget(self.cat_desc)
        b = QPushButton("In Szene übernehmen")
        b.setObjectName("primary")
        b.clicked.connect(self.cat_insert)
        l.addWidget(b)
        self.cat_add_robot = self._btn("Als weiteren Roboter einsetzen", self.cat_add_as_robot)
        l.addWidget(self.cat_add_robot)
        l.addWidget(row(self._btn("Eigene Teile-Ordner öffnen", self.open_user_catalog),
                        self._btn("Katalog neu laden", self.reload_catalog)))
        self._QTreeWidgetItem = QTreeWidgetItem
        self.fill_catalog()
        return w

    def fill_catalog(self, *_):
        q = self.cat_search.text().lower().strip()
        self.cat_tree.clear()
        groups = {}
        for i, e in enumerate(catalog.CATALOG):
            if q and q not in (e["name"] + " " + e["desc"] + " " + e["cat"]).lower():
                continue
            g = groups.get(e["cat"])
            if g is None:
                g = self._QTreeWidgetItem([e["cat"]])
                groups[e["cat"]] = g
                self.cat_tree.addTopLevelItem(g)
            it = self._QTreeWidgetItem([e["name"]])
            it.setData(0, Qt.ItemDataRole.UserRole, i)
            g.addChild(it)
        for g in groups.values():
            g.setExpanded(bool(q) or g.text(0) in ("Beispielzellen", "Werkzeuge"))

    def cat_entry(self):
        it = self.cat_tree.currentItem()
        if it is None:
            return None
        i = it.data(0, Qt.ItemDataRole.UserRole)
        return catalog.CATALOG[i] if i is not None else None

    def cat_add_as_robot(self):
        e = self.cat_entry()
        if e and e["kind"] == "robot":
            self.add_robot(e["data"])

    def cat_selected(self):
        e = self.cat_entry()
        self.cat_add_robot.setVisible(bool(e and e["kind"] == "robot"))
        self.cat_desc.setText(f"<b>{e['name']}</b><br>{e['desc']}" if e else "")

    @tracked
    def cat_insert(self):
        e = self.cat_entry()
        if not e or self.sim.state in ("running", "wait", "stopping"):
            return
        if e["kind"] == "cell" and QMessageBox.question(self, "Beispielzelle",
                "Aktuelle Szene und Programm durch die Beispielzelle ersetzen?") != QMessageBox.StandardButton.Yes:
            return
        catalog.apply(self.sim, e, (self.viewer.center[0], self.viewer.center[1], 0.0))
        self.sync_from_sim()
        if e["kind"] == "cell":
            self.editor.setPlainText(self.sim.src)
        self.log_msg(f"Katalog: {e['name']} übernommen")

    def open_user_catalog(self):
        d = catalog.user_dirs()[0]
        os.makedirs(d, exist_ok=True)
        os.startfile(d)

    def reload_catalog(self):
        import importlib
        importlib.reload(catalog)
        n = catalog.load_user_catalog()
        self.fill_catalog()
        self.log_msg(f"Katalog neu geladen ({n} eigene Einträge)")

    def sync_from_sim(self):
        """GUI-Felder nach Aenderungen an sim (Katalog, Import, Projekt) aktualisieren"""
        self.model_c.blockSignals(True)
        self.model_c.clear()
        self.model_c.addItems(list(MODELS))
        self.model_c.setCurrentText(self.sim.model_key)
        self.model_c.blockSignals(False)
        for spins, vals in ((self.root_s, self.sim.root_pose), (self.base_s, self.sim.base), (self.tool_s, self.sim.tool.tcp)):
            for s, v in zip(spins, vals):
                s.blockSignals(True)
                s.setValue(float(v))
                s.blockSignals(False)
        for s, v in ((self.tool_out, self.sim.tool.grip_out), (self.tool_rng, self.sim.tool.grip_range),
                     (self.tool_rad, self.sim.tool.radius)):
            s.blockSignals(True)
            s.setValue(float(v))
            s.blockSignals(False)
        self.update_model_info()
        self.refresh_scene_list()
        self.fill_zones()
        self.fill_points()
        self.fill_robot_list()
        self.fill_track()
        self.fill_statements()
        self.viewer.update()

    # ----- Szene
    def _scene_tab(self):
        w = QWidget()
        l = QVBoxLayout(w)
        self.scene_search = QLineEdit()
        self.scene_search.setPlaceholderText('Szene nach Name oder Art filtern …')
        self.scene_search.setAccessibleName('Szenensuche')
        self.scene_search.textChanged.connect(self.filter_scene)
        l.addWidget(self.scene_search)
        self.obj_list = QListWidget()
        self.obj_list.currentRowChanged.connect(self.on_select_row)
        l.addWidget(self.obj_list, 1)
        b = QPushButton("＋ Objekt hinzufügen")
        mm = QMenu(b)
        for txt, kind in (("Quader", "box"), ("Zylinder", "cylinder"), ("Förderband", "conveyor"),
                          ("Lichtschranke / Sensor", "sensor"), ("Teile-Spawner", "spawner"), ("Senke (Teile-Abnahme)", "sink"),
                          ("Werkstück (greifbar)", "workpiece"), ("Zone (Markierung)", "zone")):
            mm.addAction(txt, lambda k=kind: self.add_obj(k))
        b.setMenu(mm)
        l.addWidget(row(b, self._btn("Löschen", self.del_obj), self._btn("Duplizieren", self.dup_obj)))
        g = QGroupBox("Eigenschaften")
        f = QFormLayout(g)
        self.p_name = QLineEdit()
        self.p_name.editingFinished.connect(self.apply_props)
        f.addRow("Name", self.p_name)
        self.p_pos = [spin(-20000, 20000, 0, 1, 10, cb=lambda _: self.apply_props()) for _ in range(3)]
        self.p_rot = [spin(-360, 360, 0, 1, 5, cb=lambda _: self.apply_props()) for _ in range(3)]
        self.p_size = [spin(1, 20000, 100, 1, 10, cb=lambda _: self.apply_props()) for _ in range(3)]
        f.addRow("Position X Y Z", row(*self.p_pos))
        f.addRow("Drehung A B C", row(*self.p_rot))
        f.addRow("Größe", row(*self.p_size))
        self.p_color = QPushButton("Farbe …")
        self.p_color.clicked.connect(self.pick_color)
        f.addRow("Farbe", self.p_color)
        self.p_style_label = QLabel("Darstellung")
        self.p_style = QComboBox()
        self.p_style.currentIndexChanged.connect(self.apply_style)
        f.addRow(self.p_style_label, self.p_style)
        self.p_frame_color = self._btn("Rahmenfarbe …", lambda: self.pick_conveyor_color("frame_color"))
        self.p_belt_color = self._btn("Gurtfarbe …", lambda: self.pick_conveyor_color("belt_color"))
        f.addRow(self.p_frame_color)
        f.addRow(self.p_belt_color)
        self.p_feet_label = QLabel("Stützen")
        self.p_feet = QSpinBox()
        self.p_feet.setRange(0, 20)
        self.p_feet.valueChanged.connect(self.apply_feet)
        f.addRow(self.p_feet_label, self.p_feet)
        for widget in (self.p_style_label, self.p_style, self.p_frame_color,
                       self.p_belt_color, self.p_feet_label, self.p_feet):
            widget.hide()
        self.p_obst = QCheckBox("Hindernis (Kollisionsprüfung)")
        self.p_grasp = QCheckBox("Greifbar")
        self.p_obst.toggled.connect(lambda _: self.apply_props())
        self.p_grasp.toggled.connect(lambda _: self.apply_props())
        f.addRow(self.p_obst)
        f.addRow(self.p_grasp)
        self.p_io = spin(0, 1024, 0, 0, 1, cb=lambda _: self.apply_props())
        self.p_speed = spin(0, 5000, 200, 0, 10, " mm/s", cb=lambda _: self.apply_props())
        self.p_int = spin(0.1, 600, 4, 1, 0.5, " s", cb=lambda _: self.apply_props())
        f.addRow("E/A-Nr. (Band: Ausgang, Sensor: Eingang)", self.p_io)
        f.addRow("Bandgeschw.", self.p_speed)
        f.addRow("Spawn-Intervall", self.p_int)
        self.p_simpl = self._btn("CAD-Netz vereinfachen …", self.simplify_selected)
        f.addRow(self.p_simpl)
        l.addWidget(g)
        self._loading_props = False
        return w

    def _btn(self, text, fn):
        b = QPushButton(text)
        b.clicked.connect(lambda: fn())
        return b

    def refresh_scene_list(self):
        cur = self.obj_list.currentRow()
        self.obj_list.blockSignals(True)
        self.obj_list.clear()
        for o in self.sim.scene:
            self.obj_list.addItem(f"{o.name}   [{o.kind}]")
        self.obj_list.blockSignals(False)
        if 0 <= cur < self.obj_list.count():
            self.obj_list.setCurrentRow(cur)
        self.filter_scene()
        self.viewer.update()

    def filter_scene(self):
        text = self.scene_search.text().casefold()
        for i in range(self.obj_list.count()):
            item = self.obj_list.item(i)
            item.setHidden(text not in item.text().casefold())

    def sel(self):
        r = self.obj_list.currentRow()
        return self.sim.scene[r] if 0 <= r < len(self.sim.scene) else None

    def on_select_row(self, r):
        o = self.sel()
        self.viewer.selected = o
        has_styles = o is not None and o.kind in part_geom.STYLES
        conveyor = o is not None and o.kind in ("conveyor", "conveyor_arc")
        self.p_style_label.setVisible(has_styles)
        self.p_style.setVisible(has_styles)
        for widget in (self.p_frame_color, self.p_belt_color, self.p_feet_label, self.p_feet):
            widget.setVisible(conveyor)
        if o is None:
            return
        self._loading_props = True
        self.p_style.clear()
        for style, text in part_geom.STYLES.get(o.kind, []):
            self.p_style.addItem(text, style)
        self.p_style.setCurrentIndex(max(0, self.p_style.findData(getattr(o, "style", ""))))
        try:
            self.p_feet.setValue(int(o.feet or 0))
        except (TypeError, ValueError):
            self.p_feet.setValue(2)
        self.p_name.setText(o.name)
        for i in range(3):
            self.p_pos[i].setValue(o.pos[i])
            self.p_rot[i].setValue(o.rot[i])
            self.p_size[i].setValue(o.size[i])
        self.p_obst.setChecked(o.obstacle)
        self.p_grasp.setChecked(o.graspable)
        self.p_io.setValue(o.io if o.kind != "spawner" else o.io)
        self.p_speed.setValue(o.speed)
        self.p_int.setValue(o.interval)
        self._loading_props = False
        self.viewer.update()

    @tracked
    def apply_style(self):
        o = self.sel()
        if o is None or self._loading_props or o.kind not in part_geom.STYLES:
            return
        style = self.p_style.currentData()
        if style is not None:
            o.style = style
            self.viewer.update()

    @tracked
    def apply_feet(self):
        o = self.sel()
        if o is None or self._loading_props or o.kind not in ("conveyor", "conveyor_arc"):
            return
        o.feet = self.p_feet.value()
        self.viewer.update()

    @tracked
    def pick_conveyor_color(self, field):
        o = self.sel()
        if (o is None or self._loading_props or o.kind not in ("conveyor", "conveyor_arc")
                or field not in ("frame_color", "belt_color")):
            return
        title = "Rahmenfarbe" if field == "frame_color" else "Gurtfarbe"
        color = QColorDialog.getColor(QColor(getattr(o, field)), self, title)
        if color.isValid():
            setattr(o, field, color.name())
            self.viewer.update()

    @tracked
    def apply_props(self):
        o = self.sel()
        if o is None or self._loading_props:
            return
        o.name = self.p_name.text() or o.name
        o.pos = [s.value() for s in self.p_pos]
        o.rot = [s.value() for s in self.p_rot]
        o.size = [s.value() for s in self.p_size]
        o.obstacle = self.p_obst.isChecked()
        o.graspable = self.p_grasp.isChecked()
        o.io = int(self.p_io.value())
        o.speed = self.p_speed.value()
        o.interval = self.p_int.value()
        r = self.obj_list.currentRow()
        it = self.obj_list.item(r)
        if it:
            it.setText(f"{o.name}   [{o.kind}]")
        self.viewer.update()

    @tracked
    def pick_color(self):
        o = self.sel()
        if o:
            c = QColorDialog.getColor(QColor(o.color), self)
            if c.isValid():
                o.color = c.name()
                self.viewer.update()

    @tracked
    def add_obj(self, kind):
        d = {"box": ((300, 300, 300), "#8a9bb8", True, False), "cylinder": ((200, 200, 400), "#8a9bb8", True, False),
             "conveyor": ((1500, 400, 400), "#475569", False, False), "sensor": ((40, 400, 150), "#22d3c5", False, False),
             "spawner": ((100, 100, 100), "#f5b83d", False, False), "sink": ((400, 400, 300), "#16a34a", False, False), "workpiece": ((60, 40, 40), "#f5b83d", False, True),
             "zone": ((400, 400, 400), "#a78bfa", False, False)}[kind]
        n = sum(1 for o in self.sim.scene if o.kind == kind) + 1
        o = SceneObj(f"{kind}{n}", kind, (700, 0, 0), (0, 0, 0), d[0], d[1], d[2], d[3])
        if kind == "sensor":
            o.io = 1
        self.sim.scene.append(o)
        self.refresh_scene_list()
        self.obj_list.setCurrentRow(len(self.sim.scene) - 1)

    @tracked
    def del_obj(self):
        o = self.sel()
        if o:
            self.sim.scene.remove(o)
            self.viewer.selected = None
            self.refresh_scene_list()

    @tracked
    def dup_obj(self):
        o = self.sel()
        if o:
            n = SceneObj.from_dict(o.to_dict())
            n.name += "_k"
            n.pos[0] += 100
            self.sim.scene.append(n)
            self.refresh_scene_list()

    def on_pick(self, o):
        if o is not None and o in self.sim.scene:
            self.obj_list.setCurrentRow(self.sim.scene.index(o))
        self.viewer.update()

    # ----- Roboter
    def _robot_tab(self):
        w = QWidget()
        l = QVBoxLayout(w)
        g0 = QGroupBox("Roboter in der Zelle")
        v0 = QVBoxLayout(g0)
        self.rob_list = QListWidget()
        self.rob_list.setMinimumHeight(120)
        self.rob_list.setMaximumHeight(170)
        self.rob_list.currentRowChanged.connect(self.switch_robot)
        v0.addWidget(self.rob_list)
        self.rob_name = QLineEdit()
        self.rob_name.setPlaceholderText("Name des Roboters")
        self.rob_name.editingFinished.connect(self.rename_robot)
        v0.addWidget(self.rob_name)
        v0.addWidget(row(self._btn("＋ Roboter hinzufügen", lambda: self.add_robot()),
                         self._btn("Entfernen", self.remove_robot)))
        l.addWidget(g0)
        g = QGroupBox("Robotermodell")
        f = QFormLayout(g)
        self.model_c = QComboBox()
        self.model_c.addItems(list(MODELS))
        self.model_c.setCurrentText(self.sim.model_key)
        self.model_c.currentTextChanged.connect(self.change_model)
        f.addRow("Modell", self.model_c)
        f.addRow("", self._btn("Roboter-Editor … (eigene Roboter)", self.open_robot_editor))
        self.model_info = QLabel("")
        self.model_info.setObjectName("muted")
        self.model_info.setWordWrap(True)
        f.addRow(self.model_info)
        self.root_s = [spin(-20000, 20000, 0, 1, 10, cb=lambda _: self.apply_root()) for _ in range(6)]
        f.addRow("Roboter-Fuß X Y Z", row(*self.root_s[:3]))
        f.addRow("Roboter-Fuß A B C", row(*self.root_s[3:]))
        self.base_s = [spin(-20000, 20000, 0, 1, 10, cb=lambda _: self.apply_base()) for _ in range(6)]
        f.addRow(QLabel("BASE bezieht sich auf den Roboterfuß"))
        f.addRow("BASE X Y Z", row(*self.base_s[:3]))
        f.addRow("BASE A B C", row(*self.base_s[3:]))
        l.addWidget(g)
        g2 = QGroupBox("Werkzeug (TCP / Greifer)")
        f2 = QFormLayout(g2)
        self.tool_s = [spin(-2000, 2000, v, 1, 5, cb=lambda _: self.apply_tool()) for v in self.sim.tool.tcp]
        f2.addRow("TCP X Y Z", row(*self.tool_s[:3]))
        f2.addRow("TCP A B C", row(*self.tool_s[3:]))
        self.tool_out = spin(0, 1024, self.sim.tool.grip_out, 0, 1, cb=lambda _: self.apply_tool())
        self.tool_rng = spin(1, 1000, self.sim.tool.grip_range, 0, 5, " mm", cb=lambda _: self.apply_tool())
        self.tool_rad = spin(1, 300, self.sim.tool.radius, 0, 5, " mm", cb=lambda _: self.apply_tool())
        f2.addRow("Greifer-Ausgang $OUT[n]", self.tool_out)
        f2.addRow("Greifreichweite", self.tool_rng)
        f2.addRow("Werkzeugradius", self.tool_rad)
        self.grip_status = QLabel()
        self.grip_status.setObjectName("gripperStatus")
        self.grip_status.setWordWrap(True)
        self.grip_status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        f2.addRow("Greiferstatus", self.grip_status)
        l.addWidget(g2)
        g3 = QGroupBox("Linearachse (E1)")
        f3 = QFormLayout(g3)
        self.trk_on = QCheckBox("Roboter fährt auf Linearachse (entlang X des Roboterfußes)")
        self.trk_min = spin(-50000, 50000, 0, 0, 100, " mm", cb=lambda _: self.apply_track())
        self.trk_max = spin(-50000, 50000, 4000, 0, 100, " mm", cb=lambda _: self.apply_track())
        self.trk_v = spin(10, 10000, 1500, 0, 50, " mm/s", cb=lambda _: self.apply_track())
        self.trk_on.toggled.connect(lambda _: self.apply_track())
        f3.addRow(self.trk_on)
        f3.addRow("E1 min / max", row(self.trk_min, self.trk_max))
        f3.addRow("Geschwindigkeit", self.trk_v)
        l.addWidget(g3)
        l.addStretch(1)
        self.update_model_info()
        return w

    # --- Mehrere Roboter
    def fill_robot_list(self):
        self.rob_list.blockSignals(True)
        self.rob_list.clear()
        for i, r in enumerate(self.sim.robots):
            mark = "★ " if i == self.sim.active_idx else "   "
            self.rob_list.addItem(f"{mark}{r.name}   ·   {r.model.name}" + ("  ·  Linearachse" if r.track else ""))
        self.rob_list.setCurrentRow(self.sim.active_idx)
        self.rob_list.blockSignals(False)
        self.rob_name.setText(self.sim.active.name)

    @tracked
    def switch_robot(self, idx):
        if idx < 0 or idx == self.sim.active_idx:
            return
        self.sim.active.src = self.editor.toPlainText()
        self.sim.set_active(idx)
        self.editor.setPlainText(self.sim.active.src)
        self.sync_from_sim()
        self.log_msg(f"Aktiver Roboter: {self.sim.active.name}")

    @tracked
    def add_robot(self, model_key=None):
        self.sim.active.src = self.editor.toPlainText()
        a = self.sim.active
        off = a.root_pose[:]
        off[1] += max(1500.0, a.model.reach * 1.6)
        r = self.sim.add_robot(model_key, off)
        self.editor.setPlainText(r.src)
        self.sync_from_sim()
        self.log_msg(f"{r.name} hinzugefügt")

    @tracked
    def remove_robot(self):
        if len(self.sim.robots) < 2:
            QMessageBox.information(self, "Roboter", "Die Zelle braucht mindestens einen Roboter.")
            return
        self.sim.remove_robot(self.sim.active_idx)
        self.editor.setPlainText(self.sim.active.src)
        self.sync_from_sim()

    @tracked
    def rename_robot(self):
        n = self.rob_name.text().strip()
        if n:
            self.sim.active.name = n
            self.fill_robot_list()

    @tracked
    def apply_track(self):
        if getattr(self, "_loading_track", False):
            return
        if self.trk_on.isChecked():
            self.sim.active.set_track(e_min=self.trk_min.value(), e_max=self.trk_max.value(), vmax=self.trk_v.value(), lift=True)
        else:
            self.sim.active.set_track(None)
        self.sync_from_sim()

    def fill_track(self):
        self._loading_track = True
        r = self.sim.active
        self.trk_on.setChecked(r.track is not None)
        if r.track is not None:
            lo, hi = r.e_limits()
            self.trk_min.setValue(lo)
            self.trk_max.setValue(hi)
            self.trk_v.setValue(r.track.get("vmax", 1500.0))
        self._loading_track = False

    def update_model_info(self):
        m = self.sim.model
        lim = "  ".join(f"A{i + 1}: {m.limits[i, 0]:.0f}…{m.limits[i, 1]:.0f}°" for i in range(6))
        self.model_info.setText(f"Reichweite {m.reach:.0f} mm · Nutzlast {m.payload} kg\n{lim}")

    @tracked
    def open_robot_editor(self):
        import robot_editor
        d = robot_editor.RobotEditor(self, self.sim.model_key)
        if not d.exec():
            return
        self.reload_catalog()
        if d.saved_key:
            self.sim.set_model(d.saved_key)
            self.log_msg(f"Roboter „{d.saved_key}“ gespeichert und übernommen")
        self.sync_from_sim()
        self.update_model_info()
        self.viewer.update()

    @tracked
    def change_model(self, k):
        self.sim.set_model(k)
        self.update_model_info()
        self.viewer.update()

    @tracked
    def apply_root(self):
        self.sim.set_root([s.value() for s in self.root_s])
        self.viewer.update()

    @tracked
    def apply_base(self):
        self.sim.base = [s.value() for s in self.base_s]
        self.viewer.update()

    @tracked
    def apply_tool(self):
        t = self.sim.tool
        t.tcp = [s.value() for s in self.tool_s]
        t.grip_out = int(self.tool_out.value())
        t.grip_range = self.tool_rng.value()
        t.radius = self.tool_rad.value()
        t.length = float(np.linalg.norm(t.tcp[:3]))
        self.viewer.update()

    # ----- Sicherheit
    def _safety_tab(self):
        w = QWidget()
        l = QVBoxLayout(w)
        l.addWidget(QLabel("Sicherheitszonen (Weltkoordinaten, mm).\nVerbotszone: Roboter darf nicht hinein. "
                           "Arbeitsraum: Roboter darf nicht hinaus.\nBei Verletzung: STOP 0 mit Anhalteweg."))
        self.sz_table = QTableWidget(0, 9)
        self.sz_table.setHorizontalHeaderLabels(["Name", "Typ", "Xmin", "Ymin", "Zmin", "Xmax", "Ymax", "Zmax", "Aktiv"])
        self.sz_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.sz_table.cellChanged.connect(self.sz_changed)
        l.addWidget(self.sz_table)
        l.addWidget(row(self._btn("＋ Verbotszone", lambda: self.add_zone("verbot")),
                        self._btn("＋ Arbeitsraum", lambda: self.add_zone("arbeitsraum")),
                        self._btn("Löschen", self.del_zone)))
        return w

    @tracked
    def add_zone(self, typ):
        n = len(self.sim.safety) + 1
        self.sim.safety.append({"name": f"Zone{n}", "type": typ, "min": [-300, -300, 0], "max": [300, 300, 1500],
                                "active": True})
        self.fill_zones()

    @tracked
    def del_zone(self):
        r = self.sz_table.currentRow()
        if 0 <= r < len(self.sim.safety):
            del self.sim.safety[r]
            self.fill_zones()

    def fill_zones(self):
        t = self.sz_table
        t.blockSignals(True)
        t.setRowCount(len(self.sim.safety))
        for i, z in enumerate(self.sim.safety):
            vals = [z["name"], z["type"]] + [str(v) for v in z["min"] + z["max"]] + ["ja" if z.get("active", True) else "nein"]
            for j, v in enumerate(vals):
                t.setItem(i, j, QTableWidgetItem(v))
        t.blockSignals(False)
        self.viewer.update()

    @tracked
    def sz_changed(self, r, c):
        try:
            z = self.sim.safety[r]
            v = self.sz_table.item(r, c).text()
            if c == 0:
                z["name"] = v
            elif c == 1:
                z["type"] = "arbeitsraum" if v.startswith("a") else "verbot"
            elif 2 <= c <= 4:
                z["min"][c - 2] = float(v)
            elif 5 <= c <= 7:
                z["max"][c - 5] = float(v)
            else:
                z["active"] = v.lower() in ("ja", "1", "true", "x")
        except Exception:
            pass
        self.viewer.update()

    # ----- Verfahren
    def _jog_tab(self):
        w = QWidget()
        l = QVBoxLayout(w)
        g = QGroupBox("Achsen (Halten zum Verfahren)")
        gl = QGridLayout(g)
        self.ax_lbl = []
        for i in range(6):
            mi, pl = QPushButton(f"A{i + 1} −"), QPushButton(f"A{i + 1} +")
            for b, s in ((mi, -1), (pl, 1)):
                b.pressed.connect(lambda i=i, s=s: setattr(self, "jog", ("j", i, s)))
                b.released.connect(lambda: setattr(self, "jog", None))
            lb = QLabel("0.0°")
            lb.setMinimumWidth(70)
            lb.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.ax_lbl.append(lb)
            gl.addWidget(mi, i, 0)
            gl.addWidget(lb, i, 1)
            gl.addWidget(pl, i, 2)
        l.addWidget(g)
        g2 = QGroupBox("Kartesisch (TCP)")
        g2l = QGridLayout(g2)
        self.cart_lbl = []
        self.jog_frame = QComboBox()
        self.jog_frame.addItems(["BASE", "TOOL"])
        g2l.addWidget(QLabel("Bezug"), 0, 0)
        g2l.addWidget(self.jog_frame, 0, 1, 1, 2)
        for i, n in enumerate("XYZABC"):
            mi, pl = QPushButton(f"{n} −"), QPushButton(f"{n} +")
            for b, s in ((mi, -1), (pl, 1)):
                b.pressed.connect(lambda i=i, s=s: setattr(self, "jog", ("c", i, s)))
                b.released.connect(lambda: setattr(self, "jog", None))
            lb = QLabel("0.0")
            lb.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.cart_lbl.append(lb)
            g2l.addWidget(mi, i + 1, 0)
            g2l.addWidget(lb, i + 1, 1)
            g2l.addWidget(pl, i + 1, 2)
        l.addWidget(g2)
        self.jog_speed = QSlider(Qt.Orientation.Horizontal)
        self.jog_speed.setRange(1, 100)
        self.jog_speed.setValue(30)
        l.addWidget(QLabel("Verfahrgeschwindigkeit"))
        l.addWidget(self.jog_speed)
        self.st_lbl = QLabel("")
        self.sing = QProgressBar()
        self.sing.setRange(0, 100)
        self.sing.setFormat("Abstand zur Singularität: %p %")
        l.addWidget(self.st_lbl)
        l.addWidget(self.sing)
        ge = QGroupBox("Linearachse")
        gel = QHBoxLayout(ge)
        em, ep = QPushButton("E1 −"), QPushButton("E1 +")
        for b_, s_ in ((em, -1), (ep, 1)):
            b_.pressed.connect(lambda s_=s_: setattr(self, "jog", ("e", 0, s_)))
            b_.released.connect(lambda: setattr(self, "jog", None))
        self.e1_lbl = QLabel("–")
        self.e1_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        gel.addWidget(em)
        gel.addWidget(self.e1_lbl)
        gel.addWidget(ep)
        l.addWidget(ge)
        l.addWidget(row(self._btn("Home", self.go_home), self._btn("Mastering (alle 0)", lambda: self.set_q(np.zeros(6)))))
        l.addWidget(self._btn("Punkt einlernen (Teach)", self.teach_point))
        l.addStretch(1)
        return w

    def set_q(self, q):
        if self.sim.state in ("running", "wait", "stopping"):
            return
        self.sim.q = np.clip(np.array(q, float), self.sim.model.limits[:, 0], self.sim.model.limits[:, 1])
        self.sim.update_sv()

    def go_home(self):
        self.set_q(HOME)

    def do_jog(self, dt):
        if not self.jog or self.sim.state in ("running", "wait", "stopping"):
            return
        kind, i, s = self.jog
        sp = self.jog_speed.value() / 100.0
        m = self.sim.model
        if kind == "e":
            r = self.sim.active
            if r.track is not None:
                lo, hi = r.e_limits()
                r.e1 = float(np.clip(r.e1 + s * r.track["vmax"] * 0.5 * sp * dt, lo, hi))
                r.update_sv()
            return
        if kind == "j":
            q = self.sim.q.copy()
            q[i] = np.clip(q[i] + s * m.vmax[i] * 0.5 * sp * dt, m.limits[i, 0], m.limits[i, 1])
            self.sim.q = q
        else:
            Tw = self.sim.tcp_world()
            if i < 3:
                d = np.zeros(3)
                d[i] = s * 250.0 * sp * dt
                if self.jog_frame.currentText() == "TOOL":
                    Tw[:3, 3] += Tw[:3, :3] @ d
                else:
                    Tw[:3, 3] += self.sim.base_world()[:3, :3] @ d
            else:
                a = np.zeros(3)
                a[i - 3] = s * np.radians(45.0) * sp * dt
                R = (rz(a[2]) @ ry(a[1]) @ rx(a[0]))[:3, :3] if self.jog_frame.currentText() == "TOOL" else None
                # A = um Z, B = um Y, C = um X (wie Pose-Konvention)
                ang = np.zeros(3)
                ang[{3: 2, 4: 1, 5: 0}[i]] = s * np.radians(45.0) * sp * dt
                Rd = (rz(ang[2]) @ ry(ang[1]) @ rx(ang[0]))[:3, :3]
                if self.jog_frame.currentText() == "TOOL":
                    Tw[:3, :3] = Tw[:3, :3] @ Rd
                else:
                    Rb = self.sim.base_world()[:3, :3]
                    Tw[:3, :3] = Rb @ Rd @ Rb.T @ Tw[:3, :3]
            Tf = inv(self.sim.root) @ Tw @ inv(self.sim.tool_mat())
            q = m.ik(Tf, self.sim.q)
            if q is not None:
                self.sim.q = q
        self.sim.update_sv()

    # ----- E/A
    def _io_tab(self):
        w = QWidget()
        l = QVBoxLayout(w)
        l.addWidget(QLabel("E/A-Mapping: Namen per Doppelklick vergeben · Haken = Signal von Hand setzen.\n"
                           "Graue Namen sind automatische Vorschläge aus Greifern, Sensoren und Förderern."))
        self.io_n = 64
        self.io_offset = 0
        self.io_bank = QComboBox()
        self.io_bank.addItems([f"Signale {n}–{min(n + 63, self.sim.io.N - 1)}"
                               for n in range(1, self.sim.io.N, self.io_n)])
        l.addWidget(self.io_bank)
        self.io_t = QTableWidget(self.io_n, 6)
        self.io_t.setHorizontalHeaderLabels(["$IN", "Name", "Wert", "$OUT", "Name", "Wert"])
        self.io_t.verticalHeader().setVisible(False)
        hh = self.io_t.horizontalHeader()
        for c, mode in enumerate((QHeaderView.ResizeMode.ResizeToContents, QHeaderView.ResizeMode.Stretch,
                                  QHeaderView.ResizeMode.ResizeToContents) * 2):
            hh.setSectionResizeMode(c, mode)
        for i in range(self.io_n):
            for c, txt in ((0, f"IN[{i + 1}]"), (3, f"OUT[{i + 1}]")):
                it = QTableWidgetItem(txt)
                it.setFlags(Qt.ItemFlag.ItemIsEnabled)
                self.io_t.setItem(i, c, it)
            for c in (1, 4):
                self.io_t.setItem(i, c, QTableWidgetItem(""))
            for c in (2, 5):
                it = QTableWidgetItem()
                it.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
                it.setCheckState(Qt.CheckState.Unchecked)
                self.io_t.setItem(i, c, it)
        self.io_t.itemChanged.connect(self.io_edited)
        l.addWidget(self.io_t)
        self._io_lock = False
        self._io_tick = 0
        self.io_bank.currentIndexChanged.connect(self.change_io_bank)
        return w

    def change_io_bank(self, index):
        self._io_lock = True
        self.io_offset = max(0, index) * self.io_n
        for i in range(self.io_n):
            number = self.io_offset + i + 1
            self.io_t.item(i, 0).setText(f"IN[{number}]")
            self.io_t.item(i, 3).setText(f"OUT[{number}]")
        self._io_tick = 0
        self.refresh_io()

    def io_edited(self, it):
        if self._io_lock:
            return
        c, r = it.column(), self.io_offset + it.row()
        if c in (1, 4):
            key = ("in" if c == 1 else "out", r + 1)
            txt = it.text().strip()
            if txt and txt != self._io_suggest().get(key):
                self.sim.io.names[key] = txt
            else:
                self.sim.io.names.pop(key, None)
            return
        v = it.checkState() == Qt.CheckState.Checked
        if c == 2:
            self.sim.io.set_in(r + 1, v)
        elif c == 5:
            self.sim.io.set_out(r + 1, v)

    def _io_suggest(self):
        """Automatische Signalnamen aus der Zelle"""
        s = {}
        for r in self.sim.robots:
            if r.tool.grip_out:
                s[("out", int(r.tool.grip_out))] = f"Greifer {r.name}"
        for o in self.sim.scene:
            if o.kind == "sensor" and o.io:
                s[("in", int(o.io))] = f"Sensor {o.name}"
            elif o.kind in ("conveyor", "conveyor_arc") and o.io:
                s.setdefault(("out", int(o.io)), f"Band {o.name}")
            elif o.kind in ("spawner", "sink") and o.io:
                s.setdefault(("out", int(o.io)), f"Freigabe {o.name}")
        return s

    def refresh_io(self):
        self._io_lock = True
        io = self.sim.io
        self._io_tick += 1
        if self._io_tick % 5 == 1:                     # Namen seltener aktualisieren
            sug = self._io_suggest()
            for i in range(self.io_n):
                for c, kind in ((1, "in"), (4, "out")):
                    it = self.io_t.item(i, c)
                    if self.io_t.currentItem() is it and self.io_t.state() == self.io_t.State.EditingState:
                        continue
                    number = self.io_offset + i + 1
                    nm = io.names.get((kind, number))
                    txt, grey = (nm, False) if nm else (sug.get((kind, number), ""), True)
                    if it.text() != txt:
                        it.setText(txt)
                    it.setForeground(QColor("#8a94a3" if grey else B["text"]))
        for i in range(self.io_n):
            for c, val in ((2, io.get_in(self.io_offset + i + 1)), (5, io.get_out(self.io_offset + i + 1))):
                st = Qt.CheckState.Checked if val else Qt.CheckState.Unchecked
                it = self.io_t.item(i, c)
                if it.checkState() != st:
                    it.setCheckState(st)
        self._io_lock = False

    # ----- Copilot
    @tracked
    def copilot_run(self):
        txt = self.cop_in.text().strip()
        if not txt:
            return
        try:
            ans = copilot.execute(self, txt)
        except Exception as e:
            ans = f"Fehler: {e}"
        self.cop_in.clear()
        self.log_msg(f"Copilot ▸ {txt}")
        for line in ans.splitlines():
            self.log_msg(f"Copilot ◂ {line}")
        self.statusBar().showMessage(f"Copilot: {ans.splitlines()[0]}", 8000)
        self.viewer.update()

    # ----- Prozesse (Bahn / Punkt / Flaeche)
    def process_dialog(self, kind):
        o = self.sel()
        if o is None or o.kind in ("sensor", "spawner", "sink", "zone", "conveyor_arc"):
            QMessageBox.information(self, "Prozess", "Bitte zuerst im Reiter 'Szene' (oder per Klick im 3D-Fenster) "
                                    "das Bauteil auswählen, das bearbeitet werden soll.")
            return
        r = self.sim.active
        titles = {"bahn": "Bahnprozess", "punkt": "Punktprozess", "flaeche": "Flächenprozess"}
        dlg = QDialog(self)
        dlg.setWindowTitle(f"{titles[kind]} – {o.name} – {r.name}")
        dlg.resize(560, 620)
        lay = QVBoxLayout(dlg)
        info = QLabel(f"Bauteil <b>{o.name}</b> · Roboter <b>{r.name}</b> · Werkzeug <b>{r.tool.name}</b> "
                      f"(TCP Z {r.tool.tcp[2]:.0f} mm)")
        info.setWordWrap(True)
        lay.addWidget(info)
        f = QFormLayout()
        lay.addLayout(f)
        P = {}

        def num(key, label, lo, hi, val, dec=1, suf=""):
            P[key] = spin(lo, hi, val, dec, 1, suf)
            f.addRow(label, P[key])
        if kind == "bahn":
            num("height_from_top", "Nahthöhe unter Oberkante", 0.2, 5000, 2, 1, " mm")
            num("offset", "Versatz nach außen", -500, 500, 0, 1, " mm")
            num("tilt", "Anstellwinkel (Neigung)", -80, 80, 45, 1, " °")
            num("travel", "Stechwinkel (in Bahnrichtung)", -45, 45, 10, 1, " °")
            num("spacing", "Punktabstand", 2, 500, 20, 1, " mm")
            num("approach", "An-/Abfahrabstand", 0, 1000, 80, 0, " mm")
            num("speed", "Prozessgeschwindigkeit", 0.001, 2, 0.15, 3, " m/s")
            num("out_nr", "Prozess-Ausgang $OUT (0 = keiner)", 0, 1024, 7, 0)
            P["reverse"] = QCheckBox("Bahnrichtung umkehren")
            f.addRow(P["reverse"])
        elif kind == "punkt":
            P["mode"] = QComboBox()
            P["mode"].addItems(["kontur", "raster"])
            f.addRow("Punktverteilung", P["mode"])
            num("spacing", "Abstand entlang Kontur", 5, 2000, 60, 0, " mm")
            num("height_from_top", "Höhe unter Oberkante (Kontur)", 0.2, 5000, 2, 1, " mm")
            num("gx", "Raster: Punkte in X", 1, 50, 3, 0)
            num("gy", "Raster: Punkte in Y", 1, 50, 3, 0)
            num("approach", "Anfahrabstand", 0, 1000, 60, 0, " mm")
            num("dwell", "Verweilzeit je Punkt", 0, 30, 0.3, 2, " s")
            num("tilt", "Neigung", -80, 80, 0, 1, " °")
            num("out_nr", "Prozess-Ausgang $OUT (Impuls, 0 = keiner)", 0, 1024, 8, 0)
        else:
            num("width", "Bahnbreite (Sprühstrahl/Werkzeug)", 1, 2000, 60, 0, " mm")
            num("overlap", "Überlappung", 0, 90, 20, 0, " %")
            num("standoff", "Abstand zur Oberfläche", 0, 1000, 150, 0, " mm")
            num("margin", "Randabstand", 0, 500, 0, 0, " mm")
            num("direction_deg", "Bahnrichtung", -180, 180, 0, 0, " °")
            num("speed", "Prozessgeschwindigkeit", 0.001, 3, 0.3, 3, " m/s")
            num("out_nr", "Prozess-Ausgang $OUT (0 = keiner)", 0, 1024, 9, 0)
        P["spin"] = QCheckBox("Drehung um die Werkzeugachse frei (Erreichbarkeit optimieren)")
        P["spin"].setChecked(True)
        if kind != "flaeche":
            f.addRow(P["spin"])
        rep = QPlainTextEdit()
        rep.setReadOnly(True)
        rep.setMaximumHeight(150)
        lay.addWidget(rep)
        P["append"] = QCheckBox("An vorhandene Statements anhängen (sonst ersetzen)")
        P["append"].setChecked(bool(r.statements))
        lay.addWidget(P["append"])
        state = {"res": None}

        def compute():
            kw = {}
            for k, wdg in P.items():
                if k in ("append", "gx", "gy"):
                    continue
                if isinstance(wdg, QDoubleSpinBox):
                    kw[k] = int(wdg.value()) if k == "out_nr" else wdg.value()
                elif isinstance(wdg, QComboBox):
                    kw[k] = wdg.currentText()
                elif k == "reverse":
                    kw[k] = wdg.isChecked()
            if kind != "flaeche":
                kw["spin_free"] = P["spin"].isChecked()
            try:
                if kind == "bahn":
                    res = proc.path_process(r, o, **kw)
                elif kind == "punkt":
                    kw["grid"] = (int(P["gx"].value()), int(P["gy"].value()))
                    res = proc.point_process(r, o, **kw)
                else:
                    res = proc.surface_process(r, o, **kw)
            except Exception as e:
                rep.setPlainText(f"Fehler: {e}")
                return None
            state["res"] = res
            self.viewer.proc_preview = res
            self.viewer.update()
            lines = [f"{k}: {v}" for k, v in res["report"].items()]
            if res["report"].get("nicht erreichbar"):
                lines.append("⚠ Nicht erreichbare Punkte: Bauteil/Roboter verschieben, Winkel ändern oder Linearachse nutzen.")
            rep.setPlainText("\n".join(lines))
            return res

        def take():
            res = state["res"] or compute()
            if not res:
                return
            r.statements = (r.statements if P["append"].isChecked() else []) + res["stmts"]
            r.mode = "statements"
            self.fill_statements(len(r.statements) - 1)
            self.bottom.setCurrentIndex(0)
            self.log_msg(f"{titles[kind]}: {len(res['stmts'])} Bausteine für {r.name} erzeugt")
            dlg.accept()
        bb = QHBoxLayout()
        b1 = QPushButton("Vorschau berechnen")
        b1.clicked.connect(compute)
        b2 = QPushButton("Als Statements übernehmen")
        b2.setObjectName("primary")
        b2.clicked.connect(take)
        b3 = QPushButton("Schließen")
        b3.clicked.connect(dlg.reject)
        for b_ in (b1, b2, b3):
            bb.addWidget(b_)
        lay.addLayout(bb)
        compute()
        dlg.exec()

    # ----- Statements (Bausteinprogrammierung)
    def _statements_tab(self):
        w = QWidget()
        l = QHBoxLayout(w)
        left = QVBoxLayout()
        self.st_mode = QCheckBox("Dieser Roboter wird mit Statements programmiert (XRL wird automatisch erzeugt)")
        self.st_mode.toggled.connect(self.st_mode_changed)
        left.addWidget(self.st_mode)
        self.st_list = QListWidget()
        self.st_list.setFont(QFont("Segoe UI", 10))
        self.st_list.itemDoubleClicked.connect(lambda *_: self.st_edit())
        left.addWidget(self.st_list, 1)
        left.addWidget(row(self._btn("Bearbeiten …", self.st_edit), self._btn("▲", lambda: self.st_move(-1)),
                           self._btn("▼", lambda: self.st_move(1)), self._btn("Löschen", self.st_delete),
                           self._btn("Position übernehmen (Teach)", self.st_teach),
                           self._btn("Anfahren", self.st_goto)))
        gen = QPushButton("XRL erzeugen und anzeigen")
        gen.setObjectName("primary")
        gen.clicked.connect(self.st_generate)
        left.addWidget(gen)
        l.addLayout(left, 3)
        pal = QGroupBox("Bausteine (an markierter Stelle einfügen)")
        gl = QGridLayout(pal)
        items = [("PTP hier", "PTP"), ("LIN hier", "LIN"), ("CIRC", "CIRC"), ("Warten (Zeit)", "WAIT_TIME"),
                 ("Warten auf Signal", "WAIT_IN"), ("Ausgang setzen", "SET_OUT"), ("Impuls", "PULSE"),
                 ("Greifer zu", "GRIP"), ("Greifer auf", "RELEASE"), ("Schleife n×", "LOOP"),
                 ("Endlosschleife", "LOOP_FOREVER"), ("Wenn Signal", "IF"), ("Sonst", "ELSE"),
                 ("Geschwindigkeit", "VEL"), ("Unterprogramm", "CALL"), ("Meldung", "MSG"),
                 ("Kommentar", "COMMENT"), ("HALT", "HALT")]
        for i, (txt, t) in enumerate(items):
            b = QPushButton(txt)
            b.clicked.connect(lambda _, t=t: self.st_add(t))
            gl.addWidget(b, i // 2, i % 2)
        l.addWidget(pal, 2)
        return w

    def st_robot(self):
        return self.sim.active

    def fill_statements(self, keep=None):
        r = self.st_robot()
        cur = self.st_list.currentRow() if keep is None else keep
        self.st_list.blockSignals(True)
        self.st_list.clear()
        ind = stm.indents(r.statements)
        for i, s in enumerate(r.statements):
            it = QListWidgetItem(f"{i + 1:>3}   " + "      " * ind[i] + stm.label(s))
            if s["type"] in ("LOOP", "LOOP_FOREVER", "LOOP_END", "IF", "ELSE", "IF_END"):
                it.setForeground(QColor(B["accent_dark"]))
            elif s["type"] == "COMMENT":
                it.setForeground(QColor("#8a94a3"))
            self.st_list.addItem(it)
        if 0 <= cur < self.st_list.count():
            self.st_list.setCurrentRow(cur)
        self.st_list.blockSignals(False)
        self.st_mode.blockSignals(True)
        self.st_mode.setChecked(r.mode == "statements")
        self.st_mode.blockSignals(False)

    @tracked
    def st_mode_changed(self, on):
        r = self.st_robot()
        if on and r.src.strip() and not r.statements:
            if QMessageBox.question(self, "Statements", "Auf Statement-Programmierung umstellen? Das bisherige "
                                    "XRL-Programm wird beim nächsten Start durch die Bausteine ersetzt.") \
                    != QMessageBox.StandardButton.Yes:
                self.st_mode.blockSignals(True)
                self.st_mode.setChecked(False)
                self.st_mode.blockSignals(False)
                return
        r.mode = "statements" if on else "xrl"

    @tracked
    def st_add(self, t):
        r = self.st_robot()
        idx = self.st_list.currentRow() + 1 if self.st_list.currentRow() >= 0 else len(r.statements)
        s = stm.new(t)
        p = [round(x, 2) for x in r.sv["POS_ACT"]]
        if t in ("PTP", "LIN"):
            s["pos"] = p
            if t == "PTP":
                s["S"], s["T"] = r.model.status_turn(r.q)
            if r.track is not None:
                s["E1"] = round(r.e1, 1)
            s["name"] = f"P{sum(1 for x in r.statements if x['type'] in ('PTP', 'LIN', 'CIRC')) + 1}"
        elif t == "CIRC":
            s["aux"] = [p[0], p[1] + 100, p[2]] + p[3:]
            s["pos"] = [p[0] + 100, p[1] + 200, p[2]] + p[3:]
        elif t in ("GRIP", "RELEASE"):
            s["nr"] = r.tool.grip_out or 1
        new = [s]
        if t in stm.OPENERS:
            new.append(stm.new(stm.OPENERS[t]))
        r.statements[idx:idx] = new
        if not r.statements or r.mode != "statements":
            r.mode = "statements"
        self.fill_statements(idx)

    @tracked
    def st_delete(self):
        r = self.st_robot()
        i = self.st_list.currentRow()
        if 0 <= i < len(r.statements):
            del r.statements[i]
            self.fill_statements(min(i, len(r.statements) - 1))

    @tracked
    def st_move(self, d):
        r = self.st_robot()
        i = self.st_list.currentRow()
        j = i + d
        if 0 <= i < len(r.statements) and 0 <= j < len(r.statements):
            r.statements[i], r.statements[j] = r.statements[j], r.statements[i]
            self.fill_statements(j)

    @tracked
    def st_teach(self):
        r = self.st_robot()
        i = self.st_list.currentRow()
        if 0 <= i < len(r.statements) and "pos" in r.statements[i]:
            s = r.statements[i]
            s["pos"] = [round(x, 2) for x in r.sv["POS_ACT"]]
            if s["type"] == "PTP":
                s["S"], s["T"] = r.model.status_turn(r.q)
            if r.track is not None:
                s["E1"] = round(r.e1, 1)
            self.fill_statements(i)
            self.log_msg(f"Baustein {i + 1}: Position übernommen")

    def st_goto(self):
        r = self.st_robot()
        i = self.st_list.currentRow()
        if not (0 <= i < len(r.statements)) or "pos" not in r.statements[i] or r.busy():
            return
        s = r.statements[i]
        if r.track is not None and s.get("E1") is not None:
            r.e1 = float(s["E1"])
        T = r.target_flange_robot(("pos", s["pos"], None, None))
        st = (s.get("S"), s.get("T")) if s.get("S") is not None and s.get("T") is not None else None
        q = r.model.ik(T, r.q, st)
        if q is None:
            q = r.model.ik(T, r.q)
        if q is None:
            self.log_msg("Position nicht erreichbar")
            return
        r.q = q
        r.update_sv()

    @tracked
    def st_generate(self):
        r = self.st_robot()
        errs = stm.validate(r.statements)
        if errs:
            QMessageBox.warning(self, "Statements", "\n".join(errs))
            return
        r.src, r.stmt_linemap = stm.generate(r.statements, _ident(r.name))
        self.editor.setPlainText(r.src)
        self.bottom.setCurrentIndex(1)

    @tracked
    def st_edit(self):
        r = self.st_robot()
        i = self.st_list.currentRow()
        if not (0 <= i < len(r.statements)):
            return
        s = r.statements[i]
        dlg = QDialog(self)
        dlg.setWindowTitle(stm.TYPES[s["type"]][0])
        f = QFormLayout(dlg)
        widgets = {}
        names = {"pos": "Position X Y Z A B C", "aux": "Hilfspunkt X Y Z A B C", "vel": "Geschwindigkeit",
                 "sec": "Zeit (s)", "kind": "Signalart", "nr": "Nummer", "value": "Wert EIN", "count": "Anzahl",
                 "cp": "Bahn (m/s)", "ptp": "Achsen (%)", "name": "Name", "text": "Text", "S": "Status S",
                 "T": "Turn T", "E1": "Linearachse E1 (mm)"}
        for k, v in s.items():
            if k == "type":
                continue
            if isinstance(v, list):
                sp = [spin(-100000, 100000, float(x), 2, 1) for x in v]
                widgets[k] = sp
                f.addRow(names.get(k, k), row(*sp))
            elif isinstance(v, bool):
                c = QCheckBox()
                c.setChecked(v)
                widgets[k] = c
                f.addRow(names.get(k, k), c)
            elif k == "kind":
                c = QComboBox()
                c.addItems(["IN", "OUT"])
                c.setCurrentText(v)
                widgets[k] = c
                f.addRow(names.get(k, k), c)
            elif isinstance(v, (int, float)) and not isinstance(v, bool):
                sp = spin(-100000, 100000, float(v), 0 if isinstance(v, int) else 3, 1)
                widgets[k] = sp
                f.addRow(names.get(k, k), sp)
            else:
                e = QLineEdit("" if v is None else str(v))
                e.setPlaceholderText("leer = automatisch")
                widgets[k] = e
                f.addRow(names.get(k, k), e)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        f.addRow(bb)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        for k, wdg in widgets.items():
            old = s[k]
            if isinstance(wdg, list):
                s[k] = [x.value() for x in wdg]
            elif isinstance(wdg, QCheckBox):
                s[k] = wdg.isChecked()
            elif isinstance(wdg, QComboBox):
                s[k] = wdg.currentText()
            elif isinstance(wdg, QDoubleSpinBox):
                s[k] = int(wdg.value()) if isinstance(old, int) else wdg.value()
            else:
                t = wdg.text().strip()
                if k in ("S", "T", "E1"):
                    try:
                        s[k] = (int(t) if k != "E1" else float(t)) if t else None
                    except ValueError:
                        s[k] = None
                else:
                    s[k] = t
        self.fill_statements(i)

    def st_highlight(self):
        r = self.st_robot()
        if r.mode != "statements" or not r.busy():
            return
        idx = r.stmt_linemap.get(r.cur_line)
        if idx is not None and idx != self.st_list.currentRow():
            self.st_list.blockSignals(True)
            self.st_list.setCurrentRow(idx)
            self.st_list.blockSignals(False)

    # ----- Editor
    def _editor_tab(self):
        w = QWidget()
        l = QVBoxLayout(w)
        self.editor = CodeEditor(self)
        f = QFont("Cascadia Mono", 10)
        f.setStyleHint(QFont.StyleHint.Monospace)
        self.editor.setFont(f)
        self.editor.setPlainText(self.sim.src)
        self.hl = XrlHighlighter(self.editor.document())
        self.editor.setTabStopDistance(28)
        l.addWidget(self.editor)
        l.addWidget(row(self._btn("Prüfen (Syntax)", self.check_syntax), self._btn("Importieren …", self.import_program),
                        self._btn("Exportieren …", self.export_program), self._btn("Beispiel laden", self.load_example)))
        return w

    def load_example(self):
        self.editor.setPlainText(DEFAULT_PROGRAM)

    def check_syntax(self):
        try:
            xrl.Parser(xrl.tokenize(self.editor.toPlainText())).program()
            self.log_msg("Syntax OK")
        except xrl.XrlError as e:
            self.log_msg(f"Syntaxfehler: {e}")
            self.goto_line(e.line)

    def goto_line(self, n):
        blk = self.editor.document().findBlockByLineNumber(max(n - 1, 0))
        c = QTextCursor(blk)
        self.editor.setTextCursor(c)

    def highlight_line(self):
        sel = []
        n = self.sim.cur_line
        if n > 0 and self.sim.state != "idle":
            blk = self.editor.document().findBlockByLineNumber(n - 1)
            e = QTextEdit.ExtraSelection()
            e.format.setBackground(QColor(B["accent_soft"]))
            e.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
            e.cursor = QTextCursor(blk)
            sel.append(e)
        self.editor.setExtraSelections(sel)

    # ----- Meldungen
    def _log_tab(self):
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        return self.log_view

    def log_msg(self, m):
        self.sim.say(m)

    # ----- Punkte
    def _points_tab(self):
        w = QWidget()
        l = QVBoxLayout(w)
        self.pt = QTableWidget(0, 8)
        self.pt.setHorizontalHeaderLabels(["Name", "X", "Y", "Z", "A", "B", "C", "S/T"])
        self.pt.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.pt.cellChanged.connect(self.pt_changed)
        l.addWidget(self.pt)
        l.addWidget(row(self._btn("Punkt einlernen", self.teach_point), self._btn("Anfahren (PTP)", self.pt_goto),
                        self._btn("Als PTP einfügen", lambda: self.pt_insert("PTP")),
                        self._btn("Als LIN einfügen", lambda: self.pt_insert("LIN")),
                        self._btn("Löschen", self.pt_del)))
        return w

    @tracked
    def teach_point(self):
        p = self.sim.sv["POS_ACT"]
        s, t = self.sim.model.status_turn(self.sim.q)
        self.sim.waypoints.append({"name": f"P{len(self.sim.waypoints) + 1}", "pos": [round(x, 2) for x in p], "S": s, "T": t})
        self.sim.waypoints[-1].update({"base_world": [float(x) for x in mat_to_pose(self.sim.base_world())],
                                       "e1": float(self.sim.e1)})
        self.fill_points()
        self.log_msg(f"Punkt P{len(self.sim.waypoints)} eingelernt")

    def fill_points(self):
        self.pt.blockSignals(True)
        self.pt.setRowCount(len(self.sim.waypoints))
        for i, w in enumerate(self.sim.waypoints):
            vals = [w["name"]] + [f"{x:.2f}" for x in w["pos"]] + [f"{w['S']}/{w['T']}"]
            for j, v in enumerate(vals):
                it = QTableWidgetItem(v)
                if j == 7:
                    it.setFlags(Qt.ItemFlag.ItemIsEnabled)
                self.pt.setItem(i, j, it)
        self.pt.blockSignals(False)

    @tracked
    def pt_changed(self, r, c):
        try:
            w = self.sim.waypoints[r]
            v = self.pt.item(r, c).text()
            if c == 0:
                w["name"] = v
            elif 1 <= c <= 6:
                w["pos"][c - 1] = float(v)
        except Exception:
            pass

    def pt_goto(self):
        r = self.pt.currentRow()
        if r < 0 or self.sim.state in ("running", "wait"):
            return
        w = self.sim.waypoints[r]
        T = self.sim.target_flange_robot(("pos", w["pos"], None, None))
        q = self.sim.model.ik(T, self.sim.q, (w["S"], w["T"]))
        if q is None:
            q = self.sim.model.ik(T, self.sim.q)
        if q is None:
            self.log_msg("Punkt nicht erreichbar")
        else:
            self.sim.q = q
            self.sim.update_sv()

    def pt_insert(self, cmd):
        r = self.pt.currentRow()
        if r < 0:
            return
        p = self.sim.waypoints[r]["pos"]
        txt = f"{cmd} {{X {p[0]:.1f}, Y {p[1]:.1f}, Z {p[2]:.1f}, A {p[3]:.1f}, B {p[4]:.1f}, C {p[5]:.1f}}}\n"
        c = self.editor.textCursor()
        c.movePosition(QTextCursor.MoveOperation.EndOfBlock)
        c.insertText("\n" + "  " + txt.rstrip("\n"))
        self.bottom.setCurrentIndex(1)

    @tracked
    def pt_del(self):
        r = self.pt.currentRow()
        if r >= 0:
            del self.sim.waypoints[r]
            self.fill_points()

    # ----- Analyse
    def _analysis_tab(self):
        w = QWidget()
        l = QHBoxLayout(w)
        g = QGroupBox("Live-Kennzahlen")
        f = QFormLayout(g)
        self.a_state, self.a_run, self.a_cyc, self.a_en, self.a_pw, self.a_stop, self.a_col = (QLabel("-") for _ in range(7))
        f.addRow("Zustand", self.a_state)
        f.addRow("Laufzeit", self.a_run)
        f.addRow("Taktzeit (letzter / Ø Zyklus)", self.a_cyc)
        f.addRow("Energie (Schätzwert)", self.a_en)
        f.addRow("Leistung (Schätzwert)", self.a_pw)
        f.addRow("Letzter Anhalteweg (STOP 0)", self.a_stop)
        f.addRow("Kollision", self.a_col)
        self.a_tp = QLabel("-")
        self.a_tp.setWordWrap(True)
        f.addRow("Durchsatz (Materialfluss)", self.a_tp)
        l.addWidget(g)
        g2 = QGroupBox("Analysewerkzeuge")
        v = QVBoxLayout(g2)
        v.addWidget(self._btn("Erreichbarkeits-Wolke berechnen (Werkzeug senkrecht)", self.calc_reach))
        v.addWidget(self._btn("Szene auf Erreichbarkeit prüfen (Objekte + Punkte)", self.check_scene_reach))
        self.sw_rec = QCheckBox("Swept Volume aufzeichnen")
        self.sw_rec.toggled.connect(lambda c: setattr(self.sim, "record_swept", c))
        v.addWidget(self.sw_rec)
        v.addWidget(row(self._btn("Swept Volume löschen", lambda: (self.sim.swept.clear(), self.viewer.update())),
                        self._btn("Swept Volume exportieren …", self.export_swept)))
        v.addWidget(self._btn("Energie-/Taktzähler zurücksetzen", self.reset_counters))
        v.addStretch(1)
        l.addWidget(g2)
        self.reach_out = QPlainTextEdit()
        self.reach_out.setReadOnly(True)
        l.addWidget(self.reach_out, 1)
        return w

    def reset_counters(self):
        self.sim.energy_wh = 0
        self.sim.cycle_times.clear()

    def calc_reach(self):
        self.reach_out.setPlainText("Berechne …")
        QApplication.processEvents()
        ok, bad = self.sim.reach_cloud()
        self.viewer.reach_ok, self.viewer.reach_bad = ok, bad
        self.viewer.show_reach = True
        self.viewer.update()
        tot = max(len(ok) + len(bad), 1)
        self.reach_out.setPlainText(f"Erreichbar (Werkzeug senkrecht): {len(ok)} von {tot} Rasterpunkten "
                                    f"({100 * len(ok) / tot:.0f} %)\nGrün = erreichbar, rot = nicht erreichbar.")

    def check_scene_reach(self):
        out = []
        for o in self.sim.scene:
            if o.graspable or o.kind in ("workpiece",):
                p = np.array(o.pos) + np.array([0, 0, o.size[2] + 5])
                out.append(f"{'✔' if self.sim.reachable(p) else '✘'} Objekt {o.name} ({p[0]:.0f},{p[1]:.0f},{p[2]:.0f})")
        for w in self.sim.waypoints:
            T = self.sim.base_mat() @ pose_to_mat(*w["pos"])
            ok = self.sim.model.ik(T @ inv(self.sim.tool_mat()), HOME) is not None
            out.append(f"{'✔' if ok else '✘'} Punkt {w['name']}")
        self.reach_out.setPlainText("\n".join(out) or "Keine greifbaren Objekte oder Punkte vorhanden.")

    def export_swept(self):
        f, _ = QFileDialog.getSaveFileName(self, "Swept Volume", "swept_volume.csv", "CSV (*.csv)")
        if f:
            with open(f, "w", encoding="utf8") as fh:
                fh.write("x_mm;y_mm;z_mm;kantenlaenge_mm\n")
                for p in self.sim.swept_boxes():
                    fh.write(f"{p[0]:.0f};{p[1]:.0f};{p[2]:.0f};40\n")
            self.log_msg(f"Swept Volume exportiert: {len(self.sim.swept)} Voxel")

    # ----- Python-Skript
    def _script_tab(self):
        w = QWidget()
        l = QHBoxLayout(w)
        self.script = QPlainTextEdit()
        self.script.setFont(QFont("Cascadia Mono", 10))
        self.script.setPlainText(
            "# Zugriff: sim (Simulation), win (Hauptfenster), np\n"
            "# Beispiel: Ausgang setzen und Achsen lesen\n"
            "sim.io.set_out(2, True)\n"
            "print('Achsen:', [round(float(x), 1) for x in sim.q])\n"
            "print('TCP:', [round(x, 1) for x in sim.sv['POS_ACT']])\n")
        self.script_out = QPlainTextEdit()
        self.script_out.setReadOnly(True)
        l.addWidget(self.script, 3)
        c = QVBoxLayout()
        c.addWidget(self._btn("▶ Skript ausführen", self.run_script))
        c.addWidget(self.script_out, 1)
        l.addLayout(c, 2)
        return w

    @tracked
    def run_script(self):
        buf = _io.StringIO()
        ns = {"sim": self.sim, "win": self, "np": np, "mat": pose_to_mat}
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            try:
                exec(self.script.toPlainText(), ns)
            except Exception:
                traceback.print_exc()
        self.script_out.setPlainText(buf.getvalue())
        self.viewer.update()

    # ----- Konnektivitaet
    def _connect_tab(self):
        w = QWidget()
        l = QVBoxLayout(w)
        g = QGroupBox("OPC-UA-Server (Ximaj RoboSim stellt Daten bereit)")
        f = QFormLayout(g)
        self.opc_port = spin(1024, 65535, int(self.settings.get("opcua_port", 4840)), 0, 1)
        self.opc_port.valueChanged.connect(lambda v: (self.settings.__setitem__("opcua_port", int(v)), save_settings(self.settings)))
        self.opc_autoport = QCheckBox("Freien Port automatisch wählen, wenn belegt")
        self.opc_autoport.setChecked(self.settings.get("opcua_autoport", True))
        self.opc_autoport.toggled.connect(lambda c: (self.settings.__setitem__("opcua_autoport", c), save_settings(self.settings)))
        self.opc_local = QCheckBox("Nur auf diesem PC erreichbar (localhost)")
        self.opc_local.setChecked(self.settings.get("opcua_local", False))
        self.opc_local.toggled.connect(lambda c: (self.settings.__setitem__("opcua_local", c), save_settings(self.settings)))
        self.opc_nio = spin(16, 1024, int(self.settings.get("opcua_nio", 128)), 0, 16)
        self.opc_nio.valueChanged.connect(lambda v: (self.settings.__setitem__("opcua_nio", int(v)), save_settings(self.settings)))
        self.opc_btn = QPushButton("Server starten")
        self.opc_btn.setObjectName("primary")
        self.opc_btn.clicked.connect(self.toggle_opc)
        self.opc_lbl = QLabel("gestoppt")
        self.opc_lbl.setWordWrap(True)
        self.opc_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.opc_eps = QListWidget()
        self.opc_eps.setMinimumHeight(120)
        self.opc_eps.itemDoubleClicked.connect(lambda it: (QApplication.clipboard().setText(it.text()),
                                                          self.statusBar().showMessage(f"Kopiert: {it.text()}", 4000)))
        self.opc_auto = QCheckBox("Beim Programmstart automatisch starten")
        self.opc_auto.setChecked(bool(self.settings.get("opcua_autostart")))
        self.opc_auto.toggled.connect(lambda c: (self.settings.__setitem__("opcua_autostart", c), save_settings(self.settings)))
        f.addRow("Port", self.opc_port)
        f.addRow(self.opc_autoport)
        f.addRow(self.opc_local)
        f.addRow("E/A je Richtung", self.opc_nio)
        f.addRow(self.opc_btn)
        f.addRow("Status", self.opc_lbl)
        f.addRow("Endpunkte (Doppelklick kopiert)", self.opc_eps)
        nodes_btn = QPushButton("Roboterpunkte / OPC-UA-Knoten …")
        nodes_btn.setObjectName("opcNodesButton")
        nodes_btn.clicked.connect(self.opc_nodes_show)
        f.addRow(nodes_btn)
        f.addRow(self.opc_auto)
        l.addWidget(g)
        g2 = QGroupBox("OPC-UA-Clients (Ximaj RoboSim verbindet sich mit SPS/Steuerung/Leitsystem)")
        v2 = QVBoxLayout(g2)
        self.opc_ct = QTableWidget(0, 4)
        self.opc_ct.setHorizontalHeaderLabels(["Name", "URL", "Zuordnungen", "Status"])
        self.opc_ct.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.opc_ct.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.opc_ct.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.opc_ct.cellDoubleClicked.connect(lambda r, c: self.opc_client_edit(r))
        v2.addWidget(self.opc_ct)
        hb = QGridLayout()
        for index, (txt, fn) in enumerate((("Neu …", lambda: self.opc_client_edit(None)), ("Bearbeiten …", lambda: self.opc_client_edit(self.opc_ct.currentRow())),
                        ("Verbinden", self.opc_client_connect), ("Trennen", self.opc_client_disconnect),
                        ('Schreiben freigeben', self.opc_client_arm), ('Live-Diagnose', self.opc_client_diagnose),
                        ("Entfernen", self.opc_client_remove))):
            b = QPushButton(txt)
            b.clicked.connect(lambda _=False, f=fn: f())
            hb.addWidget(b, index // 4, index % 4)
        v2.addLayout(hb)
        l.addWidget(g2)
        info = QLabel(
            "Server-Knoten: Simulation (State, Time, SpeedFactor, StartAll/StopAll/ResetAll) · Robots/<Name> (State, Line, "
            "Message, Override, Axes A1–A6, Tcp X–C, E1, Start/Stop/Pause/Reset/LoadProgram) · Robot (aktiver Roboter) · "
            "IO/In, IO/Out (lesen/schreiben) · Components (Sensoren, Förderer, Erzeuger, Farbsensoren, Leuchten).\n"
            "Der Server ist ohne Anmeldung und für das lokale/vertrauenswürdige Netz gedacht; Firewall-Freigabe bei Bedarf selbst einrichten.")
        info.setWordWrap(True)
        info.setObjectName("muted")
        l.addWidget(info)
        l.addStretch(1)
        self.opc_clients = []
        return w

    def opc_nodes_show(self):
        if not self.opc.running:
            QMessageBox.information(self, "OPC-UA-Knoten", "Starte zuerst den RoboSim-OPC-UA-Server. Danach stehen seine tatsächlichen NodeIds bereit.")
            return
        import dialogs
        dialogs.opcua_nodes_dialog(self, self.opc)

    def _opc_status(self):
        if self.opc.running:
            txt = f"läuft auf Port {self.opc.port}"
            if self.opc.info:
                txt += f" – {self.opc.info}"
            self.opc_lbl.setText(txt)
            self.opc_lbl.setStyleSheet(f"color:{B['ok']}")
        else:
            self.opc_lbl.setText(f"Fehler: {self.opc.error}" if self.opc.error else "gestoppt")
            self.opc_lbl.setStyleSheet(f"color:{B['error']}" if self.opc.error else "")
        self.opc_eps.clear()
        if self.opc.running:
            self.opc_eps.addItems(self.opc.endpoints())
        self.opc_btn.setText("Server stoppen" if self.opc.running else "Server starten")

    def toggle_opc(self):
        if self.opc.running:
            self.opc.stop()
            self._opc_status()
            self.log_msg("OPC-UA-Server gestoppt")
            return
        self.opc = OpcUaService(self.sim, int(self.opc_port.value()), self.opc_autoport.isChecked(),
                                self.opc_local.isChecked(), int(self.opc_nio.value()))
        ok = self.opc.start()
        self._opc_status()
        if ok:
            self.log_msg(f"OPC-UA-Server läuft: {self.opc.endpoints()[0]}" + (f" ({self.opc.info})" if self.opc.info else ""))
            self.statusBar().showMessage(f"OPC-UA-Server läuft auf Port {self.opc.port}", 8000)
        else:
            self.log_msg(f"OPC-UA-Server nicht gestartet: {self.opc.error}")
            QMessageBox.warning(self, "OPC-UA-Server", f"Der Server konnte nicht gestartet werden:\n{self.opc.error}")

    def process_opc_commands(self):
        while self.opc.commands:
            item = self.opc.commands.pop(0)
            cmd, arg = item[0], item[1]
            rname = item[2] if len(item) > 2 else None
            r = next((x for x in self.sim.robots if x.name == rname), None)
            if rname is not None and r is None:
                self.log_msg(f"OPC-UA-Befehl verworfen: Roboter „{rname}“ ist nicht mehr vorhanden.")
                continue
            if cmd == "start_all":
                self.sim.start_all()
            elif cmd == "stop_all":
                self.sim.stop_all()
            elif r is not None:                      # Befehl fuer einen bestimmten Roboter
                if cmd == "start":
                    r.start()
                elif cmd == "stop":
                    r.stop(0)
                elif cmd == "pause":
                    r.pause()
                elif cmd == "reset":
                    r.reset()
                elif cmd == "load":
                    r.load_program(str(arg))
                    if r is self.sim.active:
                        self.editor.setPlainText(str(arg))
            elif cmd == "start":
                self.run_prog()
            elif cmd == "stop":
                self.sim.stop(0)
            elif cmd == "pause":
                self.sim.pause()
            elif cmd == "reset":
                self.reset_all()
            elif cmd == "load":
                self.editor.setPlainText(str(arg))

    def _opc_indicator(self):
        con = sum(1 for c in getattr(self, "opc_clients", []) if c.connected)
        txt = f"OPC UA: Server :{self.opc.port}" if self.opc.running else "OPC UA: Server aus"
        if getattr(self, "opc_clients", None):
            txt += f" · Clients {con}/{len(self.opc_clients)}"
        self.opc_ind.setText(txt)
        self.opc_ind.setStyleSheet(f"color:{B['ok'] if self.opc.running or con else B['muted']}")
        if getattr(self, "opc_clients", None):
            self.opc_clients_refresh()

    # ----- OPC-UA-Clients
    def opc_clients_refresh(self):
        t = self.opc_ct
        t.setRowCount(len(self.opc_clients))
        for i, c in enumerate(self.opc_clients):
            st = c.status + (f": {c.error}" if c.error else "")
            bad = sum(1 for m in c.mappings if m.get("error"))
            for j, txt in enumerate((c.name, c.url, f"{len(c.mappings)}" + (f" ({bad} Fehler)" if bad else ""), st)):
                it = t.item(i, j) or QTableWidgetItem()
                it.setText(txt)
                t.setItem(i, j, it)

    def opc_client_edit(self, row):
        import dialogs
        from opcua_client import ClientLink
        c = self.opc_clients[row] if row is not None and 0 <= row < len(self.opc_clients) else ClientLink(self.sim)
        edit = ClientLink.from_dict(self.sim, c.to_dict())
        edit.password = c.password
        if dialogs.opcua_client_dialog(self, edit):
            c.disconnect(wait=False)
            if c in self.opc_clients:
                self.opc_clients[self.opc_clients.index(c)] = edit
            else:
                self.opc_clients.append(edit)
            self.sim.opcua_clients = [x.to_dict() for x in self.opc_clients]
            self.opc_clients_refresh()

    def opc_client_connect(self):
        r = self.opc_ct.currentRow()
        if 0 <= r < len(self.opc_clients):
            c = self.opc_clients[r]
            ok = c.connect(wait=False)
            self.log_msg(f"OPC-UA-Client „{c.name}“: " + ("Verbindung wird aufgebaut" if ok else f"Fehler {c.error}"))
            self.opc_clients_refresh()

    def opc_client_disconnect(self):
        r = self.opc_ct.currentRow()
        if 0 <= r < len(self.opc_clients):
            self.opc_clients[r].disconnect(wait=False)
            self.opc_clients_refresh()

    def opc_client_remove(self):
        r = self.opc_ct.currentRow()
        if 0 <= r < len(self.opc_clients):
            self.opc_clients.pop(r).disconnect(wait=False)
            self.sim.opcua_clients = [x.to_dict() for x in self.opc_clients]
            self.opc_clients_refresh()

    def opc_client_arm(self):
        r = self.opc_ct.currentRow()
        if 0 <= r < len(self.opc_clients):
            try:
                self.opc_clients[r].arm_writes()
                self.log_msg('Schreibzugriffe ausdrücklich freigegeben: ' + self.opc_clients[r].name)
            except ValueError as exc:
                QMessageBox.warning(self, 'OPC UA', str(exc))

    def opc_client_diagnose(self):
        r = self.opc_ct.currentRow()
        if 0 <= r < len(self.opc_clients):
            import upgrade_ui
            upgrade_ui.client_diagnose(self, self.opc_clients[r])

    def opc_clients_load(self):
        """Client-Verbindungen aus dem Projekt uebernehmen (nicht automatisch verbinden)"""
        from opcua_client import ClientLink
        for c in getattr(self, "opc_clients", []):
            c.disconnect()
        self.opc_clients = [ClientLink.from_dict(self.sim, d) for d in (getattr(self.sim, "opcua_clients", None) or [])]
        self.opc_clients_refresh()

    # ----- Update
    def _update_tab(self):
        w = QWidget()
        l = QVBoxLayout(w)
        self.up_lbl = QLabel(f"{B['product']}  Version {VERSION}   ·   {B['company']}")
        self.up_lbl.setObjectName("brand")
        l.addWidget(self.up_lbl)
        self.up_notes = QPlainTextEdit()
        self.up_notes.setReadOnly(True)
        self.up_notes.setPlainText(f"Update-Quelle: GitHub-Releases von {upd.UPDATE_REPO}\n"
                                   "Updates werden geprüft (SHA-256), gesichert und erst nach Bestätigung installiert.")
        l.addWidget(self.up_notes)
        self.up_bar = QProgressBar()
        l.addWidget(self.up_bar)
        self.up_auto = QCheckBox("Beim Start automatisch nach Updates suchen")
        self.up_auto.setChecked(self.settings.get("auto_update", True))
        self.up_auto.toggled.connect(lambda c: (self.settings.__setitem__("auto_update", c), save_settings(self.settings)))
        l.addWidget(self.up_auto)
        self.up_btn = self._btn("Nach Updates suchen", lambda: self.check_updates(False))
        self.up_install = self._btn("Update herunterladen & installieren", self.start_download)
        self.up_install.setEnabled(False)
        self._package_ready = False
        self.up_rollback = self._btn("Vorherige Version installieren", self.do_rollback)
        l.addWidget(row(self.up_btn, self.up_install, self.up_rollback))
        self.up_token = QLineEdit()
        self.up_token.setEchoMode(QLineEdit.EchoMode.Password)
        self.up_token.setPlaceholderText("Optional: GitHub-Zugang für private Releases")
        access_hint = QLabel("Vorhandene GitHub-CLI-Anmeldung wird automatisch genutzt. Ein eigener Zugang wird verschlüsselt für diesen Windows-Benutzer gespeichert.")
        access_hint.setWordWrap(True)
        l.addWidget(access_hint)
        l.addWidget(row(self.up_token, self._btn("Zugang speichern", self.save_update_access)))
        releases = QLabel(f'<a href="https://github.com/{upd.UPDATE_REPO}/releases">GitHub-Releases im Browser öffnen</a>')
        releases.setOpenExternalLinks(True)
        l.addWidget(releases)
        return w

    def save_update_access(self):
        try:
            upd.release_access.save_token(self.up_token.text())
            self.up_token.clear()
            self.check_updates(False)
        except Exception as e:
            self.up_notes.setPlainText(f"Zugang konnte nicht gespeichert werden: {e}")

    def show_updates(self):
        self.dock_b.show()
        self.dock_b.raise_()
        self.bottom.setCurrentIndex(7)

    def check_updates(self, silent=False):
        if getattr(self, "_transfer_running", False):
            if not silent:
                self.show_updates()
            return
        if getattr(self, "_checking_updates", False):
            if not silent:
                self._silent = False
                self.show_updates()
            return
        self._checking_updates = True
        self.up_rollback.setEnabled(False)
        self._silent = silent
        self.last_info = None
        self._package_ready = False
        self.up_install.setText("Update herunterladen & installieren")
        self.up_btn.setEnabled(False)
        self.up_install.setEnabled(False)
        self.up_notes.setPlainText("Suche nach neuen GitHub-Releases …")
        self.statusBar().showMessage("Updatesuche läuft …")
        if not silent:
            self.show_updates()

        def work():
            try:
                info = upd.check()
            except Exception as e:
                info = {"error": f"Updatesuche fehlgeschlagen: {e}", "current": VERSION}
            self.update_found.emit(info)
        threading.Thread(target=work, daemon=True).start()

    def on_update_found(self, info):
        self._checking_updates = False
        self.up_rollback.setEnabled(True)
        self.up_btn.setEnabled(True)
        self.up_install.setEnabled(False)
        self.last_info = info
        if info.get("error") and not info.get("available"):
            self.up_notes.setPlainText(info["error"])
            self.statusBar().showMessage("Updatesuche fehlgeschlagen – Details unter Update / Info", 10000)
            if not self._silent:
                self.show_updates()
            return
        if info.get("available"):
            self.up_notes.setPlainText(f"Neue Version {info['latest']} verfügbar (installiert: {info['current']})\n\n{info.get('notes', '')}")
            self.up_install.setEnabled(True)
            self.show_updates()
            self.statusBar().showMessage(f"Update {info['latest']} verfügbar", 10000)
        else:
            self.up_notes.setPlainText(f"Kein neueres Release gefunden. Installiert: {info['current']}; GitHub: {info.get('latest', 'unbekannt')}.")
            self.statusBar().showMessage("Kein neueres Update gefunden", 10000)

    def start_download(self):
        if getattr(self, "_transfer_running", False):
            return
        if self._package_ready:
            self.on_update_done("")
            return
        info = self.last_info
        if not info or not info.get("available"):
            return
        self.up_install.setEnabled(False)
        self.up_btn.setEnabled(False)
        self.up_rollback.setEnabled(False)
        self._transfer_running = True

        def work():
            try:
                upd.download(info, self.update_progress.emit)
                self.update_done.emit("")
            except Exception as e:
                self.update_done.emit(str(e))
        threading.Thread(target=work, daemon=True).start()

    def on_update_done(self, err):
        self._transfer_running = False
        self.up_btn.setEnabled(True)
        self.up_rollback.setEnabled(True)
        if err:
            self.up_notes.setPlainText(f"Update fehlgeschlagen: {err}")
            self.up_install.setEnabled(bool(self._package_ready or (self.last_info or {}).get("available")))
            return
        self._package_ready = True
        self.up_install.setText("Geladenes Paket installieren")
        self.up_install.setEnabled(True)
        if QMessageBox.question(self, "Installation bereit", "Setup wurde geladen und geprüft.\nJetzt neu starten und installieren?") \
                == QMessageBox.StandardButton.Yes:
            self.restart_for_update()
        else:
            self.up_notes.setPlainText("Setup ist bereit. Zum Einspielen auf Geladenes Paket installieren klicken.")

    def restart_for_update(self):
        try:
            upd.restart_and_apply()
        except Exception as e:
            self.up_notes.setPlainText(f"Installation konnte nicht gestartet werden: {e}")
            self.show_updates()
            return
        self.timer.stop()
        self.opc.stop()
        QApplication.quit()

    def do_rollback(self):
        if getattr(self, "_transfer_running", False) or getattr(self, "_checking_updates", False):
            self.show_updates()
            return
        if QMessageBox.question(self, "Zurücksetzen", "Die vorherige Version laden, prüfen und zur Installation vorbereiten?") != QMessageBox.StandardButton.Yes:
            return
        if not upd.FROZEN:
            if upd.rollback():
                self.restart_for_update()
            else:
                QMessageBox.information(self, "Zurücksetzen", "Keine gesicherte Quellversion vorhanden.")
            return
        self.show_updates()
        self._package_ready = False
        self.up_btn.setEnabled(False)
        self.up_install.setEnabled(False)
        self.up_rollback.setEnabled(False)
        self.up_notes.setPlainText("Vorherige Version wird geladen und geprüft …")
        self._transfer_running = True
        def work():
            try:
                upd.prepare_rollback(self.update_progress.emit)
                self.update_done.emit("")
            except Exception as e:
                self.update_done.emit(str(e))
        threading.Thread(target=work, daemon=True).start()

    def about(self):
        box = QMessageBox(self)
        box.setWindowTitle("Über")
        pm = QPixmap(theme.LOGO)
        if not pm.isNull():
            box.setIconPixmap(pm.scaledToHeight(96, Qt.TransformationMode.SmoothTransformation))
        box.setText(f"<h3 style='font-family:Saira,Bahnschrift'>{B['product']} {VERSION}</h3><p>{B['tagline']}</p>"
                    f"<p>Eigenentwicklung der <b>{B['company']}</b><br>"
                    "<a href='https://ximaj.com'>ximaj.com</a></p>"
                    "<p style='color:#98abc6'>Eigenständige Software, nicht mit Dritt-Herstellern verbunden.</p>")
        box.exec()

    # ---------------------------------------------------------------- Programm
    def run_prog(self):
        """Start: alle Roboter mit ihren Programmen gleichzeitig (pausierte werden fortgesetzt)."""
        self._displayed_error = None
        if self.sim.any_busy():
            return
        self.sim.active.src = self.editor.toPlainText()
        if any(r.state == "paused" for r in self.sim.robots):
            for r in self.sim.robots:
                if r.state == "paused":
                    r.resume(False)
            return
        if not self.sim.any_busy():
            from diagnostics import inspect_cell
            # Fehler blockieren den Start; Warnungen bleiben nachvollziehbar im Cockpit.
            issues = inspect_cell(self.sim)
            errors = [i for i in issues if i.level == 'Fehler']
            if errors:
                self.open_cockpit()
                self.log_msg('Start abgebrochen: ' + errors[0].message)
                return
            for r in self.sim.robots:
                if r.mode == "statements":
                    errs = stm.validate(r.statements)
                    if errs:
                        QMessageBox.warning(self, "Statements", f"{r.name}:\n" + "\n".join(errs))
                        return
                    r.src, r.stmt_linemap = stm.generate(r.statements, _ident(r.name))
                    if r is self.sim.active:
                        self.editor.setPlainText(r.src)
                r.load_program(r.src)
            self.sim.start_all(False)

    def step_prog(self):
        self.sim.world_paused = False
        if self.sim.state in ("idle", "error", "stopped"):
            self.sim.load_program(self.editor.toPlainText())
            self.sim.start(True)
        elif self.sim.state == "paused":
            self.sim.resume(True)

    def reset_all(self):
        self.jog = None
        self.sim.reset_world()
        self._displayed_error = None
        self.refresh_ui()
        self.viewer.update()

    # ---------------------------------------------------------------- Tick
    def on_tick(self):
        import time
        now = time.perf_counter()
        dt = min(now - self._t_last, 0.1)
        self._t_last = now
        self.do_jog(dt)
        active = self.sim.state in ("running", "wait", "stopping") or self.jog
        try:
            self.sim.tick(dt)
        except Exception as exc:
            self.sim.pause_all()
            self.log_msg(f'Simulation angehalten: {type(exc).__name__}: {exc}')
            self.statusBar().showMessage(self.sim.message)
        self.process_opc_commands()
        self._opc_tick = getattr(self, "_opc_tick", 0) + 1
        if self._opc_tick % 60 == 0:                     # etwa jede Sekunde: Verbindungsstatus anzeigen
            self._opc_indicator()
            self.opc_clients_refresh()
        self.viewer.update()
        if self.recording:
            self._rec_t += 1
            if self._rec_t % 3 == 0:
                self.frames.append(self.viewer.grabFramebuffer())
        self._ui_t += dt
        if self._ui_t > 0.1:
            self._ui_t = 0
            self.refresh_ui()

    def refresh_ui(self):
        self.ribbon.update_history()
        s = self.sim
        grip = s.active.gripper_info()
        if grip["holding"]:
            grip_text = f"Hält: {grip['part']}"
        elif not grip["output"]:
            grip_text = "Deaktiviert (Ausgang 0)"
        elif not grip["command"]:
            grip_text = f"Offen · $OUT[{grip['output']}] = FALSE"
        elif grip["nearest"]:
            grip_text = f"Greifbefehl aktiv · {grip['nearest']}: {grip['distance']:.1f} mm Abstand, Reichweite {s.tool.grip_range:.1f} mm"
        else:
            grip_text = "Greifbefehl aktiv · kein greifbares Werkstück vorhanden"
        if grip["conflicts"]:
            grip_text += f"\nZuordnung prüfen: $OUT[{grip['output']}] steuert auch " + ", ".join(grip["conflicts"])
        self.grip_status.setText(grip_text)
        self.grip_status.setStyleSheet(f"color:{B['warn'] if grip['conflicts'] else B['text']}")
        for i in range(6):
            self.ax_lbl[i].setText(f"{s.q[i]:.1f}°")
            self.cart_lbl[i].setText(f"{s.sv['POS_ACT'][i]:.1f}")
        st, tn = s.model.status_turn(s.q)
        self.st_lbl.setText(f"Status S={st}  Turn T={tn}")
        try:
            sg = s.model.singularity(s.q)
            self.sing.setValue(int(min(1.0, sg * 4) * 100))
        except Exception:
            pass
        col = {"idle": B["muted"], "running": B["ok"], "wait": B["warn"], "paused": B["warn"],
               "error": B["error"], "stopped": B["error"], "stopping": B["error"]}[s.state]
        self.state_l.setText(f"<span style='color:{col}'>● {s.state.upper()}</span>  Zeile {s.cur_line}  ·  t={s.t:.1f}s ")
        self.state_l.setToolTip(s.message)
        if s.state == "wait" and s.wait_fn is not None:
            self.state_l.setText(self.state_l.text() + " · wartet auf Bedingung (E/A prüfen)")
        if s.state == "error" and getattr(self, "_displayed_error", None) != (id(s.active), s.cur_line):
            self._displayed_error = (id(s.active), s.cur_line)
            self.dock_b.show()
            self.bottom.setCurrentIndex(2)
            self.statusBar().showMessage(s.message)
        self.highlight_line()
        self.editor.setReadOnly(any(r.busy() or r.state == 'paused' for r in s.robots))
        self.editor.gutter.update()
        self.st_highlight()
        self.refresh_io()
        self.a_state.setText(s.state)
        self.a_run.setText(f"{s.run_t:.2f} s")
        ct = s.cycle_times
        self.a_cyc.setText(f"{ct[-1]:.2f} s / {sum(ct) / len(ct):.2f} s  ({len(ct)} Zyklen)" if ct else "-")
        self.a_en.setText(f"{s.energy_wh * 1000:.1f} mWh")
        self.a_pw.setText(f"{s.power_w:.0f} W")
        self.a_stop.setText(f"{s.stop_dist:.1f}" if s.stop_dist is not None else "-")
        self.a_col.setText(s.collision or "keine")
        tp = s.throughput()
        self.a_tp.setText(f"{tp['fertig']} fertig · {tp['erzeugt']} erzeugt · {tp['im_umlauf']} im Umlauf · "
                          f"{tp['pro_stunde']:.0f} Teile/h")
        r = s.active
        self.e1_lbl.setText(f"E1 = {r.e1:.1f} mm" if r.track is not None else "keine Linearachse")
        if len(s.robots) > 1:
            busy = sum(1 for x in s.robots if x.busy())
            self.state_l.setText(self.state_l.text() + f"  ·  {busy}/{len(s.robots)} Roboter aktiv")
        if getattr(self, '_log_revision', -1) != s.log_revision:
            self._log_revision = s.log_revision
            self.log_view.setPlainText("\n".join(s.log))
            self.log_view.verticalScrollBar().setValue(self.log_view.verticalScrollBar().maximum())
        if not self.sz_table.hasFocus() and self.sz_table.rowCount() != len(s.safety):
            self.fill_zones()
        if self.pt.rowCount() != len(s.waypoints):
            self.fill_points()

    # ---------------------------------------------------------------- Dateien
    def new_project(self):
        was_dirty = self.dirty
        if not self._confirm_discard():
            return
        if was_dirty:
            self.autosave.clear(self.project_path)
        self._restoring = True
        self.sim.reset_world()
        for client in self.opc_clients:
            client.disconnect(wait=False)
        fresh = Simulation().to_dict()
        fresh['scene'] = [o.to_dict() for o in default_scene()]
        fresh['robots'][0]['tool']['grip_out'] = 1
        self.sim.from_dict(fresh)
        self.opc_clients_load()
        self.editor.setPlainText(DEFAULT_PROGRAM)
        self.project_path = None
        self.viewer.selected, self.viewer.selection = None, []
        self.sync_from_sim()
        self.sim.src = self.editor.toPlainText()
        self._restoring = False
        self._clean_history()

    def save_project(self, as_new=False):
        p = self.project_path
        if as_new or not p:
            p, _ = QFileDialog.getSaveFileName(self, "Projekt speichern", "zelle.xrsim", "Ximaj Projekt (*.xrsim)")
            if not p:
                return
        old_path = self.project_path
        self.sim.src = self.editor.toPlainText()
        try:
            project_store.write_project(p, self.sim.to_dict())
        except (OSError, ValueError) as err:
            QMessageBox.warning(self, 'Speichern', f'Projekt konnte nicht gespeichert werden: {err}')
            return False
        self.project_path = p
        self._remember(p)
        self.log_msg(f"Projekt gespeichert: {p}")
        self.mark_changed()
        self._saved_snapshot = self.history.current
        self.autosave.clear(old_path)
        self.autosave.clear(p)
        self._update_history_ui()
        return True

    def open_project(self, path=None):
        p = path if isinstance(path, str) else QFileDialog.getOpenFileName(self, "Projekt öffnen", "", "Ximaj Projekt (*.xrsim)")[0]
        if not p:
            return
        was_dirty = self.dirty
        if not self._confirm_discard():
            return
        try:
            data = project_store.read_project(p)
            # Die laufende Zelle bleibt bis zum erfolgreichen Probeaufbau unverändert.
            candidate = Simulation()
            model_snapshot = dict(MODELS)
            try:
                candidate.from_dict({**data, 'run_scripts': False})
                loaded_models = dict(MODELS)
            finally:
                MODELS.clear()
                MODELS.update(model_snapshot)
        except (OSError, ValueError, TypeError, KeyError, IndexError) as exc:
            QMessageBox.warning(self, 'Projekt öffnen', f'Projekt konnte nicht geladen werden: {exc}')
            return False
        if was_dirty:
            self.autosave.clear(self.project_path)
        self._restoring = True
        self.sim.reset_world()
        for client in self.opc_clients:
            client.disconnect(wait=False)
        # Der vollständig geladene Probeaufbau wird übernommen, ohne CAD-Dateien doppelt zu laden.
        self.sim.__dict__.clear()
        self.sim.__dict__.update(candidate.__dict__)
        for robot in self.sim.robots:
            robot.w = self.sim
        MODELS.update(loaded_models)
        self.sim.world_paused = True
        self.sim.run_scripts = bool(data.get('run_scripts', False))
        try:
            self.sim.init_scripts()
        except Exception as exc:
            self.sim.script_host = None
            self.sim.say('Komponenten-Skripte konnten nicht gestartet werden: ' + str(exc))
        self.viewer.selected, self.viewer.selection = None, []
        self.editor.setPlainText(self.sim.src)
        self.project_path = p
        self._remember(p)
        self.sync_from_sim()
        self.opc_clients_load()
        self._restoring = False
        self._clean_history()

    def _remember(self, p):
        """Projekt in die Liste „Zuletzt verwendet“ (DATEI-Ansicht) aufnehmen"""
        p = os.path.abspath(p)
        rec = [x for x in self.settings.get("recent", []) if os.path.normcase(x) != os.path.normcase(p)]
        self.settings["recent"] = [p] + rec[:14]
        save_settings(self.settings)

    def open_cockpit(self):
        self.dock_b.show()
        self.bottom.setCurrentIndex(self.cockpit_index)
        self.cockpit.check()

    def open_debugger(self):
        self.dock_b.show()
        self.bottom.setCurrentIndex(self.debugger_index)
        self.debugger.refresh()

    @tracked
    def import_vcmx(self):
        p, _ = QFileDialog.getOpenFileName(self, "Projekt/Modell importieren", "", "Layouts/Modelle (*.vcmx *.vcm)")
        if not p:
            return
        run_scripts = False
        if self._vcmx_has_scripts(p):
            a = QMessageBox.question(
                self, "Komponenten-Skripte",
                "Diese Datei enthält Python-Skripte von Komponenten (z. B. Farbsensor, Farbanzeige, Teile-Erzeuger).\n\n"
                "Sollen sie in der Simulation ausgeführt werden? Das ist nötig, damit sich diese Komponenten wie im "
                "Original verhalten.\n\nNur bei Dateien aus vertrauenswürdiger Quelle (z. B. eigenen Projekten) bestätigen.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.Yes)
            run_scripts = a == QMessageBox.StandardButton.Yes
        try:
            rep = vcmx_import.import_file(self.sim, p, run_scripts=run_scripts)
        except Exception as e:
            traceback.print_exc()
            QMessageBox.warning(self, "Import", f"Import fehlgeschlagen:\n{e}")
            return
        self.sync_from_sim()
        if rep.get("main_program"):
            self.use_imported_program(rep["main_program"])
        self.show_import_report(rep)

    @staticmethod
    def _vcmx_has_scripts(path):
        """Schnellpruefung: enthaelt die Datei Komponenten-Skripte (vcCore/vcScript)?"""
        import zipfile
        try:
            with zipfile.ZipFile(path) as z:
                for n in [n for n in z.namelist() if n.endswith((".rsc", ".vcm"))][:40]:
                    data = z.read(n)
                    if b"import vcCore" in data or b"from vcScript import" in data:
                        return True
        except Exception:
            pass
        return False

    @tracked
    def use_imported_program(self, source):
        # Importierter Text muss auch im Robotermodell gespeichert sein.
        r = self.sim.active
        r.mode = "xrl"
        r.load_program(source)
        self.editor.setPlainText(source)
        self.fill_statements()
        self.bottom.setCurrentIndex(1)
        self.dock_b.show()

    def show_import_report(self, rep):
        dlg = QDialog(self)
        dlg.setWindowTitle("Import-Bericht")
        dlg.resize(760, 560)
        l = QVBoxLayout(dlg)
        t = QPlainTextEdit()
        t.setReadOnly(True)
        t.setPlainText("\n".join(rep.get("log", [])))
        l.addWidget(t, 1)
        progs = sorted(rep.get("programs", {}))
        if progs:
            l.addWidget(QLabel(f"{len(progs)} Programme übernommen – in den Editor laden:"))
            c = QComboBox()
            c.addItems(progs)
            if rep.get("main_name"):
                c.setCurrentText(rep["main_name"])
            l.addWidget(QLabel("Startmodul: Auswahl lädt auch Unterprogramme und globale Daten (z. B. XHOME)."))
            l.addWidget(c)
            l.addWidget(self._btn("Programm in Editor laden",
                                  lambda: self.use_imported_program(vcmx_import.program_source(rep, c.currentText()))))
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        bb.rejected.connect(dlg.reject)
        l.addWidget(bb)
        dlg.exec()

    def import_program(self):
        p, _ = QFileDialog.getOpenFileName(self, "Programm importieren", "", "Programme (*.xrl *.src *.txt);;Alle (*.*)")
        if p:
            self.use_imported_program(open(p, encoding="utf8", errors="replace").read())

    def export_program(self):
        p, _ = QFileDialog.getSaveFileName(self, "Programm exportieren", "programm.xrl", "XRL (*.xrl);;SRC (*.src)")
        if p:
            open(p, "w", encoding="utf8").write(self.editor.toPlainText())

    def export_config(self):
        p, _ = QFileDialog.getSaveFileName(self, "Konfiguration exportieren", "config.xcfg", "Konfiguration (*.xcfg)")
        if p:
            json.dump({"tool": self.sim.tool.to_dict(), "base": self.sim.base, "root": self.sim.root_pose,
                       "waypoints": self.sim.waypoints, "safety": self.sim.safety}, open(p, "w", encoding="utf8"), indent=1)

    @tracked
    def import_config(self):
        p, _ = QFileDialog.getOpenFileName(self, "Konfiguration importieren", "", "Konfiguration (*.xcfg)")
        if p:
            d = json.load(open(p, encoding="utf8"))
            self.sim.tool.__dict__.update(d.get("tool", {}))
            self.sim.base = d.get("base", self.sim.base)
            self.sim.set_root(d.get("root", self.sim.root_pose))
            self.sim.waypoints = d.get("waypoints", [])
            self.sim.safety = d.get("safety", [])
            self.fill_points()
            self.fill_zones()

    @tracked
    def import_cad(self):
        p, _ = QFileDialog.getOpenFileName(self, "CAD-Modell", "", "CAD/3D-Modelle (*.step *.stp *.iges *.igs *.stl *.obj "
                                           "*.ply *.glb *.gltf *.3mf *.off)")
        if not p:
            return
        try:
            self.statusBar().showMessage("CAD-Datei wird gelesen …")
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            QApplication.processEvents()
            o = SceneObj(os.path.splitext(os.path.basename(p))[0], "mesh", (600, 0, 0), color="#94a3b8")
            try:
                o.load_mesh(p)
            finally:
                QApplication.restoreOverrideCursor()
            self.log_msg(f"CAD importiert: {o.name} · {len(o.mesh[1])} Dreiecke · "
                         f"{o.size[0]:.0f}×{o.size[1]:.0f}×{o.size[2]:.0f} mm")
            self.sim.scene.append(o)
            self.refresh_scene_list()
            self.obj_list.setCurrentRow(len(self.sim.scene) - 1)
        except Exception as e:
            QMessageBox.warning(self, "Import", f"Fehler: {e}")

    @tracked
    def import_dxf(self):
        p, _ = QFileDialog.getOpenFileName(self, "Hallenlayout (DXF)", "", "DXF (*.dxf)")
        if not p:
            return
        try:
            o = SceneObj(os.path.splitext(os.path.basename(p))[0], "drawing", color="#475569")
            o.load_dxf(p)
            self.sim.scene.insert(0, o)
            self.refresh_scene_list()
            self.log_msg(f"Layout importiert: {len(o.lines)} Linien, {o.size[0] / 1000:.1f} × {o.size[1] / 1000:.1f} m")
        except Exception as e:
            QMessageBox.warning(self, "DXF", f"Fehler: {e}")

    @tracked
    def simplify_selected(self):
        o = self.sel()
        if o is None or o.kind != "mesh" or o.mesh is None:
            QMessageBox.information(self, "Vereinfachen", "Bitte ein importiertes CAD-Modell auswählen.")
            return
        from PyQt6.QtWidgets import QInputDialog
        n0 = len(o.mesh[1])
        n, ok = QInputDialog.getInt(self, "CAD-Netz vereinfachen", f"Aktuell {n0} Dreiecke. Ziel-Anzahl:",
                                    max(1000, n0 // 5), 100, max(n0, 100), 1000)
        if ok:
            o.simplify_mesh(n)
            self.viewer.update()
            self.log_msg(f"{o.name}: {n0} → {len(o.mesh[1])} Dreiecke")

    def export_html(self):
        p, _ = QFileDialog.getSaveFileName(self, "3D-Präsentation", "zelle.html", "HTML (*.html)")
        if p:
            try:
                cad.export_html(self.sim, p, f"{os.path.splitext(os.path.basename(p))[0]}")
                self.log_msg(f"3D-Präsentation gespeichert: {p}")
            except Exception as e:
                QMessageBox.warning(self, "Export", f"Fehler: {e}")

    def export_scene3d(self):
        p, _ = QFileDialog.getSaveFileName(self, "Szene exportieren", "zelle.glb", "GLB (*.glb);;OBJ (*.obj);;STL (*.stl)")
        if not p:
            return
        import trimesh
        sc = trimesh.Scene()
        for o in self.sim.scene:
            if o.kind == "mesh" and o.mesh is not None:
                m = trimesh.Trimesh(o.mesh[0], o.mesh[1])
            elif o.kind == "cylinder":
                m = trimesh.creation.cylinder(radius=o.size[0] / 2, height=o.size[2])
                m.apply_translation([0, 0, o.size[2] / 2])
            else:
                m = trimesh.creation.box(extents=o.size)
                m.apply_translation([0, 0, o.size[2] / 2])
            m.apply_transform(o.matrix())
            sc.add_geometry(m, node_name=o.name)
        for i, (a, b, r, nm) in enumerate(self.sim.capsules()):
            m = trimesh.creation.capsule(height=float(np.linalg.norm(b - a)) or 1, radius=float(r))
            d = (b - a) / (np.linalg.norm(b - a) or 1)
            T = trimesh.geometry.align_vectors([0, 0, 1], d)
            m.apply_transform(T)
            m.apply_translation((a + b) / 2)
            sc.add_geometry(m, node_name=f"robot_{nm}")
        sc.export(p)
        self.log_msg(f"Szene exportiert: {p}")

    def save_screenshot(self):
        p, _ = QFileDialog.getSaveFileName(self, "Screenshot", "screenshot.png", "PNG (*.png)")
        if p:
            self.viewer.grabFramebuffer().save(p)

    def toggle_record(self):
        if not self.recording:
            self.frames = []
            self.recording = True
            self.log_msg("Animationsaufnahme gestartet")
            return
        self.recording = False
        if not self.frames:
            return
        p, flt = QFileDialog.getSaveFileName(self, "Video speichern", "simulation.mp4", "Video MP4 (*.mp4);;Animiertes GIF (*.gif)")
        if not p:
            self.frames = []
            return
        if p.lower().endswith(".mp4"):
            try:
                cad.export_mp4(self.frames, p, fps=20)
                self.log_msg(f"Video gespeichert: {p} ({len(self.frames)} Bilder)")
            except Exception as e:
                QMessageBox.warning(self, "Video", f"Fehler: {e}")
            self.frames = []
            return
        d = os.path.dirname(p)
        from PIL import Image
        imgs = []
        for i, f in enumerate(self.frames):
            pth = os.path.join(d, f"frame_{i:04d}.png")
            f.save(pth)
            imgs.append(Image.open(pth).convert("P", palette=Image.Palette.ADAPTIVE).resize((f.width() // 2, f.height() // 2)))
        imgs[0].save(p, save_all=True, append_images=imgs[1:], duration=50, loop=0)
        for i in range(len(self.frames)):
            try:
                os.remove(os.path.join(d, f"frame_{i:04d}.png"))
            except OSError:
                pass
        self.log_msg(f"Animation gespeichert: {len(self.frames)} Bilder in {d}")
        self.frames = []

    def closeEvent(self, e):
        if not self._confirm_discard():
            e.ignore()
            return
        self.autosave_timer.stop()
        self.autosave.clear(self.project_path)
        self.settings["window_state"] = bytes(self.saveState().toHex()).decode()
        self.opc.stop()
        for c in getattr(self, "opc_clients", []):
            c.disconnect()
        save_settings(self.settings)
        super().closeEvent(e)


def default_scene():
    return [
        SceneObj("Tisch", "box", (500, 0, 0), (0, 0, 0), (600, 1000, 20), "#64748b", True, False),
        SceneObj("Teil1", "workpiece", (450, 250, 20), (0, 0, 0), (60, 40, 40), "#f5b83d", False, True),
        SceneObj("Ablage", "box", (450, -250, 0), (0, 0, 0), (120, 120, 20), "#334155", False, False),
    ]


def _ident(name):
    s = "".join(ch if ch.isalnum() else "_" for ch in name)
    return s if s and not s[0].isdigit() else "p_" + s


def make_splash():
    """Startbild im Stil der Website: Navy-Verlauf, RoboSim-Logo, Version."""
    from PyQt6.QtWidgets import QSplashScreen
    from PyQt6.QtGui import QLinearGradient, QFont as _F
    W, H = 640, 360
    pm = QPixmap(W, H)
    p = QPainter(pm)
    g = QLinearGradient(0, 0, W, H * 0.47)
    g.setColorAt(0.0, QColor(B["navy"]))
    g.setColorAt(0.4, QColor(B["navy"]))
    g.setColorAt(1.0, QColor(B["navy_end"]))
    p.fillRect(0, 0, W, H, g)
    logo = QPixmap(theme.LOGO)
    if not logo.isNull():
        lg = logo.scaledToWidth(520, Qt.TransformationMode.SmoothTransformation)
        p.drawPixmap((W - lg.width()) // 2, 95, lg)
    f = _F("Saira")
    if f.family() != "Saira":
        f = _F("Bahnschrift")
    f.setPointSize(11)
    p.setFont(f)
    p.setPen(QColor(255, 255, 255, 190))
    p.fillRect(W // 2 - 28, 262, 56, 3, QColor(B["accent"]))
    p.drawText(0, 280, W, 24, Qt.AlignmentFlag.AlignHCenter, B["tagline"])
    p.drawText(0, 318, W, 24, Qt.AlignmentFlag.AlignHCenter, f"Version {VERSION}  ·  {B['company']}")
    p.end()
    s = QSplashScreen(pm)
    s.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
    return s


def selftest():
    """Pruefung der gebauten EXE ohne Fenster: XimajRoboSim.exe --selftest [STEP-Datei]"""
    import tempfile
    out = []

    def check(name, fn):
        try:
            out.append(f"OK   {name}: {fn()}")
        except Exception as e:
            out.append(f"FEHLER {name}: {type(e).__name__}: {e}")
    check("Version", lambda: VERSION)
    check("cascadio (STEP/IGES)", lambda: __import__("cascadio").__name__)
    step = next((a for a in sys.argv if a.lower().endswith((".step", ".stp"))), None)
    if step:
        check("STEP laden", lambda: f"{len(cad.load_cad(step)[1])} Dreiecke")
    check("ezdxf (DXF)", lambda: __import__("ezdxf").__version__)
    check("ffmpeg (MP4)", lambda: __import__("imageio_ffmpeg").get_ffmpeg_exe())
    check("asyncua (OPC UA)", lambda: __import__("asyncua").__name__)
    def run_opcua():
        import asyncio
        import socket
        from asyncua import Client, ua
        from opcua_nodes import NAMESPACE_URI, ROOT_ID, child_id
        sample = Simulation()
        sample.waypoints = [{"name": "P1", "pos": [1., 2., 3., 4., 5., 6.], "S": 0, "T": 0}]
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        service = OpcUaService(sample, port, local_only=True, n_io=16)
        try:
            if not service.start():
                raise RuntimeError(service.error)
            async def read():
                async with Client(service.endpoints()[0]) as c:
                    ns = await c.get_namespace_index(NAMESPACE_URI)
                    prefix = child_id(ROOT_ID + "/Robots", sample.active.name)
                    pos = await c.get_node(ua.NodeId(prefix + "/Points/P1/Pose", ns)).read_value()
                    axes = await c.get_node(ua.NodeId(prefix + "/Axes/JointPosition", ns)).read_value()
                    if pos != [1., 2., 3., 4., 5., 6.] or axes != list(sample.q):
                        raise ValueError("OPC-UA-Werte stimmen nicht mit der Simulation überein")
                    return f"{len(service.catalog())} echte Knoten, Achsen und Teach-Pose gelesen"
            return asyncio.run(read())
        finally:
            service.stop()
    check("OPC UA Knoten (echter Loopback)", run_opcua)
    check("Vereinfachung", lambda: __import__("fast_simplification").__name__)

    def run_cell():
        s = Simulation()
        e = [e for e in catalog.CATALOG if e["kind"] == "cell"][0]
        catalog.apply(s, e)
        s.start_all()
        for _ in range(60 * 30):
            s.tick(1 / 60)
            if not s.any_busy():
                break
        return f"{s.state}, {s.run_t:.1f} s"
    check("Simulation", run_cell)
    check("Statements", lambda: len(stm.generate([stm.new("PTP"), stm.new("WAIT_TIME")], "t")[0]))
    def run_upgrade():
        from project_store import write_project, read_project
        from diagnostics import inspect_cell
        import upgrade_ui
        s = Simulation()
        s.load_program('DEF main()\n$OUT[6]=TRUE\nWAIT FOR $IN[3]\nEND')
        s.active.breakpoints = {2}
        s.start()
        s.tick(.02)
        assert s.state == 'paused' and not s.io.get_out(6)
        before = s.t
        s.tick(.5)
        assert s.t == before
        s.resume()
        s.tick(.02)
        assert s.state == 'wait' and s.io.get_out(6)
        assert not s.start()
        s.io.set_in(3, True)
        s.tick(.02)
        assert s.state == 'idle'
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, 'test.xrsim')
            write_project(path, s.to_dict())
            assert read_project(path)['robots'][0]['breakpoints'] == [2]
        assert not any(i.level == 'Fehler' for i in inspect_cell(s))
        return 'Haltepunkt, Pause, WAIT, Mehrfachstart und atomare Datei geprüft'
    check('Upgrade 2.0', run_upgrade)
    p = os.path.join(tempfile.gettempdir(), "xrs_selftest.txt")
    open(p, "w", encoding="utf8").write("\n".join(out))
    print("\n".join(out))
    sys.exit(0 if all(x.startswith("OK") for x in out) else 1)


def main():
    if "--selftest" in sys.argv:
        selftest()
    from PyQt6.QtGui import QSurfaceFormat
    fmt = QSurfaceFormat()
    fmt.setSamples(8)                 # Kantenglaettung
    fmt.setDepthBufferSize(24)
    fmt.setStencilBufferSize(8)       # fuer Bodenschatten
    QSurfaceFormat.setDefaultFormat(fmt)
    app = QApplication(sys.argv)

    def _hook(et, ev, tb):
        # Fehler in Bedienelementen nicht zum Absturz werden lassen (PyQt beendet sonst das Programm)
        import traceback
        traceback.print_exception(et, ev, tb)
        w = next((x for x in QApplication.topLevelWidgets() if isinstance(x, MainWindow)), None)
        if w is not None:
            try:
                w.log_msg(f"Fehler: {et.__name__}: {ev}")
                w.statusBar().showMessage(f"Fehler: {ev}", 10000)
            except Exception:
                pass
    sys.excepthook = _hook
    # deutsche Texte fuer Qt-Standarddialoge (Abbrechen, Schliessen, Ja/Nein, Dateidialog)
    from PyQt6.QtCore import QTranslator, QLibraryInfo, QLocale
    app._tr = QTranslator()
    if app._tr.load(QLocale(QLocale.Language.German), "qtbase", "_", QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)):
        app.installTranslator(app._tr)
    app.setStyleSheet(theme.stylesheet())
    app.setApplicationName(B["product"])
    ico = os.path.join(HERE, "assets", "ximaj_robosim.png")
    if os.path.exists(ico):
        app.setWindowIcon(QIcon(ico))
    from time import monotonic
    splash = make_splash()
    splash_started = monotonic()
    splash.show()
    app.processEvents()
    w = MainWindow()

    def show_main_window():
        w.show()
        splash.finish(w)

    remaining_ms = max(0, int(3000 - (monotonic() - splash_started) * 1000))
    QTimer.singleShot(remaining_ms, show_main_window)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
