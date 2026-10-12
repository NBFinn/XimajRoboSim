"""Menueband der Ximaj RoboSim: Reiter START, MODELLIERUNG, PROGRAMM, KONFIGURATION, HILFE und die DATEI-Ansicht.

Baut das Band auf und verbindet jede Schaltflaeche mit einer Funktion des Hauptfensters (win) bzw. der Module
editing, analysis, trace und dialogs.
"""
import os
import numpy as np
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QAction, QKeySequence, QPixmap
from PyQt6.QtWidgets import (QLabel, QMessageBox, QInputDialog, QLineEdit, QWidget, QVBoxLayout, QListWidget,
                             QListWidgetItem, QHBoxLayout, QFileDialog)

import theme
from ribbon import Ribbon, Backstage
from icons import icon
from history import tracked



class RibbonUI:
    def __init__(self, win):
        self.win = win
        self.sim = win.sim
        self.v = win.viewer
        self.clipboard = []
        self.mode_buttons = {}
        rb = self.rb = Ribbon(win)
        win.setMenuWidget(rb)
        self._head()
        self._start()
        self._modeling()
        self._program()
        self._config()
        self._view()
        self._help()
        self.bs = Backstage(win)
        self._backstage()
        rb.file_clicked.connect(self.bs.show_stage)
        self._shortcuts()
        v = self.v
        v.object_moved.connect(self._on_moved)
        v.target_picked.connect(self._on_target)
        v.measured.connect(lambda d: self.msg(d.get("text", "")))
        v.interacted.connect(self._on_interact)
        v.selection_changed.connect(lambda sel: self.msg(f"{len(sel)} Objekte ausgewählt") if len(sel) > 1 else None)
        self.analysis_on = True
        self.analysis_popup = False
        self._last_issue_count = 0
        self._atimer = QTimer(win)
        self._atimer.timeout.connect(self._auto_analysis)
        self._atimer.start(4000)

    # ------------------------------------------------------------------ Hilfen
    def msg(self, text):
        if text:
            self.win.statusBar().showMessage(text, 8000)
            self.win.log_msg(text)

    def sel(self):
        return self.v.selected

    def sels(self):
        s = [o for o in (self.v.selection or []) if o is not None]
        if not s and self.v.selected is not None:
            s = [self.v.selected]
        return s

    def refresh(self):
        self.win.refresh_scene_list()
        self.v.update()

    def _ed(self):
        import editing
        return editing

    def safe(self, fn, *a, **k):
        try:
            return fn(*a, **k)
        except Exception as e:
            import traceback
            traceback.print_exc()
            QMessageBox.warning(self.win, "Ximaj RoboSim", f"{e}")

    def set_mode(self, mode, on=True):
        if not on and self.v.mode == mode:
            mode = "select"
        self.v.mode = mode
        self.v.pts = []
        for m, buttons in self.mode_buttons.items():
            for b in buttons:
                b.blockSignals(True)
                b.setChecked(m == mode)
                b.blockSignals(False)
        hints = {"move": "Verschieben: an den farbigen Achsen ziehen, gelber Ring dreht · Raster nach Einstellung",
                 "pnp": "PnP: Objekt ziehen – an Förderbandenden wird automatisch angedockt",
                 "interact": "Interagieren: Förderband an/aus, Teile-Erzeuger auslösen, Signale schalten",
                 "jog": "Jog: an den Achsen am Werkzeugpunkt ziehen",
                 "measure": "Messen: zwei Punkte anklicken (Strg = Objektursprung)",
                 "dim_linear": "Bemaßung linear: zwei Punkte anklicken",
                 "dim_angle": "Bemaßung Winkel: drei Punkte anklicken (Scheitel in der Mitte)",
                 "snap": "Andocken: Zielobjekt anklicken – Auswahl wird oben aufgesetzt",
                 "align": "Ausrichten: Zielobjekt anklicken – Drehung wird übernommen",
                 "attach": "Fügen: neues Elternobjekt anklicken",
                 "select": "Auswählen: Klick · Strg+Klick ergänzt · Umschalt+Ziehen = Rahmen"}
        self.win.statusBar().showMessage(hints.get(mode, ""), 10000)
        self.v.setFocus()
        self.v.update()

    def mode_btn(self, g, text, ic, mode, large=True, tip=None, menu=None):
        f = (g.large if large else g.small)
        kw = {"menu": menu} if large and menu else {}
        b = f(text, ic, lambda c, m=mode: self.set_mode(m, c), checkable=True, tip=tip, **kw)
        self.mode_buttons.setdefault(mode, []).append(b)
        return b

    # ------------------------------------------------------------------ Kopf rechts
    def _head(self):
        rb = self.rb
        logo = QLabel()
        pm = QPixmap(theme.LOGO)
        if not pm.isNull():
            logo.setPixmap(pm.scaledToHeight(26, Qt.TransformationMode.SmoothTransformation))
        logo.setToolTip("Ximaj RoboSim")
        logo.setStyleSheet("padding: 0 8px; background: transparent;")
        rb.add_head_widget(logo)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Befehl suchen …")
        self.search.setFixedWidth(200)
        self.search.setStyleSheet("QLineEdit{background:rgba(255,255,255,0.12);color:white;border:1px solid "
                                  "rgba(255,255,255,0.25);border-radius:6px;padding:2px 8px;margin:3px 6px}")
        self.search.returnPressed.connect(self.run_search)
        rb.add_head_widget(self.search)

    def run_search(self):
        """Befehlssuche: findet Schaltflaechen aller Reiter und loest sie aus"""
        q = self.search.text().strip().lower()
        if not q:
            return
        import upgrade_ui
        upgrade_ui.command_palette(self.win, q)

    # ------------------------------------------------------------------ gemeinsame Gruppen
    def g_clipboard(self, p):
        g = p.group("Zwischenablage")
        self.undo_button = g.small('Rückgängig', 'undo', self.win.undo, tip='Strg+Z')
        self.redo_button = g.small('Wiederholen', 'redo', self.win.redo, tip='Strg+Y')
        g.column()
        g.small("Kopieren", "copy", self.copy, tip="Strg+C")
        g.small("Einfügen", "paste", self.paste, tip="Strg+V")
        g.small("Löschen", "delete", self.delete, tip="Entf")
        g.column()
        g.small("Gruppieren", "group", self.group, tip="Strg+G")
        g.small("Gruppierung aufheben", "ungroup", self.ungroup, tip="Strg+Umschalt+G")
        return g

    def g_handling(self, p, jog=False, pnp=True):
        g = p.group("Handhabung")
        self.mode_btn(g, "Auswählen", "select", "select",
                      menu=[("Alles auswählen", self.select_all), ("Auswahl aufheben", self.select_none),
                            ("Gleichen Typ auswählen", self.select_same), ("Auswahl umkehren", self.select_invert)])
        self.mode_btn(g, "Verschieben", "move", "move", tip="Objekt mit Achsenkreuz verschieben/drehen")
        if pnp:
            self.mode_btn(g, "PnP", "pnp", "pnp", tip="Plug & Play: Objekte ziehen und automatisch andocken")
        if jog:
            self.mode_btn(g, "Jog", "jog", "jog", tip="Roboter am Werkzeugpunkt ziehen")
        else:
            self.mode_btn(g, "Interagieren", "interact", "interact", tip="Komponenten in der Simulation bedienen")
        return g

    def g_grid(self, p):
        g = p.group("Positionsraster")
        g.spin("Größe", self.v.snap_step, " mm", lambda v: setattr(self.v, "snap_step", v), 1, 10000, 10)
        g.check("Automatische Größe", self.v.snap_auto, lambda c: setattr(self.v, "snap_auto", c),
                tip="Raster passt sich dem Zoom an")
        g.check("Immer fangen", self.v.snap_always, lambda c: setattr(self.v, "snap_always", c))

    def g_tools(self, p, robot_tools=False):
        g = p.group("Werkzeuge")
        self.mode_btn(g, "Messen", "measure", "measure")
        self.mode_btn(g, "Andocken", "snap", "snap", large=False, tip="Auswahl auf ein Zielobjekt setzen")
        self.mode_btn(g, "Ausrichten", "align", "align", large=False, tip="Drehung eines Zielobjekts übernehmen")
        if robot_tools:
            g.small("Robot World Frame verschieben", "robot_frame", self.robot_world_frame)
            g.small("Roboter austauschen", "robot_swap", self.swap_robot)
        return g

    def g_connect(self, p):
        g = p.group("Verbinden")
        g.small("Schnittstellen", "interfaces", self.interfaces)
        g.small("Signale", "signals", self.signals)
        return g

    def g_origin(self, p):
        g = p.group("Ursprung")
        g.small("Positionieren", "origin", self.origin_place)
        g.small("Verschieben", "origin_move", self.origin_move)

    def g_analysis(self, p):
        g = p.group("Projektanalyse")
        g.check("Analyse eingeschaltet", True, lambda c: setattr(self, "analysis_on", c))
        g.check("Automatisches Popup", False, lambda c: setattr(self, "analysis_popup", c))
        g.small("Projektanalyse Fenster", "analysis", self.analysis_window)

    # ------------------------------------------------------------------ START
    def _start(self):
        p = self.rb.add_tab("START")
        self.g_clipboard(p)
        self.g_handling(p)
        self.g_grid(p)
        self.g_tools(p)
        g = p.group("Bemaßung")
        self.mode_btn(g, "Linear", "dim_linear", "dim_linear", large=False)
        self.mode_btn(g, "Winkel", "dim_angle", "dim_angle", large=False)
        g.small("Alle entfernen", "delete", self.clear_dims)
        self.g_connect(p)
        g = p.group("Hierarchie")
        self.mode_btn(g, "Fügen", "attach", "attach", large=False, tip="Auswahl an ein Elternobjekt anhängen")
        g.small("Ablösen", "detach", self.detach)
        g = p.group("Import")
        g.large("Geometrie", "geometry", self.win.import_cad, tip="CAD: STEP, IGES, STL, OBJ, PLY, GLB, 3MF")
        g = p.group("Export")
        g.small("STL", "stl", lambda: self.export_selection("stl"))
        g.small("Geometrie", "geometry", self.win.export_scene3d)
        g.small("Bild", "image", self.win.save_screenshot)
        g = p.group("Kamera")
        g.large("Kamera-Animator", "camera", self.camera_animator)
        self.g_analysis(p)

    # ------------------------------------------------------------------ MODELLIERUNG
    def _modeling(self):
        # nur Modellierfunktionen; Bearbeiten, Raster, Werkzeuge und Verbinden stehen im Reiter START
        p = self.rb.add_tab("MODELLIERUNG")
        g = p.group("Bewegungsmodus")
        b1 = g.large("Hierarchie", "hierarchy", lambda c: c and self._move_mode(True), checkable=True, checked=True,
                     tip="Kinder bewegen sich mit")
        b2 = g.large("Ausgewählt", "select", lambda c: c and self._move_mode(False), checkable=True,
                     tip="Nur das ausgewählte Objekt bewegen")
        self._mm = (b1, b2)
        g = p.group("Komponente")
        g.small("Im Katalog speichern", "save", self.component_save, tip="Auswahl als eigene Katalog-Komponente speichern")
        g.small("Speichern unter …", "save_as", lambda: self.component_save(True))
        g = p.group("Struktur")
        g.large("Hierarchie\nzeigen", "hierarchy", self.show_structure)
        g = p.group("Geometrie")
        g.large("Features", "features", menu=[("Quader", lambda: self.feature("box")), ("Zylinder", lambda: self.feature("cylinder")),
                                             ("Werkstück", lambda: self.feature("workpiece")), ("Zone (transparent)", lambda: self.feature("zone")),
                                             None, ("CAD-Datei …", self.win.import_cad), ("2D-Layout (DXF) …", self.win.import_dxf)])
        g.large("Werkzeuge", "tools", menu=[("Netz vereinfachen …", self.win.simplify_selected),
                                           ("Spiegeln (X)", lambda: self.mirror(0)), ("Spiegeln (Y)", lambda: self.mirror(1)),
                                           ("Maße auf Raster runden", self.round_to_grid)])
        g = p.group("Verhaltensweise")
        g.large("Verhalten", "behavior", menu=[("Förderband", lambda: self.behavior("conveyor")),
                                              ("Lichtschranke / Sensor", lambda: self.behavior("sensor")),
                                              ("Farbsensor", lambda: self.behavior("color_sensor")),
                                              ("Teile-Erzeuger", lambda: self.behavior("spawner")),
                                              ("Senke", lambda: self.behavior("sink")),
                                              ("Signalleuchte / Farbanzeige", lambda: self.behavior("lamp")), None,
                                              ("Greifbar an/aus", lambda: self.flag("graspable")),
                                              ("Hindernis an/aus", lambda: self.flag("obstacle"))])
        g = p.group("Assistenten")
        g.large("Assistenten", "assistant", menu=[("Förderstrecke …", self.wizard_conveyor_line),
                                                 ("Schutzzaun um Zelle", self.wizard_fence),
                                                 ("Palette mit Teilen …", self.wizard_pallet)])
        self.g_origin(p)

    # ------------------------------------------------------------------ PROGRAMM
    def _program(self):
        p = self.rb.add_tab("PROGRAMM")
        g = p.group("Steuerung")
        g.large("Start", "play", self.win.run_prog, tip="F5")
        g.small("Schritt", "step", self.win.step_prog, tip="F10")
        g.small("Pause", "pause", lambda: self.sim.pause_all())
        g.small("Stop 0", "stop", lambda: self.sim.stop_all())
        g.column()
        g.small("Reset", "reset", self.win.reset_all)
        g = p.group('Prüfen und Debuggen')
        g.large('Produktions-\ncockpit', 'analysis', self.win.open_cockpit, tip='Zelle, Signale und Leistung prüfen')
        g.small('Debugger', 'step', self.win.open_debugger)
        g.small('Haltepunkt', 'stop', lambda: self.win.editor.toggle(), tip='F9')
        g = p.group("Komponente")
        g.small("Import", "import", self.win.import_vcmx)
        g.small("An Roboterflansch", "robot", self.attach_flange, tip="Auswahl an den Flansch des aktiven Roboters fügen")
        g = p.group("Roboter")
        self.mode_btn(g, "Jog", "jog", "jog", tip="Roboter am Werkzeugpunkt ziehen")
        g.small("Robot World Frame verschieben", "robot_frame", self.robot_world_frame)
        g.small("Roboter austauschen", "robot_swap", self.swap_robot)
        g.small("Punkt einlernen", "add", self.win.teach_point)
        g = p.group("Anzeigen")
        g.check("Traces", self.v.show_trail, lambda c: (setattr(self.v, "show_trail", c), setattr(self.v, "show_traces", c), self.v.update()))
        g.check("Überlagerungsmenü lehren", False, self.teach_overlay)
        g.small("Simulationskonfiguration", "sim_config", self.sim_config)
        g = p.group("Kollisionsprüfung")
        g.small("Kollisionserkennung bearbeiten", "collision", self.collision_edit)
        g.check("Kollisionserkennung aktivieren", getattr(self.sim, "collision_enabled", True),
                lambda c: setattr(self.sim, "collision_enabled", c))
        g.check("Stopp bei Kollision", getattr(self.sim, "stop_on_collision", True), self._stop_on_collision)
        g = p.group("Position fixieren")
        self.fix_mode = "reference"
        g.radio("Zur Referenz", "fix", True, lambda: setattr(self, "fix_mode", "reference"),
                tip="Robot World Frame verschieben: angehängte Objekte wandern mit")
        g.radio("Zur Welt", "fix", False, lambda: setattr(self, "fix_mode", "world"),
                tip="Robot World Frame verschieben: Objekte bleiben in der Welt stehen")
        g = p.group("Limits")
        g.check("Achslimits farbig anzeigen", False, lambda c: (setattr(self.sim, "show_limit_colors", c), self.v.update()))
        g.check("Bei Achslimits anhalten", False, lambda c: setattr(self.sim, "stop_at_limits", c))
        g.check("Ausgabe Meldungs-Panel", False, lambda c: setattr(self.sim, "limit_messages", c))
        g = p.group("Trace")
        g.small("Analyse", "analysis", self.trace_stats)
        g.small("Diagramm", "chart", self.trace_chart)
        self.rec_btn = g.small("Online-Aufzeichnung", "record", self.trace_toggle, checkable=True)
        g = p.group("Prozesse")
        g.small("Bahnprozess …", "process", lambda: self.win.process_dialog("bahn"))
        g.small("Punktprozess …", "process", lambda: self.win.process_dialog("punkt"))
        g.small("Flächenprozess …", "process", lambda: self.win.process_dialog("flaeche"))

    # ------------------------------------------------------------------ KONFIGURATION
    def _config(self):
        p = self.rb.add_tab("KONFIGURATION")
        g = p.group("Roboter")
        g.small("Hinzufügen", "add", lambda: self.win.add_robot())
        g.small("Kopieren", "copy", self.robot_copy)
        g.small("Einfügen", "paste", self.robot_paste)
        g.column()
        g.small("Löschen", "delete", self.win.remove_robot)
        g = p.group("E/A")
        g.large("E/A\nVerschaltungseditor", "io", self.signals)
        g.large("Verschaltungs-\nübersicht", "io_overview", self.io_overview)
        g.large("Geräte-\nkatalog", "device_catalog", self.device_catalog)
        g.large("Automatisches\nRouting", "routing", self.auto_routing, tip="Sensoren ohne Signal freie Eingänge zuweisen")
        g = p.group("Antriebe")
        g.large("Antriebs-\nkonfiguration", "drive", self.drive_config)
        g.large("Konfigurations-\nvorschlag", "drive_suggest", self.config_suggest)
        g = p.group("Maschinendaten")
        g.large("Maschinendaten\nEditor", "machine_data", self.win.open_robot_editor)
        g.small("Maschinendaten exportieren", "rcs", self.rcs_export)
        g = p.group("Konfiguration")
        g.large("Steuerungspaket\nexportieren", "transfer", self.transfer,
                tip="Programme, Konfiguration, Punkte und E/A-Namen je Roboter in einen Ordner schreiben")
        g.small("Aktuelle Konfiguration beibehalten", "keep", self.keep_config)
        g.small("Projekt zusammenführen", "merge", self.merge_project)
        g = p.group("Netzwerk")
        g.large("Grundlegende\nNetzwerkkonfiguration", "network", lambda: self.focus_bottom("Konnektivität"))
        g = p.group("Langtexte")
        g.large("Langtext-Editor", "longtext", self.longtext)

    # ------------------------------------------------------------------ ANSICHT
    def _view(self):
        p = self.rb.add_tab("ANSICHT")
        g = p.group("Kamera")
        for n, k, ic in (("Isometrisch", "iso", "view_iso"), ("Vorne", "front", "layout"), ("Seite", "side", "layout"), ("Oben", "top", "layout")):
            g.small(n, ic, lambda k=k: self.v.view(k))
        g = p.group("Darstellung")
        for txt, attr in (("Helle Hallenansicht", "light_mode"), ("Schatten", "shadows"), ("TCP-Spur", "show_trail"),
                          ("Koordinatensysteme", "show_frames"), ("Erreichbarkeits-Wolke", "show_reach"),
                          ("Swept Volume", "show_swept"), ("Bemaßungen", "show_dims"), ("Kollisionskörper", "show_caps")):
            g.check(txt, getattr(self.v, attr, False), lambda c, a=attr: self._view_flag(a, c))
        g = p.group("Fenster")
        for d, n in ((self.win.dock_l, "Aufbau"), (self.win.dock_r, "Bedienung"), (self.win.dock_b, "Werkzeuge")):
            g.check(n, True, lambda c, d=d: d.setVisible(c))
        g.small("Anordnung zurücksetzen", "layout", self.win.reset_layout)
        g = p.group("Aufnahme")
        g.small("Video aufnehmen/stoppen", "record", self.win.toggle_record, tip="Strg+R")
        g.small("3D-Präsentation (HTML)", "export", self.win.export_html)
        g.small("Screenshot", "image", self.win.save_screenshot)

    def _view_flag(self, attr, on):
        setattr(self.v, attr, on)
        if attr == "light_mode":                       # Hallenansicht merken
            self.win.settings["light_mode"] = bool(on)
            from main import save_settings
            save_settings(self.win.settings)
        self.v.update()

    # ------------------------------------------------------------------ HILFE
    def _help(self):
        import dialogs
        p = self.rb.add_tab("HILFE")
        g = p.group("Hilfe und Referenz")
        g.large("Hilfe", "help", lambda: dialogs.help_dialog(self.win), tip="F1 · Erste Schritte, Tastenkürzel, Tipps, Fehlerbehebung")
        g.small("Python-API", "api", lambda: dialogs.help_dialog(self.win, "python"))
        g.small("OPC-UA-API", "api", lambda: dialogs.help_dialog(self.win, "opcua"))
        g.small("XRL-Referenz", "api", lambda: dialogs.help_dialog(self.win, "xrl"))
        g = p.group("Suche")
        s = QLineEdit()
        s.setPlaceholderText("In der Hilfe suchen …")
        s.setFixedWidth(180)
        s.returnPressed.connect(lambda: dialogs.help_dialog(self.win, s.text()))
        g.widget(s)
        g = p.group("Fehlerbericht")
        g.large("Fehlerbericht\nerstellen", "bug", lambda: dialogs.bug_report(self.win))
        g = p.group("Scripting")
        g.small("Neues VS-Code-Projekt", "vscode", lambda: dialogs.vscode_project(self.win, new=True))
        g.small("VS-Code-Projekt öffnen", "vscode", lambda: dialogs.vscode_project(self.win, new=False))
        g = p.group("Assistent")
        g.large("Geführter\nArbeitsablauf", "workflow", lambda: dialogs.guided_workflow(self.win))
        g = p.group("Programm")
        g.small("Nach Updates suchen", "update", lambda: self.win.check_updates(False))
        g.small("Vorherige Version", "reset", self.win.do_rollback)
        g.small("Über Ximaj RoboSim", "info", self.win.about)

    # ------------------------------------------------------------------ DATEI (Backstage)
    def _backstage(self):
        b, w = self.bs, self.win
        b.item("Neu", "new", w.new_project)
        b.item("Öffnen …", "open", w.open_project)
        b.item("Speichern", "save", w.save_project)
        b.item("Speichern unter …", "save_as", lambda: w.save_project(True))
        b.item("Importieren (.vcmx/.vcm) …", "import", w.import_vcmx)
        b.item("CAD importieren …", "geometry", w.import_cad)
        b.item("Programm importieren …", "import", w.import_program)
        b.item("Programm exportieren …", "export", w.export_program)
        b.item("Konfiguration exportieren …", "export", w.export_config)
        b.item("Konfiguration importieren …", "import", w.import_config)
        b.spacer()
        b.item("Updates", "update", lambda: w.check_updates(False))
        b.item("Über", "info", w.about)
        b.item("Beenden", "exit", w.close)
        b.closed.connect(lambda: self.v.setFocus())
        self.rb.file_clicked.connect(self._fill_backstage)

    def _fill_backstage(self):
        from version import VERSION
        w = QWidget()
        l = QVBoxLayout(w)
        t = QLabel("Zuletzt verwendet")
        t.setObjectName("bs_title")
        l.addWidget(t)
        lst = QListWidget()
        for path in self.win.settings.get("recent", [])[:15]:
            it = QListWidgetItem(icon("open", 20), f"{os.path.basename(path)}\n{path}")
            it.setData(Qt.ItemDataRole.UserRole, path)
            lst.addItem(it)
        if lst.count() == 0:
            lst.addItem("Noch keine Projekte geöffnet.")
        lst.itemActivated.connect(lambda it: it.data(Qt.ItemDataRole.UserRole) and (self.bs.hide_stage(),
                                                                                    self.win.open_project(it.data(Qt.ItemDataRole.UserRole))))
        l.addWidget(lst, 1)
        info = QLabel(f"{theme.BRAND['product']} {VERSION} · {theme.BRAND['company']}\n"
                      f"Projekt: {self.win.project_path or 'nicht gespeichert'} · "
                      f"{len(self.sim.robots)} Roboter · {len(self.sim.scene)} Objekte")
        info.setObjectName("muted")
        l.addWidget(info)
        self.bs.set_body(w)

    def update_history(self):
        history = self.win.history
        for control in (self.undo_button, self.undo_action):
            control.setEnabled(history.can_undo)
        for control in (self.redo_button, self.redo_action):
            control.setEnabled(history.can_redo)

    def _shortcuts(self):
        w = self.win
        for key, fn, attr in (('Ctrl+Z', w.undo, 'undo_action'), ('Ctrl+Y', w.redo, 'redo_action')):
            action = QAction(w)
            action.setShortcut(QKeySequence(key))
            action.triggered.connect(fn)
            w.addAction(action)
            setattr(self, attr, action)
        for key, fn in (("Ctrl+N", w.new_project), ("Ctrl+O", w.open_project), ("Ctrl+S", w.save_project),
                        ("Ctrl+I", w.import_vcmx), ("Ctrl+R", w.toggle_record), ("Ctrl+Q", w.close),
                        ("Ctrl+C", self.copy), ("Ctrl+V", self.paste), ("Ctrl+G", self.group),
                        ("Ctrl+Shift+G", self.ungroup), ("Ctrl+F1", self.rb.toggle_collapsed),
                        ("F1", lambda: __import__("dialogs").help_dialog(w)), ("Ctrl+A", self.select_all),
                        ("M", lambda: self.set_mode("move")), ("Esc", lambda: self.set_mode("select"))):
            a = QAction(w)
            a.setShortcut(QKeySequence(key))
            a.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
            a.triggered.connect(lambda _=False, f=fn: f())
            w.addAction(a)
        a = QAction(w)
        a.setShortcut(QKeySequence(Qt.Key.Key_Delete))
        a.triggered.connect(lambda: self.v.hasFocus() and self.delete())
        w.addAction(a)

    # ------------------------------------------------------------------ Bearbeiten
    def copy(self):
        s = self.sels()
        if s:
            self.clipboard = self.safe(self._ed().copy, self.sim, s) or []
            self.msg(f"{len(s)} Objekt(e) kopiert")

    @tracked
    def paste(self):
        if not self.clipboard:
            return
        new = self.safe(self._ed().paste, self.sim, self.clipboard) or []
        self.v.selection = list(new)
        self.v.selected = new[0] if new else None
        self.refresh()
        self.msg(f"{len(new)} Objekt(e) eingefügt")

    @tracked
    def delete(self):
        s = self.sels()
        if not s:
            return
        self.safe(self._ed().delete, self.sim, s)
        self.v.selected, self.v.selection = None, []
        self.refresh()
        self.msg(f"{len(s)} Objekt(e) gelöscht")

    @tracked
    def group(self):
        s = self.sels()
        if len(s) < 2:
            self.msg("Zum Gruppieren mindestens zwei Objekte wählen (Strg+Klick oder Umschalt+Rahmen)")
            return
        g = self.safe(self._ed().group, self.sim, s)
        if g is not None:
            self.v.selected, self.v.selection = g, [g]
            self.refresh()
            self.msg(f"Gruppe „{g.name}“ erstellt")

    @tracked
    def ungroup(self):
        o = self.sel()
        if o is None or o.kind != "group":
            self.msg("Bitte eine Gruppe auswählen")
            return
        kids = self.safe(self._ed().ungroup, self.sim, o) or []
        self.v.selected, self.v.selection = None, list(kids)
        self.refresh()

    def select_all(self):
        self.v.selection = [o for o in self.sim.scene if o.visible]
        self.v.selected = self.v.selection[0] if self.v.selection else None
        self.v.update()

    def select_none(self):
        self.v.selection, self.v.selected = [], None
        self.v.update()

    def select_same(self):
        o = self.sel()
        if o:
            self.v.selection = [x for x in self.sim.scene if x.kind == o.kind]
            self.v.update()

    def select_invert(self):
        cur = set(map(id, self.sels()))
        self.v.selection = [o for o in self.sim.scene if id(o) not in cur and o.visible]
        self.v.selected = self.v.selection[0] if self.v.selection else None
        self.v.update()

    def clear_dims(self):
        self.sim.dimensions = []
        self.v.measure_result = None
        self.v.update()

    def _move_mode(self, children):
        self.v.move_children = children
        b1, b2 = self._mm
        for b, on in ((b1, children), (b2, not children)):
            b.blockSignals(True)
            b.setChecked(on)
            b.blockSignals(False)

    @tracked
    def _on_moved(self, o):
        if o is self.win.sel():
            self.win.on_select_row(self.win.obj_list.currentRow())

    @tracked
    def _on_target(self, mode, target):
        s = [o for o in self.sels() if o is not target]
        if not s:
            self.msg("Zuerst ein Objekt auswählen, dann das Ziel anklicken")
            return
        ed = self._ed()
        for o in s:
            if mode == "snap":
                self.safe(ed.snap, self.sim, o, target)
            elif mode == "align":
                self.safe(ed.align, self.sim, o, target, "rotation")
            elif mode == "attach":
                self.safe(ed.attach, self.sim, o, target.name)
        self.msg({"snap": "Angedockt an", "align": "Ausgerichtet an", "attach": "Gefügt an"}[mode] + f" „{target.name}“")
        self.set_mode("select")
        self.refresh()

    @tracked
    def detach(self):
        for o in self.sels():
            self.safe(self._ed().detach, self.sim, o)
        self.refresh()
        self.msg("Abgelöst")

    @tracked
    def attach_flange(self):
        r = self.sim.active
        for o in self.sels():
            self.safe(self._ed().attach, self.sim, o, f"{r.name}@flange")
        self.msg(f"An den Flansch von „{r.name}“ gefügt")
        self.refresh()

    def export_selection(self, fmt):
        import trimesh
        s = self.sels() or list(self.sim.scene)
        p, _ = QFileDialog.getSaveFileName(self.win, "STL exportieren", "auswahl.stl", "STL (*.stl)")
        if not p:
            return
        try:
            from cad import scene_to_trimesh
            m = scene_to_trimesh(s)
        except Exception:
            parts = []
            for o in s:
                b = trimesh.creation.box(extents=o.size)
                b.apply_translation([0, 0, o.size[2] / 2])
                b.apply_transform(o.matrix())
                parts.append(b)
            m = trimesh.util.concatenate(parts)
        m.export(p)
        self.msg(f"STL gespeichert: {p}")

    @tracked
    def _on_interact(self, o):
        if o is None:
            return
        if o.kind in ("conveyor", "conveyor_arc"):
            o.stopped = not getattr(o, "stopped", False)
            if o.io:
                self.sim.io.set_out(int(o.io), not o.stopped)
            self.msg(f"{o.name}: {'angehalten' if o.stopped else 'läuft'}")
        elif o.kind == "spawner":
            o.timer = max(o.interval, getattr(o, "timer", 0))
            if getattr(o, "trigger", 0):
                self.sim.io.set_out(int(o.trigger), not self.sim.io.get_out(int(o.trigger)))
            self.msg(f"{o.name}: Teil angefordert")
        elif o.kind in ("sensor", "color_sensor") and o.io:
            self.sim.io.set_in(int(o.io), not self.sim.io.get_in(int(o.io)))
            self.msg(f"{o.name}: Signal $IN[{o.io}] umgeschaltet")
        else:
            self.msg(f"{o.name}: keine Interaktion")
        self.v.update()

    # ------------------------------------------------------------------ Modellierung
    def component_save(self, ask=False):
        import dialogs
        dialogs.save_component(self.win, self.sels(), ask)

    def show_structure(self):
        import dialogs
        dialogs.structure(self.win)

    @tracked
    def feature(self, kind):
        from sim import SceneObj
        c = self.v.center
        size = {"box": [400, 400, 400], "cylinder": [300, 300, 400], "workpiece": [100, 80, 60], "zone": [1000, 1000, 1000]}[kind]
        o = SceneObj(f"{ {'box': 'Quader', 'cylinder': 'Zylinder', 'workpiece': 'Teil', 'zone': 'Zone'}[kind]} {len(self.sim.scene) + 1}",
                     kind, [float(c[0]), float(c[1]), 0.0], [0, 0, 0], size,
                     {"box": "#9aa5b1", "cylinder": "#9aa5b1", "workpiece": "#f5b83d", "zone": "#ef4444"}[kind],
                     kind in ("box", "cylinder"), kind == "workpiece")
        if kind == "zone":
            o.alpha = 0.25
        self.sim.scene.append(o)
        self.v.selected, self.v.selection = o, [o]
        self.refresh()
        self.set_mode("move")

    @tracked
    def mirror(self, axis):
        for o in self.sels():
            self._as_mesh(o)
            if o.kind == "mesh" and o.mesh is not None:
                V, F = o.mesh
                V = V.copy()
                V[:, axis] *= -1
                o.mesh = (V, F[:, ::-1].copy())
                o._glcache = None
                o.mesh_mirror = list(getattr(o, "mesh_mirror", None) or []) + [axis]
                off = list(getattr(o, "mesh_offset", None) or [0.0, 0.0, 0.0])
                off[axis] = -off[axis]                       # damit Speichern/Laden dieselbe Geometrie ergibt
                o.mesh_offset = off
            else:
                self.msg(f"„{o.name}“ ({o.kind}) kann nicht gespiegelt werden")
        self.v.update()

    @tracked
    def round_to_grid(self):
        st = self.v.snap_step
        for o in self.sels():
            o.pos = [round(v / st) * st if i < 2 else v for i, v in enumerate(o.pos)]
        self.refresh()

    @tracked
    def behavior(self, kind):
        for o in self.sels():
            o.kind = kind
            if kind in ("sensor", "color_sensor", "spawner", "sink", "lamp"):
                o.obstacle = False
            if kind == "color_sensor" and not getattr(o, "color_outs", None):
                o.color_outs = {"ROT": 2, "GRUEN": 3, "BLAU": 4, "GELB": 5, "WEISS": 6}
                o.detected = 7
            if kind == "lamp" and not getattr(o, "inputs", None):
                o.inputs = {"ROT": 2, "GRUEN": 3, "BLAU": 4, "GELB": 5, "WEISS": 6}
        self.refresh()
        self.msg(f"Verhalten gesetzt: {kind}")

    @tracked
    def flag(self, attr):
        for o in self.sels():
            setattr(o, attr, not getattr(o, attr))
            self.msg(f"{o.name}: {attr} = {getattr(o, attr)}")
        self.refresh()

    @tracked
    def wizard_conveyor_line(self):
        import dialogs
        dialogs.conveyor_line(self.win)

    @tracked
    def wizard_fence(self):
        import dialogs
        dialogs.fence_around(self.win)

    @tracked
    def wizard_pallet(self):
        import dialogs
        dialogs.pallet(self.win)

    @tracked
    def origin_place(self):
        o = self.sel()
        if o is None:
            self.msg("Bitte ein Objekt wählen")
            return
        items = ["Boden-Mitte", "Mitte", "Oben-Mitte"]
        it, ok = QInputDialog.getItem(self.win, "Ursprung positionieren", f"Ursprung von „{o.name}“ legen auf:", items, 0, False)
        if ok:
            self._as_mesh(o)
            r = self.safe(self._ed().set_origin, self.sim, o, {"Boden-Mitte": "bottom_center", "Mitte": "center",
                                                               "Oben-Mitte": "top_center"}[it])
            self.msg(r if isinstance(r, str) else f"Ursprung von „{o.name}“: {it}")
            self.refresh()

    def _as_mesh(self, o):
        """Quader/Zylinder fuer einen frei waehlbaren Ursprung in ein formgleiches Netz umwandeln"""
        if o.kind not in ("box", "cylinder"):
            return
        from sim import prim_mesh
        o.mesh = prim_mesh(o.kind, o.size)                    # wie bisher: Ursprung unten in der Mitte
        o.prim, o.kind = o.kind, "mesh"
        o.mesh_offset = [0.0, 0.0, 0.0]
        o._glcache = None
        self.msg(f"„{o.name}“ wurde für den freien Ursprung in ein Netz umgewandelt")

    @tracked
    def origin_move(self):
        o = self.sel()
        if o is None:
            self.msg("Bitte ein Objekt wählen")
            return
        txt, ok = QInputDialog.getText(self.win, "Ursprung verschieben", "Versatz X Y Z in mm (Geometrie bleibt stehen):", text="0 0 0")
        if ok:
            try:
                d = [float(v) for v in txt.replace(",", " ").split()][:3]
                self._as_mesh(o)
                r = self.safe(self._ed().set_origin, self.sim, o, tuple(d))
                self.msg(r if isinstance(r, str) else "Ursprung verschoben")
            except ValueError:
                self.msg("Bitte drei Zahlen eingeben")
            self.refresh()

    # ------------------------------------------------------------------ Programm
    @tracked
    def robot_world_frame(self):
        import dialogs
        dialogs.robot_world_frame(self.win, self.fix_mode)

    @tracked
    def swap_robot(self):
        from kinematics import MODELS
        r = self.sim.active
        it, ok = QInputDialog.getItem(self.win, "Roboter austauschen", f"Neues Modell für „{r.name}“:", list(MODELS),
                                      list(MODELS).index(r.model_key) if r.model_key in MODELS else 0, False)
        if ok:
            self.safe(self._ed().swap_robot, self.sim, r, it)
            self.win.sync_from_sim()
            self.v.update()
            self.msg(f"Roboter ausgetauscht: {it}")

    def teach_overlay(self, on):
        import dialogs
        dialogs.teach_overlay(self.win, on)

    @tracked
    def sim_config(self):
        import dialogs
        dialogs.sim_config(self.win)

    @tracked
    def collision_edit(self):
        import dialogs
        dialogs.collision_config(self.win)

    @tracked
    def _stop_on_collision(self, c):
        self.sim.stop_on_collision = c
        if hasattr(self.win, "col_stop"):
            self.win.col_stop.setChecked(c)

    def _recorder(self):
        rec = getattr(self.sim, "recorder", None)
        if rec is None:
            import sim_trace
            rec = self.sim.recorder = sim_trace.Recorder(self.sim)
        return rec

    def trace_toggle(self, on):
        rec = self._recorder()
        if on:
            rec.clear()
            rec.start()
            self.msg("Online-Aufzeichnung gestartet")
        else:
            rec.stop()
            self.msg("Online-Aufzeichnung gestoppt")

    def trace_stats(self):
        import dialogs
        dialogs.trace_stats(self.win, self._recorder())

    def trace_chart(self):
        import dialogs
        dialogs.trace_chart(self.win, self._recorder())

    # ------------------------------------------------------------------ Konfiguration
    def robot_copy(self):
        self._robot_clip = self.sim.active.to_dict()
        self.msg(f"Roboter „{self.sim.active.name}“ kopiert")

    @tracked
    def robot_paste(self):
        d = getattr(self, "_robot_clip", None)
        if not d:
            return
        self.win.add_robot(d.get("model"))                 # neuer Roboter neben dem aktiven
        r = self.sim.active
        root, name = list(r.root_pose), r.name
        d = dict(d)
        d["name"] = name
        d["root"] = root
        r.from_dict(d)                                     # Werkzeug, Basis, Programm, Punkte uebernehmen
        r.set_root(root)
        self.win.editor.setPlainText(r.src)
        self.win.sync_from_sim()
        self.v.update()
        self.msg(f"Roboter eingefügt: {name}")

    @tracked
    def signals(self):
        import dialogs
        dialogs.signal_editor(self.win)

    @tracked
    def interfaces(self):
        import dialogs
        dialogs.interfaces(self.win)

    def io_overview(self):
        import dialogs
        dialogs.io_overview(self.win)

    @tracked
    def device_catalog(self):
        import dialogs
        dialogs.device_catalog(self.win)

    @tracked
    def auto_routing(self):
        import dialogs
        dialogs.auto_routing(self.win)

    @tracked
    def drive_config(self):
        import dialogs
        dialogs.drive_config(self.win)

    @tracked
    def config_suggest(self):
        import dialogs
        dialogs.config_suggest(self.win)

    def rcs_export(self):
        import dialogs
        dialogs.rcs_export(self.win)

    def transfer(self):
        import dialogs
        dialogs.transfer_to_controller(self.win)

    @tracked
    def keep_config(self):
        m = self.sim.active.model
        self.sim.imported_models[self.sim.active.model_key] = {
            "dims": [m.a1, m.d1, m.a2, m.a3, m.d4, m.d6], "limits": [list(map(float, l)) for l in m.limits],
            "vmax": [float(v) for v in m.vmax], "payload": float(m.payload or 0)}
        self.msg("Aktuelle Roboterkonfiguration wird im Projekt gespeichert")

    @tracked
    def merge_project(self):
        import dialogs
        dialogs.merge_project(self.win)

    @tracked
    def longtext(self):
        import dialogs
        dialogs.longtext_editor(self.win)

    # ------------------------------------------------------------------ Analyse / Allgemein
    def analysis_window(self):
        import dialogs
        dialogs.analysis_window(self.win)

    def _auto_analysis(self):
        if not self.analysis_on or self.sim.state in ("running", "wait"):
            return
        try:
            import analysis
            issues = analysis.analyze(self.sim)
        except Exception:
            return
        n = sum(1 for i in issues if i.get("level") in ("Fehler", "Warnung"))
        self.rb.pages["START"].groups["Projektanalyse"].items["Projektanalyse Fenster"].setText(
            f"Projektanalyse Fenster ({n})" if n else "Projektanalyse Fenster")
        if self.analysis_popup and n > self._last_issue_count:
            self.analysis_window()
        self._last_issue_count = n

    def focus_left(self, name):
        tabs = self.win.left_tabs
        for i in range(tabs.count()):
            if tabs.tabText(i).startswith(name):
                tabs.setCurrentIndex(i)
                self.win.dock_l.show()

    def focus_bottom(self, name):
        tabs = self.win.bottom
        for i in range(tabs.count()):
            if tabs.tabText(i).startswith(name):
                tabs.setCurrentIndex(i)
                self.win.dock_b.show()

    def camera_animator(self):
        import dialogs
        dialogs.camera_animator(self.win)
