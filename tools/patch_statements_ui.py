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


patch("sim.py", [
    ('''        self.waypoints = []
        self.tool_table = {}
        self.base_table = {}
        self.pending_stop = None''', '''        self.waypoints = []
        self.statements = []                       # Statement-Programm (Bausteine)
        self.mode = "xrl"                          # "xrl" | "statements"
        self.stmt_linemap = {}
        self.tool_table = {}
        self.base_table = {}
        self.pending_stop = None'''),
    ('''            "program": self.src, "waypoints": self.waypoints, "tool_table": self.tool_table,''',
     '''            "program": self.src, "waypoints": self.waypoints, "tool_table": self.tool_table,
            "statements": self.statements, "mode": self.mode,'''),
    ('''        self.waypoints = d.get("waypoints", [])
        self.sv.update(d.get("sv", {}))
        self.reset()


# ------------------------------------------------------------------ Halle / Welt''', '''        self.waypoints = d.get("waypoints", [])
        self.statements = d.get("statements", [])
        self.mode = d.get("mode", "xrl")
        self.sv.update(d.get("sv", {}))
        self.reset()


# ------------------------------------------------------------------ Halle / Welt'''),
])

patch("main.py", [
    ("import catalog\n", "import catalog\nimport statements as stm\n"),
    ('''        bottom.addTab(self._editor_tab(), "Programm (XRL)")''', '''        bottom.addTab(self._statements_tab(), "Statements")
        bottom.addTab(self._editor_tab(), "Programm (XRL)")'''),
    ('''            self.bottom.setCurrentIndex(6)''', '''            self.bottom.setCurrentIndex(7)'''),
    ('''        c.insertText("\\n" + "  " + txt.rstrip("\\n"))
        self.bottom.setCurrentIndex(0)''', '''        c.insertText("\\n" + "  " + txt.rstrip("\\n"))
        self.bottom.setCurrentIndex(1)'''),
    # Start: Statement-Programme erzeugen
    ('''        if not self.sim.any_busy():
            for r in self.sim.robots:
                r.load_program(r.src)
            self.sim.start_all(False)''', '''        if not self.sim.any_busy():
            for r in self.sim.robots:
                if r.mode == "statements":
                    errs = stm.validate(r.statements)
                    if errs:
                        QMessageBox.warning(self, "Statements", f"{r.name}:\\n" + "\\n".join(errs))
                        return
                    r.src, r.stmt_linemap = stm.generate(r.statements, _ident(r.name))
                    if r is self.sim.active:
                        self.editor.setPlainText(r.src)
                r.load_program(r.src)
            self.sim.start_all(False)'''),
    ('''    # ----- Editor
    def _editor_tab(self):''', '''    # ----- Statements (Bausteinprogrammierung)
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

    def st_mode_changed(self, on):
        r = self.st_robot()
        if on and r.src.strip() and not r.statements:
            if QMessageBox.question(self, "Statements", "Auf Statement-Programmierung umstellen? Das bisherige "
                                    "XRL-Programm wird beim nächsten Start durch die Bausteine ersetzt.") \\
                    != QMessageBox.StandardButton.Yes:
                self.st_mode.blockSignals(True)
                self.st_mode.setChecked(False)
                self.st_mode.blockSignals(False)
                return
        r.mode = "statements" if on else "xrl"

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

    def st_delete(self):
        r = self.st_robot()
        i = self.st_list.currentRow()
        if 0 <= i < len(r.statements):
            del r.statements[i]
            self.fill_statements(min(i, len(r.statements) - 1))

    def st_move(self, d):
        r = self.st_robot()
        i = self.st_list.currentRow()
        j = i + d
        if 0 <= i < len(r.statements) and 0 <= j < len(r.statements):
            r.statements[i], r.statements[j] = r.statements[j], r.statements[i]
            self.fill_statements(j)

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
        q = r.model.ik(T, r.q, st) or None
        if q is None:
            q = r.model.ik(T, r.q)
        if q is None:
            self.log_msg("Position nicht erreichbar")
            return
        r.q = q
        r.update_sv()

    def st_generate(self):
        r = self.st_robot()
        errs = stm.validate(r.statements)
        if errs:
            QMessageBox.warning(self, "Statements", "\\n".join(errs))
            return
        r.src, r.stmt_linemap = stm.generate(r.statements, _ident(r.name))
        self.editor.setPlainText(r.src)
        self.bottom.setCurrentIndex(1)

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
    def _editor_tab(self):'''),
    # Statements bei Roboterwechsel/Sync und live markieren
    ('''        self.fill_robot_list()
        self.fill_track()
        self.viewer.update()''', '''        self.fill_robot_list()
        self.fill_track()
        self.fill_statements()
        self.viewer.update()'''),
    ('''        self.highlight_line()
        self.refresh_io()''', '''        self.highlight_line()
        self.st_highlight()
        self.refresh_io()'''),
    ('''def make_splash():''', '''def _ident(name):
    s = "".join(ch if ch.isalnum() else "_" for ch in name)
    return s if s and not s[0].isdigit() else "p_" + s


def make_splash():'''),
])
# QListWidgetItem importieren
p = os.path.join(B, "main.py")
m = open(p, encoding="utf8").read()
if "QListWidgetItem" not in m.split("from PyQt6.QtWidgets import", 1)[1].split(")", 1)[0]:
    m = m.replace("QPushButton, QListWidget, ", "QPushButton, QListWidget, QListWidgetItem, ", 1)
open(p, "w", encoding="utf8").write(m)
print("ok")
