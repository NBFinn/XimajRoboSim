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
    ("import statements as stm\n", "import statements as stm\nimport processes as proc\n"),
    ('''        h = mb.addMenu("&Hilfe")''', '''        pm = mb.addMenu("&Prozesse")
        self._act(pm, "Bahnprozess (Schweißen, Kleben, Dichten) …", lambda: self.process_dialog("bahn"))
        self._act(pm, "Punktprozess (Punktschweißen, Inspektion) …", lambda: self.process_dialog("punkt"))
        self._act(pm, "Flächenprozess (Lackieren, Polieren, Entgraten) …", lambda: self.process_dialog("flaeche"))
        pm.addSeparator()
        self._act(pm, "Prozessvorschau ausblenden", lambda: (setattr(self.viewer, "proc_preview", None), self.viewer.update()))
        h = mb.addMenu("&Hilfe")'''),
    ('''    # ----- Statements (Bausteinprogrammierung)''', '''    # ----- Prozesse (Bahn / Punkt / Flaeche)
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
            rep.setPlainText("\\n".join(lines))
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

    # ----- Statements (Bausteinprogrammierung)'''),
])

patch("viewer.py", [
    ('''        self.light_mode = True          # helle Hallenansicht''', '''        self.proc_preview = None        # Prozessvorschau (Bahn/Punkte/Abdeckung)
        self.light_mode = True          # helle Hallenansicht'''),
    ('''        self._draw_safety()''', '''        self._draw_safety()
        if self.proc_preview:
            self._draw_process(self.proc_preview)'''),
    ('''    def _draw_trail(self):''', '''    def _draw_process(self, res):
        glDisable(GL_LIGHTING)
        # Abdeckung (Flaechenprozess)
        glDepthMask(GL_FALSE)
        for p0, p1, wdt in res.get("coverage", []):
            d = p1 - p0
            n = np.array([-d[1], d[0], 0.0])
            ln = np.linalg.norm(n)
            if ln < 1e-9:
                continue
            n = n / ln * wdt / 2
            glColor4f(0.95, 0.45, 0.1, 0.28)
            glBegin(GL_QUADS)
            for q in (p0 - n, p1 - n, p1 + n, p0 + n):
                glVertex3f(q[0], q[1], q[2] + 0.8)
            glEnd()
        glDepthMask(GL_TRUE)
        glLineWidth(3)
        for poly in res.get("preview", []):
            glColor4f(0.95, 0.4, 0.05, 1)
            glBegin(GL_LINE_STRIP if not res.get("points") else GL_POINTS)
            for p in poly:
                glVertex3f(*p)
            glEnd()
            glPointSize(9)
            glColor4f(0.1, 0.1, 0.1, 1)
            glBegin(GL_POINTS)
            for p in poly:
                glVertex3f(*p)
            glEnd()
        glEnable(GL_LIGHTING)

    def _draw_trail(self):'''),
])
print("ok")
