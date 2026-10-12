"""Hauptfenster: mehrere Roboter, Linearachse E1, gemeinsamer Start, Durchsatz, Katalog 'weiterer Roboter'."""
import os
B = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "ximaj_robosim")


def patch(fn, pairs):
    p = os.path.join(B, fn)
    m = open(p, encoding="utf8").read()
    for a, b in pairs:
        if a not in m:
            raise SystemExit(f"{fn}: NICHT GEFUNDEN:\n{a[:300]}")
        m = m.replace(a, b, 1)
    open(p, "w", encoding="utf8").write(m)


patch("main.py", [
    # --- Roboter-Reiter: Liste + Linearachse
    ('''    def _robot_tab(self):
        w = QWidget()
        l = QVBoxLayout(w)
        g = QGroupBox("Robotermodell")''', '''    def _robot_tab(self):
        w = QWidget()
        l = QVBoxLayout(w)
        g0 = QGroupBox("Roboter in der Zelle")
        v0 = QVBoxLayout(g0)
        self.rob_list = QListWidget()
        self.rob_list.setMaximumHeight(110)
        self.rob_list.currentRowChanged.connect(self.switch_robot)
        v0.addWidget(self.rob_list)
        self.rob_name = QLineEdit()
        self.rob_name.setPlaceholderText("Name des Roboters")
        self.rob_name.editingFinished.connect(self.rename_robot)
        v0.addWidget(self.rob_name)
        v0.addWidget(row(self._btn("＋ Roboter hinzufügen", lambda: self.add_robot()),
                         self._btn("Entfernen", self.remove_robot)))
        l.addWidget(g0)
        g = QGroupBox("Robotermodell")'''),
    ('''        f2.addRow("Werkzeugradius", self.tool_rad)
        l.addWidget(g2)
        l.addStretch(1)
        self.update_model_info()
        return w''', '''        f2.addRow("Werkzeugradius", self.tool_rad)
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

    def switch_robot(self, idx):
        if idx < 0 or idx == self.sim.active_idx:
            return
        self.sim.active.src = self.editor.toPlainText()
        self.sim.set_active(idx)
        self.editor.setPlainText(self.sim.active.src)
        self.sync_from_sim()
        self.log_msg(f"Aktiver Roboter: {self.sim.active.name}")

    def add_robot(self, model_key=None):
        self.sim.active.src = self.editor.toPlainText()
        a = self.sim.active
        off = a.root_pose[:]
        off[1] += max(1500.0, a.model.reach * 1.6)
        r = self.sim.add_robot(model_key, off)
        self.editor.setPlainText(r.src)
        self.sync_from_sim()
        self.log_msg(f"{r.name} hinzugefügt")

    def remove_robot(self):
        if len(self.sim.robots) < 2:
            QMessageBox.information(self, "Roboter", "Die Zelle braucht mindestens einen Roboter.")
            return
        self.sim.remove_robot(self.sim.active_idx)
        self.editor.setPlainText(self.sim.active.src)
        self.sync_from_sim()

    def rename_robot(self):
        n = self.rob_name.text().strip()
        if n:
            self.sim.active.name = n
            self.fill_robot_list()

    def apply_track(self):
        if getattr(self, "_loading_track", False):
            return
        if self.trk_on.isChecked():
            self.sim.active.set_track(e_min=self.trk_min.value(), e_max=self.trk_max.value(), vmax=self.trk_v.value())
        else:
            self.sim.active.set_track(None)
        self.fill_robot_list()
        self.viewer.update()

    def fill_track(self):
        self._loading_track = True
        r = self.sim.active
        self.trk_on.setChecked(r.track is not None)
        if r.track is not None:
            lo, hi = r.e_limits()
            self.trk_min.setValue(lo)
            self.trk_max.setValue(hi)
            self.trk_v.setValue(r.track.get("vmax", 1500.0))
        self._loading_track = False'''),
    ('''        self.update_model_info()
        self.refresh_scene_list()
        self.fill_zones()
        self.fill_points()
        self.viewer.update()''', '''        self.update_model_info()
        self.refresh_scene_list()
        self.fill_zones()
        self.fill_points()
        self.fill_robot_list()
        self.fill_track()
        self.viewer.update()'''),
    # --- E1 im Tippbetrieb
    ('''        l.addWidget(row(self._btn("Home", self.go_home), self._btn("Mastering (alle 0)", lambda: self.set_q(np.zeros(6)))))''',
     '''        ge = QGroupBox("Linearachse")
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
        l.addWidget(row(self._btn("Home", self.go_home), self._btn("Mastering (alle 0)", lambda: self.set_q(np.zeros(6)))))'''),
    ('''        kind, i, s = self.jog
        sp = self.jog_speed.value() / 100.0
        m = self.sim.model''', '''        kind, i, s = self.jog
        sp = self.jog_speed.value() / 100.0
        m = self.sim.model
        if kind == "e":
            r = self.sim.active
            if r.track is not None:
                lo, hi = r.e_limits()
                r.e1 = float(np.clip(r.e1 + s * r.track["vmax"] * 0.5 * sp * dt, lo, hi))
                r.update_sv()
            return'''),
    # --- Programmsteuerung fuer alle Roboter
    ('''    def run_prog(self):
        if self.sim.state in ("idle", "error", "stopped"):
            self.sim.load_program(self.editor.toPlainText())
            self.sim.start(False)
        elif self.sim.state == "paused":
            self.sim.resume(False)''', '''    def run_prog(self):
        """Start: alle Roboter mit ihren Programmen gleichzeitig (pausierte werden fortgesetzt)."""
        self.sim.active.src = self.editor.toPlainText()
        if any(r.state == "paused" for r in self.sim.robots):
            for r in self.sim.robots:
                if r.state == "paused":
                    r.resume(False)
            return
        if not self.sim.any_busy():
            for r in self.sim.robots:
                r.load_program(r.src)
            self.sim.start_all(False)'''),
    ('''    def reset_all(self):
        self.sim.reset()
        for o in list(self.sim.scene):
            if o.attached:
                o.attached = False''', '''    def reset_all(self):
        for r in self.sim.robots:
            r.reset()
            r.collision = None
        for o in list(self.sim.scene):
            if o.attached:
                o.attached = False
                o.attached_to = None'''),
    ('''        self.sim.tick(dt) if self.sim.state in ("running", "wait", "stopping") else self.sim._update_world(dt)''',
     '''        self.sim.tick(dt) if self.sim.any_busy() else self.sim._update_world(dt)'''),
    ('''        btn("⏸ Pause", self.sim.pause)
        btn("■ Stop 0", lambda: self.sim.stop(0), "danger", "STOP 0 - sofort anhalten mit maximaler Verzögerung")''',
     '''        btn("⏸ Pause", lambda: self.sim.pause_all())
        btn("■ Stop 0", lambda: self.sim.stop_all(), "danger", "STOP 0 – alle Roboter sofort anhalten (maximale Verzögerung)")'''),
    # --- Anzeige
    ('''        self.a_col.setText(s.collision or "keine")''', '''        self.a_col.setText(s.collision or "keine")
        tp = s.throughput()
        self.a_tp.setText(f"{tp['fertig']} fertig · {tp['erzeugt']} erzeugt · {tp['im_umlauf']} im Umlauf · "
                          f"{tp['pro_stunde']:.0f} Teile/h")
        r = s.active
        self.e1_lbl.setText(f"E1 = {r.e1:.1f} mm" if r.track is not None else "keine Linearachse")
        if len(s.robots) > 1:
            busy = sum(1 for x in s.robots if x.busy())
            self.state_l.setText(self.state_l.text() + f"  ·  {busy}/{len(s.robots)} Roboter aktiv")'''),
    ('''        f.addRow("Kollision", self.a_col)''', '''        f.addRow("Kollision", self.a_col)
        self.a_tp = QLabel("-")
        self.a_tp.setWordWrap(True)
        f.addRow("Durchsatz (Materialfluss)", self.a_tp)'''),
    ('''    def new_project(self):
        self.sim.scene = default_scene()''', '''    def new_project(self):
        self.sim.clear_robots()
        self.sim.scene = default_scene()'''),
    # --- Katalog: Roboter zusaetzlich einsetzen
    ('''        l.addWidget(row(self._btn("Eigene Teile-Ordner öffnen", self.open_user_catalog),''',
     '''        self.cat_add_robot = self._btn("Als weiteren Roboter einsetzen", self.cat_add_as_robot)
        l.addWidget(self.cat_add_robot)
        l.addWidget(row(self._btn("Eigene Teile-Ordner öffnen", self.open_user_catalog),'''),
    ('''    def cat_selected(self):
        e = self.cat_entry()''', '''    def cat_add_as_robot(self):
        e = self.cat_entry()
        if e and e["kind"] == "robot":
            self.add_robot(e["data"])

    def cat_selected(self):
        e = self.cat_entry()
        self.cat_add_robot.setVisible(bool(e and e["kind"] == "robot"))'''),
])

# Katalog: Senke + Linearachse
patch("catalog.py", [
    ('''E("Fördertechnik", "Lichtschranke / Endlagensensor"''', '''E("Fördertechnik", "Senke (Teile-Abnahme)", "Entfernt ankommende Teile und zählt den Durchsatz", "obj",
  [O("Senke", "sink", (400, 400, 300), "#16a34a", obstacle=False)])
E("Roboter", "Linearachse 4 m (für aktiven Roboter)", "Roboter fährt auf einer 4-m-Bodenschiene (E1)", "track",
  {"min": 0, "max": 4000, "vmax": 1500})
E("Roboter", "Linearachse 8 m (für aktiven Roboter)", "Roboter fährt auf einer 8-m-Bodenschiene (E1)", "track",
  {"min": 0, "max": 8000, "vmax": 2000})
E("Fördertechnik", "Lichtschranke / Endlagensensor"'''),
    ('''    if k == "tool":''', '''    if k == "track":
        t = entry["data"]
        sim.set_track(e_min=t["min"], e_max=t["max"], vmax=t.get("vmax", 1500))
        return "Linearachse"
    if k == "tool":'''),
])
print("ok")
