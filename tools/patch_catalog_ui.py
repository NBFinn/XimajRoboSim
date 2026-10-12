import os
P = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "ximaj_robosim", "main.py")
m = open(P, encoding="utf8").read()


def rep(a, b):
    global m
    if a not in m:
        raise SystemExit("NICHT GEFUNDEN:\n" + a[:200])
    m = m.replace(a, b, 1)


rep("import xrl\n", "import xrl\nimport catalog\nimport vcmx_import\n")
rep('''        left = QTabWidget()
        left.addTab(self._scene_tab(), "Szene")''', '''        left = QTabWidget()
        left.addTab(self._catalog_tab(), "Katalog")
        left.addTab(self._scene_tab(), "Szene")''')
rep('''    # ----- Szene
    def _scene_tab(self):''', '''    # ----- Katalog
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

    def cat_selected(self):
        e = self.cat_entry()
        self.cat_desc.setText(f"<b>{e['name']}</b><br>{e['desc']}" if e else "")

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
        self.viewer.update()

    # ----- Szene
    def _scene_tab(self):''')
rep('''        self.sim.from_dict(json.load(open(p, encoding="utf8")))
        self.editor.setPlainText(self.sim.src)
        self.model_c.blockSignals(True)
        self.model_c.setCurrentText(self.sim.model_key)
        self.model_c.blockSignals(False)
        for s, v in zip(self.root_s, self.sim.root_pose):
            s.blockSignals(True); s.setValue(v); s.blockSignals(False)
        for s, v in zip(self.base_s, self.sim.base):
            s.blockSignals(True); s.setValue(v); s.blockSignals(False)
        for s, v in zip(self.tool_s, self.sim.tool.tcp):
            s.blockSignals(True); s.setValue(v); s.blockSignals(False)
        self.project_path = p
        self.update_model_info()
        self.refresh_scene_list()
        self.fill_zones()
        self.fill_points()''', '''        self.sim.from_dict(json.load(open(p, encoding="utf8")))
        self.editor.setPlainText(self.sim.src)
        self.project_path = p
        self.sync_from_sim()''')
rep('''        self._act(m, "Projekt speichern", self.save_project, "Ctrl+S")''', '''        self._act(m, "Projekt speichern", self.save_project, "Ctrl+S")
        self._act(m, "Altes Projekt importieren (.vcmx / .vcm) …", self.import_vcmx, "Ctrl+I")''')
rep('''    def import_program(self):''', '''    def import_vcmx(self):
        p, _ = QFileDialog.getOpenFileName(self, "Projekt/Modell importieren", "", "Layouts/Modelle (*.vcmx *.vcm)")
        if not p:
            return
        try:
            rep = vcmx_import.import_file(self.sim, p)
        except Exception as e:
            traceback.print_exc()
            QMessageBox.warning(self, "Import", f"Import fehlgeschlagen:\\n{e}")
            return
        self.sync_from_sim()
        if rep.get("main_program"):
            self.editor.setPlainText(rep["main_program"])
        self.show_import_report(rep)

    def show_import_report(self, rep):
        dlg = QDialog(self)
        dlg.setWindowTitle("Import-Bericht")
        dlg.resize(760, 560)
        l = QVBoxLayout(dlg)
        t = QPlainTextEdit()
        t.setReadOnly(True)
        t.setPlainText("\\n".join(rep.get("log", [])))
        l.addWidget(t, 1)
        progs = sorted(rep.get("programs", {}))
        if progs:
            l.addWidget(QLabel(f"{len(progs)} Programme übernommen – in den Editor laden:"))
            c = QComboBox()
            c.addItems(progs)
            l.addWidget(c)
            l.addWidget(self._btn("Programm in Editor laden",
                                  lambda: self.editor.setPlainText(rep["programs"][c.currentText()])))
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        bb.rejected.connect(dlg.reject)
        l.addWidget(bb)
        dlg.exec()

    def import_program(self):''')
open(P, "w", encoding="utf8").write(m)
print("ok")
