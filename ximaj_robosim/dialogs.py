"""Dialoge des Menuebands: Signale, E/A-Uebersicht, Geraete, Antriebe, Maschinendaten, Analyse, Traces, Hilfe usw."""
import os
import json
import math
import time
import zipfile
import numpy as np
from PyQt6.QtCore import Qt, QTimer, QUrl, QPointF, QRectF
from PyQt6.QtGui import QDesktopServices, QPainter, QColor, QPen, QFont, QBrush, QPainterPath
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QGridLayout, QTableWidget, QTableWidgetItem,
                             QPushButton, QLabel, QComboBox, QLineEdit, QDoubleSpinBox, QSpinBox, QCheckBox, QTreeWidget,
                             QTreeWidgetItem, QTextBrowser, QMessageBox, QFileDialog, QInputDialog, QWidget, QListWidget,
                             QHeaderView, QDialogButtonBox, QGraphicsView, QGraphicsScene, QGraphicsRectItem,
                             QGraphicsTextItem, QGraphicsPathItem, QRadioButton, QButtonGroup, QGroupBox, QSplitter,
                             QAbstractItemView, QStackedWidget, QListWidgetItem)

import theme
from icons import icon

B = theme.BRAND


def _dlg(win, title, w=760, h=520):
    d = QDialog(win)
    d.setWindowTitle(title)
    d.resize(w, h)
    return d, QVBoxLayout(d)


def _buttons(d, l, ok=True):
    bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel if ok
                          else QDialogButtonBox.StandardButton.Close)
    for sb, txt in ((QDialogButtonBox.StandardButton.Ok, "OK"), (QDialogButtonBox.StandardButton.Cancel, "Abbrechen"),
                    (QDialogButtonBox.StandardButton.Close, "Schließen")):
        b = bb.button(sb)
        if b is not None:
            b.setText(txt)
    ok_b = bb.button(QDialogButtonBox.StandardButton.Ok)
    if ok_b is not None:
        ok_b.setObjectName("primary")
    bb.accepted.connect(d.accept)
    bb.rejected.connect(d.reject)
    l.addWidget(bb)
    return bb


def _hint(l, text):
    lb = QLabel(text)
    lb.setWordWrap(True)
    lb.setObjectName("muted")
    l.addWidget(lb)
    return lb


def open_url(url):
    QDesktopServices.openUrl(QUrl(url))


def _signal_names(sim, name):
    """bekannte Signalnamen eines Objekts/Roboters (fuer Auswahllisten)"""
    out = []
    for r in sim.robots:
        if r.name == name:
            out += [f"Outputs_Port_{i}" for i in range(1, 33)] + [f"Inputs_Port_{i}" for i in range(1, 33)]
    o = next((o for o in sim.scene if o.name == name), None)
    if o is not None:
        out += {"conveyor": ["Engine"], "conveyor_arc": ["Engine"], "sensor": ["SensorBooleanSignal"],
                "spawner": ["CreationSignal"], "color_sensor": ["ColorTrigger", "ColorDetected", *getattr(o, "color_outs", {}).keys()],
                "lamp": list(getattr(o, "inputs", {}).keys())}.get(o.kind, [])
        host = getattr(sim, "script_host", None)
        try:
            comp = host.components.get(name) if host else None
            if comp is not None:
                out += [s for s in getattr(comp, "signals", {}) if s not in out]
        except Exception:
            pass
    return out


def _endpoints(sim):
    return [r.name for r in sim.robots] + [o.name for o in sim.scene if o.kind not in ("box", "cylinder", "mesh", "fence", "drawing", "group", "workpiece")]


# ---------------------------------------------------------------- Signale / E/A-Verschaltung
def signal_editor(win):
    sim = win.sim
    d, l = _dlg(win, "E/A-Verschaltungseditor", 980, 560)
    _hint(l, "Verbindungen zwischen Signalen von Komponenten und Roboter-Ein-/Ausgängen. Roboterausgänge heißen "
             "Outputs_Port_N ($OUT[N]), Robotereingänge Inputs_Port_N ($IN[N]). Doppelklick bearbeitet eine Zelle.")
    t = QTableWidget(0, 4)
    t.setHorizontalHeaderLabels(["Quelle (Objekt)", "Quelle (Signal)", "Ziel (Objekt)", "Ziel (Signal)"])
    t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    names = _endpoints(sim)

    def add_row(src=("", ""), dst=("", "")):
        r = t.rowCount()
        t.insertRow(r)
        for c, (obj, sig) in enumerate((src, dst)):
            cb = QComboBox()
            cb.setEditable(True)
            cb.addItems(names)
            cb.setCurrentText(obj)
            sc = QComboBox()
            sc.setEditable(True)
            sc.addItems(_signal_names(sim, obj))
            sc.setCurrentText(sig)
            cb.currentTextChanged.connect(lambda n, sc=sc: (sc.clear(), sc.addItems(_signal_names(sim, n))))
            t.setCellWidget(r, c * 2, cb)
            t.setCellWidget(r, c * 2 + 1, sc)

    for k in getattr(sim, "links", []) or []:
        add_row(tuple(k["src"]), tuple(k["dst"]))
    l.addWidget(t, 1)
    h = QHBoxLayout()
    b1 = QPushButton("Verbindung hinzufügen")
    b1.clicked.connect(lambda: add_row())
    b2 = QPushButton("Markierte entfernen")
    b2.clicked.connect(lambda: [t.removeRow(r) for r in sorted({i.row() for i in t.selectedIndexes()} |
                                                                 ({t.currentRow()} if t.currentRow() >= 0 else set()), reverse=True)])
    h.addWidget(b1)
    h.addWidget(b2)
    h.addStretch(1)
    l.addLayout(h)
    _buttons(d, l)
    if d.exec():
        links = []
        for r in range(t.rowCount()):
            v = [t.cellWidget(r, c).currentText().strip() for c in range(4)]
            if all(v):
                links.append({"src": (v[0], v[1]), "dst": (v[2], v[3])})
        sim.links = links
        if hasattr(sim, "wire_links"):
            sim.wire_links()
        win.log_msg(f"E/A-Verschaltung: {len(links)} Verbindungen übernommen")


def io_overview(win):
    """Grafische Uebersicht: Roboter in der Mitte, Komponenten links/rechts, Linien = Verbindungen/E/A"""
    sim = win.sim
    d, l = _dlg(win, "Applikation – Verschaltungsübersicht", 1100, 720)
    sc = QGraphicsScene()
    view = QGraphicsView(sc)
    view.setRenderHint(QPainter.RenderHint.Antialiasing)
    l.addWidget(view, 1)
    nodes = {}

    def node(name, x, y, kind, color):
        r = QGraphicsRectItem(0, 0, 200, 46)
        r.setBrush(QBrush(QColor(color)))
        r.setPen(QPen(QColor(B["border"]), 1))
        r.setPos(x, y)
        sc.addItem(r)
        tx = QGraphicsTextItem(f"{name}\n{kind}")
        tx.setDefaultTextColor(QColor("white" if color in (B["navy"], B["accent"]) else B["text"]))
        tx.setPos(x + 6, y + 2)
        sc.addItem(tx)
        nodes[name] = (x, y)

    for i, r in enumerate(sim.robots):
        node(r.name, 450, 40 + i * 260, "Roboter", B["navy"])
    comps = [o for o in sim.scene if o.kind in ("conveyor", "conveyor_arc", "sensor", "spawner", "sink", "color_sensor", "lamp")]
    for i, o in enumerate(comps):
        node(o.name, 0 if i % 2 == 0 else 900, 20 + (i // 2) * 70, o.kind, "#ffffff")
    pen = QPen(QColor(B["accent"]), 1.6)

    def edge(a, b, label):
        if a not in nodes or b not in nodes:
            return
        (x1, y1), (x2, y2) = nodes[a], nodes[b]
        p1 = QPointF(x1 + (200 if x2 > x1 else 0), y1 + 23)
        p2 = QPointF(x2 + (0 if x2 > x1 else 200), y2 + 23)
        path = QPainterPath(p1)
        mx = (p1.x() + p2.x()) / 2
        path.cubicTo(QPointF(mx, p1.y()), QPointF(mx, p2.y()), p2)
        it = QGraphicsPathItem(path)
        it.setPen(pen)
        sc.addItem(it)
        tx = QGraphicsTextItem(label)
        tx.setDefaultTextColor(QColor(B["muted"]))
        tx.setFont(QFont("Segoe UI", 7))
        tx.setPos((p1 + p2) / 2)
        sc.addItem(tx)

    for k in getattr(sim, "links", []) or []:
        edge(k["src"][0], k["dst"][0], f"{k['src'][1]} → {k['dst'][1]}")
    rname = sim.robots[0].name if sim.robots else None
    linked = {k["src"][0] for k in getattr(sim, "links", []) or []} | {k["dst"][0] for k in getattr(sim, "links", []) or []}
    for o in comps:
        if o.io and o.name not in linked and rname:
            edge(o.name, rname, f"{'$IN' if o.kind in ('sensor', 'color_sensor') else '$OUT'}[{o.io}]")
    _buttons(d, l, ok=False)
    d.exec()


def device_catalog(win):
    sim = win.sim
    d, l = _dlg(win, "Device Catalog – Geräte der Zelle", 900, 560)
    t = QTableWidget(0, 5)
    t.setHorizontalHeaderLabels(["Gerät", "Typ", "E/A", "Verbindungen", "Position (mm)"])
    t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    links = getattr(sim, "links", []) or []
    rows = []
    for r in sim.robots:
        rows.append((r.name, f"Roboter {r.model_key}", "$IN/$OUT 1–1024",
                     sum(1 for k in links if r.name in (k["src"][0], k["dst"][0])), r.root_pose[:3]))
    names = {"conveyor": "Förderband", "conveyor_arc": "Kurvenförderer", "sensor": "Sensor", "spawner": "Teile-Erzeuger",
             "sink": "Senke", "color_sensor": "Farbsensor", "lamp": "Signalleuchte"}
    for o in sim.scene:
        if o.kind in names:
            io = f"{o.io}" if o.io else "–"
            rows.append((o.name, names[o.kind], io, sum(1 for k in links if o.name in (k["src"][0], k["dst"][0])), o.pos))
    for row in rows:
        r = t.rowCount()
        t.insertRow(r)
        for c, v in enumerate((row[0], row[1], row[2], str(row[3]), ", ".join(f"{x:.0f}" for x in row[4]))):
            t.setItem(r, c, QTableWidgetItem(v))
    t.cellDoubleClicked.connect(lambda r, c: _select_by_name(win, t.item(r, 0).text()))
    l.addWidget(t, 1)
    _hint(l, "Doppelklick wählt das Gerät in der 3D-Ansicht. Neue Geräte kommen aus dem Katalog (links).")
    _buttons(d, l, ok=False)
    d.exec()


def _select_by_name(win, name):
    o = next((o for o in win.sim.scene if o.name == name), None)
    if o is not None:
        win.viewer.selected = o
        win.viewer.selection = [o]
        win.on_pick(o)
    else:
        for i, r in enumerate(win.sim.robots):
            if r.name == name:
                win.switch_robot(i) if hasattr(win, "switch_robot") else None


def auto_routing(win):
    """freie E/A automatisch an Sensoren/Farbsensoren ohne Signal vergeben"""
    sim = win.sim
    used_in = {int(o.io) for o in sim.scene if o.kind in ("sensor", "color_sensor") and o.io}
    for o in sim.scene:
        for n in (getattr(o, "color_outs", None) or {}).values():
            used_in.add(int(n or 0))
    linked = {k["src"][0] for k in getattr(sim, "links", []) or []} | {k["dst"][0] for k in getattr(sim, "links", []) or []}
    n_next, done = 1, []
    for o in sim.scene:
        if o.kind == "sensor" and not o.io and o.name not in linked:
            while n_next in used_in:
                n_next += 1
            o.io = n_next
            used_in.add(n_next)
            sim.io.names[("in", n_next)] = o.name
            done.append(f"{o.name} → $IN[{n_next}]")
    win.log_msg("Automatisches Routing: " + ("; ".join(done) if done else "alle Sensoren sind bereits verbunden"))
    QMessageBox.information(win, "Automatisches Routing", "\n".join(done) or "Alle Sensoren sind bereits verbunden.")


# ---------------------------------------------------------------- Antriebe / Maschinendaten
def drive_config(win):
    r = win.sim.active
    m = r.model
    d, l = _dlg(win, f"Antriebskonfiguration – {r.name}", 620, 420)
    _hint(l, f"Modell {r.model_key}. Geschwindigkeiten und Achsgrenzen gelten für dieses Projekt.")
    t = QTableWidget(6, 3)
    t.setHorizontalHeaderLabels(["v max (°/s)", "min (°)", "max (°)"])
    t.setVerticalHeaderLabels([f"A{i + 1}" for i in range(6)])
    for i in range(6):
        for c, v in enumerate((m.vmax[i], m.limits[i][0], m.limits[i][1])):
            t.setItem(i, c, QTableWidgetItem(f"{float(v):g}"))
    t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    l.addWidget(t, 1)
    _buttons(d, l)
    if d.exec():
        try:
            vmax = [float(t.item(i, 0).text()) for i in range(6)]
            lim = [(float(t.item(i, 1).text()), float(t.item(i, 2).text())) for i in range(6)]
        except (ValueError, AttributeError):
            QMessageBox.warning(win, "Antriebskonfiguration", "Ungültige Zahl.")
            return
        if any(v <= 0 for v in vmax) or any(lo >= hi for lo, hi in lim):
            QMessageBox.warning(win, "Antriebskonfiguration", "Geschwindigkeiten müssen > 0 und Minimum < Maximum sein.")
            return
        from kinematics import MODELS, RobotModel
        if getattr(m, "maker", None) != "Eigene":
            # Projektkopie anlegen: mitgelieferte Modelle bleiben unveraendert, die Kopie wird im Projekt gespeichert
            key = f"{r.model_key} · Projekt"
            n = RobotModel(key, m.a1, m.d1, m.a2, m.a3, m.d4, m.d6, lim, vmax, m.payload)
            n.maker, n.cad, n.paint = "Eigene", dict(getattr(m, "cad", None) or {}), getattr(m, "paint", None)
            MODELS[key] = n
            q = r.q.copy()
            r.set_model(key)
            r.q = np.clip(q, n.limits[:, 0], n.limits[:, 1])
        else:
            m.vmax[:] = vmax
            m.limits[:] = lim
        win.sync_from_sim()
        win.update_model_info()
        win.log_msg("Antriebskonfiguration übernommen")


def config_suggest(win):
    """passende Robotermodelle nach Reichweite der Punkte/Objekte und Traglast vorschlagen"""
    from kinematics import MODELS
    sim = win.sim
    r = sim.active
    root = r.robroot()[:3, 3]
    pts = []
    Bw = r.base_world()
    for wp in getattr(r, "waypoints", None) or []:          # eingelernte Punkte (BASE-Koordinaten)
        pts.append((Bw @ np.array([*wp["pos"][:3], 1.0]))[:3])
    pts += [np.array(o.pos, float) for o in sim.scene if o.graspable or o.kind in ("conveyor", "spawner", "sink")]
    need = max([float(np.linalg.norm(p - root)) for p in pts] or [800.0])
    load = float(getattr(r, "payload", 0) or 0)
    cand = sorted(((k, m) for k, m in MODELS.items() if m.reach >= need * 1.05 and (m.payload or 0) >= load),
                  key=lambda km: km[1].reach)
    d, l = _dlg(win, "Konfigurationsvorschlag", 640, 480)
    _hint(l, f"Benötigte Reichweite ≈ {need:.0f} mm (+5 % Reserve), Traglast ≥ {load:g} kg. Kleinste passende Modelle zuerst.")
    lst = QListWidget()
    for k, m in cand[:20]:
        lst.addItem(f"{k} · Reichweite {m.reach:.0f} mm · {m.payload:g} kg")
    l.addWidget(lst, 1)
    _buttons(d, l)
    if d.exec() and lst.currentRow() >= 0:
        k = cand[lst.currentRow()][0]
        r.set_model(k)
        win.sync_from_sim()
        win.viewer.update()
        win.log_msg(f"Robotermodell gewechselt: {k}")


def rcs_export(win):
    r = win.sim.active
    m = r.model
    p, _ = QFileDialog.getSaveFileName(win, "Maschinendaten exportieren", f"{r.name}_maschinendaten.dat", "Maschinendaten (*.dat);;JSON (*.json)")
    if not p:
        return
    if p.lower().endswith(".json"):
        json.dump({"model": r.model_key, "dims": [m.a1, m.d1, m.a2, m.a3, m.d4, m.d6], "limits": [list(map(float, x)) for x in m.limits],
                   "vmax": [float(v) for v in m.vmax], "payload": m.payload, "root": list(r.root_pose),
                   "tool": list(r.tool.tcp), "base": list(r.base)}, open(p, "w", encoding="utf-8"), indent=2)
    else:
        lines = [f"; Maschinendaten {r.name} – {r.model_key} (Ximaj RoboSim)",
                 f"$ROBROOT={{X {r.root_pose[0]:.3f},Y {r.root_pose[1]:.3f},Z {r.root_pose[2]:.3f},A {r.root_pose[3]:.3f},B {r.root_pose[4]:.3f},C {r.root_pose[5]:.3f}}}",
                 f"; Kinematik a1={m.a1} d1={m.d1} a2={m.a2} a3={m.a3} d4={m.d4} d6={m.d6}"]
        for i in range(6):
            lines.append(f"$SOFTN_END[{i + 1}]={m.limits[i][0]:.1f}")
            lines.append(f"$SOFTP_END[{i + 1}]={m.limits[i][1]:.1f}")
            lines.append(f"$VEL_AXIS_MA[{i + 1}]={m.vmax[i]:.1f}")
        lines.append(f"$TOOL={{X {r.tool.tcp[0]:.3f},Y {r.tool.tcp[1]:.3f},Z {r.tool.tcp[2]:.3f},A {r.tool.tcp[3]:.3f},B {r.tool.tcp[4]:.3f},C {r.tool.tcp[5]:.3f}}}")
        open(p, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    win.log_msg(f"Maschinendaten exportiert: {p}")


def transfer_to_controller(win):
    """Projektpaket wie auf einer Steuerung ablegen: Programme, Konfiguration, E/A-Namen je Roboter"""
    folder = QFileDialog.getExistingDirectory(win, "Zielordner (Steuerung/Netzlaufwerk/USB) wählen")
    if not folder:
        return
    sim = win.sim
    n = 0
    for r in sim.robots:
        base = os.path.join(folder, r.name.replace(" ", "_"))
        prog = os.path.join(base, "Program")
        cfg = os.path.join(base, "Config")
        os.makedirs(prog, exist_ok=True)
        os.makedirs(cfg, exist_ok=True)
        src = r.src or ""
        open(os.path.join(prog, "main.src"), "w", encoding="utf-8").write(src)
        n += 1
        json.dump({"model": r.model_key, "root": list(r.root_pose), "tool": list(r.tool.tcp), "base": list(r.base),
                   "points": list(getattr(r, "waypoints", None) or [])},
                  open(os.path.join(cfg, "config.json"), "w", encoding="utf-8"), indent=2)
    names = [[k[0], k[1], v] for k, v in sim.io.names.items()]
    json.dump(names, open(os.path.join(folder, "io_names.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    win.log_msg(f"Konfiguration für {n} Roboter nach {folder} übertragen")
    QMessageBox.information(win, "Übertragen", f"Programme und Konfiguration für {n} Roboter abgelegt in:\n{folder}")


def merge_project(win):
    p, _ = QFileDialog.getOpenFileName(win, "Projekt zusammenführen", "", "Ximaj-Projekt (*.xrsim)")
    if not p:
        return
    from sim import Simulation
    other = Simulation()
    other.from_dict(json.load(open(p, encoding="utf-8")))
    return merge_sim(win, other, os.path.basename(p))


def merge_sim(win, other, label="Projekt"):
    """Objekte, Roboter und Signalverbindungen einer zweiten Simulation uebernehmen (Namen eindeutig halten)"""
    names = {o.name for o in win.sim.scene} | {r.name for r in win.sim.robots}
    ren = {}

    def unique(n):
        new = n
        k = 2
        while new in names:
            new = f"{n} ({k})"
            k += 1
        names.add(new)
        if new != n:
            ren[n] = new
        return new

    for r in other.robots:
        r.name = unique(r.name)
    for o in other.scene:
        o.name = unique(o.name)
    for o in other.scene:
        par = getattr(o, "parent", None)
        if par:
            base, _, suffix = par.partition("@")
            o.parent = ren.get(base, base) + (("@" + suffix) if suffix else "")
        win.sim.scene.append(o)
    added = 0
    for r in other.robots:
        win.sim.robots.append(r)
        r.w = win.sim
        added += 1
    fix = lambda e: (ren.get(e[0], e[0]), e[1])
    win.sim.links = list(getattr(win.sim, "links", []) or []) + [
        {"src": fix(k["src"]), "dst": fix(k["dst"])} for k in (getattr(other, "links", []) or [])]
    if hasattr(win.sim, "wire_links"):
        win.sim.wire_links()
    win.refresh_scene_list()
    win.fill_robot_list()
    win.viewer.update()
    win.log_msg(f"Projekt zusammengeführt: {len(other.scene)} Objekte, {added} Roboter aus {label}")
    return added


def longtext_editor(win):
    sim = win.sim
    d, l = _dlg(win, "Langtext-Editor – E/A-Namen", 760, 640)
    _hint(l, "Klartextnamen für Ein- und Ausgänge. Import/Export als CSV (Typ;Nummer;Name).")
    t = QTableWidget(0, 3)
    t.setHorizontalHeaderLabels(["Typ", "Nummer", "Name"])
    t.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
    for (kind, n), name in sorted(sim.io.names.items(), key=lambda kv: (kv[0][0], kv[0][1])):
        r = t.rowCount()
        t.insertRow(r)
        for c, v in enumerate(("$IN" if kind == "in" else "$OUT", str(n), name)):
            t.setItem(r, c, QTableWidgetItem(v))
    l.addWidget(t, 1)
    h = QHBoxLayout()

    def add():
        r = t.rowCount()
        t.insertRow(r)
        for c, v in enumerate(("$IN", "1", "")):
            t.setItem(r, c, QTableWidgetItem(v))

    def imp():
        p, _ = QFileDialog.getOpenFileName(d, "CSV importieren", "", "CSV (*.csv *.txt)")
        if p:
            for line in open(p, encoding="utf-8-sig"):
                parts = [x.strip() for x in line.replace(",", ";").split(";")]
                if len(parts) >= 3 and parts[1].isdigit():
                    r = t.rowCount()
                    t.insertRow(r)
                    for c, v in enumerate(parts[:3]):
                        t.setItem(r, c, QTableWidgetItem(v))

    def exp():
        p, _ = QFileDialog.getSaveFileName(d, "CSV exportieren", "langtexte.csv", "CSV (*.csv)")
        if p:
            with open(p, "w", encoding="utf-8") as f:
                for r in range(t.rowCount()):
                    f.write(";".join(t.item(r, c).text() if t.item(r, c) else "" for c in range(3)) + "\n")

    for txt, fn in (("Zeile hinzufügen", add), ("CSV importieren …", imp), ("CSV exportieren …", exp)):
        b = QPushButton(txt)
        b.clicked.connect(fn)
        h.addWidget(b)
    h.addStretch(1)
    l.addLayout(h)
    _buttons(d, l)
    if d.exec():
        names = {}
        for r in range(t.rowCount()):
            try:
                kind = "in" if "IN" in t.item(r, 0).text().upper() else "out"
                n = int(t.item(r, 1).text())
                nm = t.item(r, 2).text().strip() if t.item(r, 2) else ""
                if nm:
                    names[(kind, n)] = nm
            except (ValueError, AttributeError):
                pass
        sim.io.names = names
        win.log_msg(f"Langtexte übernommen ({len(names)} Namen)")


# ---------------------------------------------------------------- Programm-Werkzeuge
def robot_world_frame(win, fix_mode):
    r = win.sim.active
    d, l = _dlg(win, f"Robot World Frame verschieben – {r.name}", 460, 300)
    f = QFormLayout()
    sp = []
    for i, n in enumerate(("X", "Y", "Z", "A", "B", "C")):
        s = QDoubleSpinBox()
        s.setRange(-50000, 50000)
        s.setDecimals(1)
        s.setValue(float(r.root_pose[i]))
        sp.append(s)
        f.addRow(n + (" (mm)" if i < 3 else " (°)"), s)
    l.addLayout(f)
    _hint(l, "Position fixieren: " + ("Zur Referenz – angehängte Objekte wandern mit." if fix_mode == "reference"
                                      else "Zur Welt – Objekte bleiben in der Welt stehen."))
    _buttons(d, l)
    if d.exec():
        pose = [s.value() for s in sp]
        try:
            import editing
            editing.move_robot_frame(win.sim, r, pose, fix_mode)
        except Exception:
            r.set_root(pose)
        win.sync_from_sim()
        win.viewer.update()


def sim_config(win):
    sim = win.sim
    d, l = _dlg(win, "Simulationskonfiguration", 480, 360)
    f = QFormLayout()
    spd = QComboBox()
    for t in ("0.25x", "0.5x", "1x", "2x", "5x", "10x", "20x"):
        spd.addItem(t)
    spd.setCurrentText(f"{sim.speed_factor:g}x")
    ovr = QSpinBox()
    ovr.setRange(1, 100)
    ovr.setValue(int(sim.override * 100))
    ovr.setSuffix(" %")
    col = QCheckBox("Kollisionen prüfen")
    col.setChecked(getattr(sim, "collision_enabled", True))
    stop = QCheckBox("Bei Kollision anhalten")
    stop.setChecked(getattr(sim, "stop_on_collision", True))
    lim = QDoubleSpinBox()
    lim.setRange(0.5, 20)
    lim.setSuffix(" % des Achsbereichs")
    lim.setValue(getattr(sim, "limit_warn_pct", 3.0))
    f.addRow("Simulationsgeschwindigkeit", spd)
    f.addRow("Override", ovr)
    f.addRow(col)
    f.addRow(stop)
    f.addRow("Warnung vor Achsgrenze", lim)
    l.addLayout(f)
    _buttons(d, l)
    if d.exec():
        sim.speed_factor = float(spd.currentText()[:-1])
        sim.override = ovr.value() / 100.0
        sim.collision_enabled = col.isChecked()
        sim.stop_on_collision = stop.isChecked()
        sim.limit_warn_pct = lim.value()
        if hasattr(win, "spd"):
            win.spd.setCurrentText(spd.currentText())
            win.ovr.setValue(ovr.value())


def collision_config(win):
    sim = win.sim
    d, l = _dlg(win, "Kollisionserkennung bearbeiten", 640, 560)
    _hint(l, "Haken = Objekt nimmt an der Kollisionsprüfung teil (Hindernis). Ausgenommene Paare werden nicht geprüft.")
    lst = QListWidget()
    for o in sim.scene:
        it = QListWidgetItem(f"{o.name}  ({o.kind})")
        it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        it.setCheckState(Qt.CheckState.Checked if o.obstacle else Qt.CheckState.Unchecked)
        lst.addItem(it)
    l.addWidget(lst, 1)
    ign = QLineEdit("; ".join(f"{a} ↔ {b}" for a, b in sorted(getattr(sim, "collision_ignore", set()) or set())))
    ign.setPlaceholderText("Ausnahmen: Objekt A ↔ Objekt B; …")
    l.addWidget(QLabel("Ausgenommene Paare"))
    l.addWidget(ign)
    _buttons(d, l)
    if d.exec():
        for i, o in enumerate(sim.scene):
            o.obstacle = lst.item(i).checkState() == Qt.CheckState.Checked
        pairs = set()
        for part in ign.text().split(";"):
            if "↔" in part:
                a, b = [x.strip() for x in part.split("↔", 1)]
                if a and b:
                    pairs.add((a, b))
        sim.collision_ignore = pairs
        win.viewer.update()


_overlay = None


def teach_overlay(win, on):
    """schwebendes Lehr-Menue ueber der 3D-Ansicht: Achsen/kartesisch tippen, Punkt einlernen"""
    global _overlay
    if not on:
        if _overlay is not None:
            _overlay.hide()
        return
    if _overlay is None:
        w = QWidget(win.viewer)
        w.setStyleSheet(f"QWidget{{background:rgba(255,255,255,0.94);border-radius:10px}} QPushButton{{padding:3px 6px;min-width:34px}}")
        g = QGridLayout(w)
        g.setContentsMargins(10, 8, 10, 8)
        g.addWidget(QLabel("<b>Lehren</b>"), 0, 0, 1, 4)
        for i, ax in enumerate(("X", "Y", "Z")):
            g.addWidget(QLabel(ax), i + 1, 0)
            for c, s in ((1, -1), (2, 1)):
                b = QPushButton(("−" if s < 0 else "+"))
                b.setAutoRepeat(True)
                b.setAutoRepeatInterval(60)
                b.clicked.connect(lambda _=False, i=i, s=s: _nudge(win, i, s))
                g.addWidget(b, i + 1, c)
        step = QComboBox()
        step.addItems(["1 mm", "10 mm", "50 mm"])
        step.setCurrentIndex(1)
        w._step = step
        g.addWidget(step, 4, 0, 1, 3)
        b = QPushButton("Punkt einlernen")
        b.clicked.connect(win.teach_point)
        g.addWidget(b, 5, 0, 1, 3)
        w.adjustSize()
        _overlay = w
    _overlay.move(16, 16)
    _overlay.show()
    _overlay.raise_()


def _nudge(win, axis, sign):
    st = float(_overlay._step.currentText().split()[0]) if _overlay else 10.0
    r = win.sim.active
    P = r.tcp_world()[:3, 3].copy()
    P[axis] += sign * st
    win.viewer._jog_tcp(P)
    win.viewer.update()


# ---------------------------------------------------------------- Traces
def trace_stats(win, rec):
    d, l = _dlg(win, "Trace – Analyse", 640, 420)
    t = QTableWidget(0, 2)
    t.setHorizontalHeaderLabels(["Kennwert", "Wert"])
    t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    try:
        st = rec.stats()
    except Exception as e:
        st = {"Hinweis": f"Noch keine Aufzeichnung ({e})"}
    if not st:
        st = {"Hinweis": "Noch keine Daten – Online-Aufzeichnung starten und Simulation laufen lassen."}
    for k, v in (st.items() if isinstance(st, dict) else []):
        r = t.rowCount()
        t.insertRow(r)
        t.setItem(r, 0, QTableWidgetItem(str(k)))
        t.setItem(r, 1, QTableWidgetItem(f"{v:.3f}" if isinstance(v, float) else str(v)))
    l.addWidget(t, 1)
    h = QHBoxLayout()
    b = QPushButton("Als CSV speichern …")

    def save():
        p, _ = QFileDialog.getSaveFileName(d, "Trace speichern", "trace.csv", "CSV (*.csv)")
        if p:
            rec.to_csv(p)
    b.clicked.connect(save)
    h.addWidget(b)
    h.addStretch(1)
    l.addLayout(h)
    _buttons(d, l, ok=False)
    d.exec()


class Chart(QWidget):
    """einfaches Liniendiagramm (ohne Fremdbibliothek)"""

    COLORS = ["#0e74bb", "#e8590c", "#2f9e44", "#ae3ec9", "#f08c00", "#1098ad", "#c92a2a"]

    def __init__(self):
        super().__init__()
        self.series = []
        self.title = ""
        self.setMinimumHeight(320)

    def set(self, series, title=""):
        self.series = series
        self.title = title
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor(B["field"]))
        m = 48
        W, H = self.width() - m - 16, self.height() - m - 28
        p.setPen(QColor(B["text"]))
        p.drawText(m, 18, self.title)
        if not self.series or W < 10 or H < 10:
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Keine Daten")
            return
        t0 = min(float(s[1][0]) for s in self.series if len(s[1]))
        t1 = max(float(s[1][-1]) for s in self.series if len(s[1]))
        lo = min(float(np.min(s[2])) for s in self.series if len(s[2]))
        hi = max(float(np.max(s[2])) for s in self.series if len(s[2]))
        if hi - lo < 1e-9:
            hi, lo = hi + 1, lo - 1
        if t1 - t0 < 1e-9:
            t1 = t0 + 1
        X = lambda t: m + (t - t0) / (t1 - t0) * W
        Y = lambda v: 28 + H - (v - lo) / (hi - lo) * H
        p.setPen(QPen(QColor(B["border"]), 1))
        for k in range(6):
            y = 28 + H * k / 5
            p.drawLine(int(m), int(y), int(m + W), int(y))
            p.drawText(2, int(y + 4), f"{hi - (hi - lo) * k / 5:.0f}")
        p.drawText(int(m), int(28 + H + 18), f"{t0:.1f} s")
        p.drawText(int(m + W - 50), int(28 + H + 18), f"{t1:.1f} s")
        for i, (name, t, v) in enumerate(self.series):
            if len(t) < 2:
                continue
            col = QColor(self.COLORS[i % len(self.COLORS)])
            p.setPen(QPen(col, 1.6))
            step = max(1, len(t) // 1500)
            path = QPainterPath(QPointF(X(t[0]), Y(v[0])))
            for k in range(step, len(t), step):
                path.lineTo(QPointF(X(t[k]), Y(v[k])))
            p.drawPath(path)
            p.drawText(int(m + 10 + i * 90), int(self.height() - 6), name)


def trace_chart(win, rec):
    sim = win.sim
    d, l = _dlg(win, "Trace – Diagramm", 980, 560)
    h = QHBoxLayout()
    rc = QComboBox()
    rc.addItems([r.name for r in sim.robots])
    qc = QComboBox()
    qc.addItems(["Achswinkel A1–A6 (°)", "TCP-Geschwindigkeit (mm/s)", "TCP-Position X/Y/Z (mm)"])
    h.addWidget(QLabel("Roboter"))
    h.addWidget(rc)
    h.addWidget(QLabel("Größe"))
    h.addWidget(qc, 1)
    l.addLayout(h)
    ch = Chart()
    l.addWidget(ch, 1)

    def upd():
        name = rc.currentText()
        try:
            if qc.currentIndex() == 0:
                t, q = rec.series(name, "q")
                ser = [(f"A{i + 1}", t, q[:, i]) for i in range(q.shape[1])] if len(q) else []
            elif qc.currentIndex() == 1:
                t, v = rec.series(name, "speed")
                ser = [("v TCP", t, v)]
            else:
                t, xyz = rec.series(name, "tcp")
                ser = [(a, t, xyz[:, i]) for i, a in enumerate("XYZ")] if len(xyz) else []
        except Exception:
            ser = []
        ch.set(ser, f"{name} – {qc.currentText()}")

    rc.currentIndexChanged.connect(upd)
    qc.currentIndexChanged.connect(upd)
    tm = QTimer(d)
    tm.timeout.connect(upd)
    tm.start(500)
    upd()
    _buttons(d, l, ok=False)
    d.exec()


# ---------------------------------------------------------------- Analyse
def analysis_window(win):
    d, l = _dlg(win, "Projektanalyse", 900, 520)
    t = QTableWidget(0, 3)
    t.setHorizontalHeaderLabels(["Stufe", "Meldung", "Objekt"])
    t.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
    t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    l.addWidget(t, 1)
    info = _hint(l, "")

    def run():
        try:
            import analysis
            issues = analysis.analyze(win.sim)
        except Exception as e:
            issues = [{"level": "Fehler", "text": f"Analyse nicht möglich: {e}", "obj": None}]
        t.setRowCount(0)
        colors = {"Fehler": "#dc2626", "Warnung": "#d97706", "Hinweis": B["muted"]}
        for i in issues:
            r = t.rowCount()
            t.insertRow(r)
            it = QTableWidgetItem(i.get("level", ""))
            it.setForeground(QColor(colors.get(i.get("level"), B["text"])))
            t.setItem(r, 0, it)
            t.setItem(r, 1, QTableWidgetItem(i.get("text", "")))
            t.setItem(r, 2, QTableWidgetItem(i.get("obj") or ""))
        info.setText(f"{len(issues)} Einträge · Doppelklick wählt das Objekt" if issues else "Keine Auffälligkeiten gefunden.")

    t.cellDoubleClicked.connect(lambda r, c: t.item(r, 2) and t.item(r, 2).text() and _select_by_name(win, t.item(r, 2).text()))
    b = QPushButton("Erneut analysieren")
    b.clicked.connect(run)
    l.addWidget(b)
    run()
    _buttons(d, l, ok=False)
    d.exec()


# ---------------------------------------------------------------- Verbinden / Struktur / Komponenten
def interfaces(win):
    """Schnittstellen: Foerderbandenden und PnP-Anschluesse anzeigen und verbinden"""
    sim = win.sim
    d, l = _dlg(win, "Schnittstellen", 760, 480)
    t = QTableWidget(0, 4)
    t.setHorizontalHeaderLabels(["Objekt", "Schnittstelle", "Position (mm)", "Nächster Anschluss"])
    t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    try:
        import editing
        ends = [(o, editing.conveyor_ends(o)) for o in sim.scene if o.kind in ("conveyor", "conveyor_arc")]
    except Exception:
        ends = []
    allpts = []
    for o, e in ends:
        for nm in ("start", "end"):
            P = np.array(e[nm] if isinstance(e, dict) else e[0 if nm == "start" else 1], float)
            allpts.append((o, nm, P))
    for o, nm, P in allpts:
        best = min(((np.linalg.norm(P - Q), f"{o2.name}.{n2}") for o2, n2, Q in allpts if o2 is not o), default=None)
        r = t.rowCount()
        t.insertRow(r)
        for c, v in enumerate((o.name, "Eingang" if nm == "start" else "Ausgang", ", ".join(f"{x:.0f}" for x in P),
                               f"{best[1]} ({best[0]:.0f} mm)" if best else "–")):
            t.setItem(r, c, QTableWidgetItem(v))
    l.addWidget(t, 1)
    h = QHBoxLayout()
    b = QPushButton("Auswahl per PnP andocken")

    def pnp():
        try:
            import editing
            for o in [x for x in win.viewer.selection or [win.viewer.selected] if x is not None]:
                m = editing.pnp(sim, o)
                win.log_msg(m or f"{o.name}: kein Anschluss in Reichweite")
            win.refresh_scene_list()
            win.viewer.update()
        except Exception as e:
            QMessageBox.warning(d, "PnP", str(e))
    b.clicked.connect(pnp)
    h.addWidget(b)
    b2 = QPushButton("Signale bearbeiten …")
    b2.clicked.connect(lambda: signal_editor(win))
    h.addWidget(b2)
    h.addStretch(1)
    l.addLayout(h)
    _buttons(d, l, ok=False)
    d.exec()


def structure(win):
    sim = win.sim
    d, l = _dlg(win, "Struktur (Hierarchie)", 560, 600)
    tr = QTreeWidget()
    tr.setHeaderLabels(["Objekt", "Typ"])
    items = {}
    for r in sim.robots:
        it = QTreeWidgetItem([r.name, f"Roboter {r.model_key}"])
        tr.addTopLevelItem(it)
        items[r.name] = it
        items[f"{r.name}@flange"] = it
        items[f"{r.name}@base"] = it
    pending = list(sim.scene)
    for o in pending:
        items.setdefault(o.name, QTreeWidgetItem([o.name, o.kind]))
    for o in pending:
        par = getattr(o, "parent", None)
        if par and par in items and items[par] is not items[o.name]:
            items[par].addChild(items[o.name])
        else:
            tr.addTopLevelItem(items[o.name])
    tr.expandAll()
    tr.itemDoubleClicked.connect(lambda it, c: _select_by_name(win, it.text(0)))
    l.addWidget(tr, 1)
    _hint(l, "Fügen/Ablösen im Reiter START oder MODELLIERUNG. Doppelklick wählt das Objekt.")
    _buttons(d, l, ok=False)
    d.exec()


def save_component(win, objs, ask=False):
    import catalog
    if not objs:
        QMessageBox.information(win, "Komponente speichern", "Bitte zuerst Objekte auswählen.")
        return
    name = objs[0].name if len(objs) == 1 else "Baugruppe"
    if ask:
        name, ok = QInputDialog.getText(win, "Komponente speichern", "Name im Katalog (Kategorie „Eigene“):", text=name)
        if not ok or not name.strip():
            return
    ref = np.array(objs[0].pos, float)
    specs = []
    for o in objs:
        dct = o.to_dict()
        specs.append({"name": o.name, "kind": o.kind, "size": list(o.size), "color": o.color,
                      "off": [float(v) for v in np.array(o.pos) - ref], "rot": list(o.rot), "obstacle": o.obstacle,
                      "graspable": o.graspable, "alpha": getattr(o, "alpha", 1.0), "io": getattr(o, "io", 0),
                      "speed": getattr(o, "speed", 200.0), "interval": getattr(o, "interval", 4.0),
                      "max_parts": getattr(o, "max_parts", 20),
                      **{k: dct[k] for k in ("color_outs", "detected", "trigger", "inputs", "colors") if k in dct}})
    folder = catalog.user_dirs()[0]
    os.makedirs(folder, exist_ok=True)
    fn = os.path.join(folder, "".join(c if c.isalnum() or c in " _-" else "_" for c in name) + ".json")
    json.dump([{"cat": "Eigene", "name": name, "desc": f"Eigene Komponente ({len(specs)} Teile)", "kind": "obj",
                "data": specs}], open(fn, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    win.reload_catalog()
    win.log_msg(f"Komponente „{name}“ gespeichert: {fn}")


# ---------------------------------------------------------------- Assistenten
def conveyor_line(win):
    from sim import SceneObj
    n, ok = QInputDialog.getInt(win, "Förderstrecke", "Anzahl Bänder (je 2 m, hintereinander):", 3, 1, 20)
    if not ok:
        return
    c = win.viewer.center
    x0 = float(c[0])
    for i in range(n):
        o = SceneObj(f"Förderband {len(win.sim.scene) + 1}", "conveyor", [x0 + i * 2000, float(c[1]), 0], [0, 0, 0],
                     [2000, 500, 800], "#2b2f36", True, False)
        win.sim.scene.append(o)
    win.refresh_scene_list()
    win.viewer.update()


def fence_around(win):
    from sim import SceneObj
    pts = [np.array(o.pos, float) for o in win.sim.scene if o.kind not in ("fence", "drawing", "zone")]
    pts += [r.robroot()[:3, 3] for r in win.sim.robots]
    if not pts:
        return
    P = np.array(pts)
    reach = max((r.model.reach for r in win.sim.robots), default=1000)
    lo, hi = P.min(0) - reach * 0.6, P.max(0) + reach * 0.6
    W, D = hi[0] - lo[0], hi[1] - lo[1]
    cx, cy = (lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2
    for name, pos, rot, L in (("Zaun Nord", [cx, hi[1], 0], 0, W), ("Zaun Süd", [cx, lo[1], 0], 0, W),
                              ("Zaun Ost", [hi[0], cy, 0], 90, D), ("Zaun West", [lo[0], cy, 0], 90, D)):
        win.sim.scene.append(SceneObj(name, "fence", [float(v) for v in pos], [rot, 0, 0], [float(L), 50, 2000], "#f5c518", True, False))
    win.refresh_scene_list()
    win.viewer.update()
    win.log_msg("Schutzzaun um die Zelle erstellt")


def pallet(win):
    from sim import SceneObj
    nx, ok = QInputDialog.getInt(win, "Palette", "Teile in X:", 4, 1, 20)
    if not ok:
        return
    ny, ok = QInputDialog.getInt(win, "Palette", "Teile in Y:", 3, 1, 20)
    if not ok:
        return
    c = win.viewer.center
    win.sim.scene.append(SceneObj("Palette", "box", [float(c[0]), float(c[1]), 0], [0, 0, 0], [1200, 800, 144], "#c8a165", True, False))
    for i in range(nx):
        for j in range(ny):
            win.sim.scene.append(SceneObj(f"Teil {i + 1}.{j + 1}", "workpiece",
                                          [float(c[0]) - 450 + i * 900 / max(nx - 1, 1), float(c[1]) - 300 + j * 600 / max(ny - 1, 1), 144],
                                          [0, 0, 0], [100, 80, 60], "#f5b83d", False, True))
    win.refresh_scene_list()
    win.viewer.update()


# ---------------------------------------------------------------- Kamera-Animator
def camera_animator(win):
    v = win.viewer
    d, l = _dlg(win, "Kamera-Animator", 520, 520)
    _hint(l, "Ansichten als Schlüsselbilder speichern und als Kamerafahrt abspielen. Mit „Aufnehmen“ entsteht ein Video.")
    lst = QListWidget()
    keys = getattr(win, "_cam_keys", [])
    win._cam_keys = keys

    def refill():
        lst.clear()
        for i, k in enumerate(keys):
            lst.addItem(f"{i + 1}: Azimut {k['az']:.0f}°, Höhe {k['el']:.0f}°, Abstand {k['dist']:.0f} mm, Dauer {k['t']:.1f} s")

    def add():
        keys.append({"az": v.az, "el": v.el, "dist": v.dist, "center": [float(x) for x in v.center], "t": dur.value()})
        refill()

    def rem():
        if lst.currentRow() >= 0:
            keys.pop(lst.currentRow())
            refill()

    def play(record=False):
        if len(keys) < 2:
            QMessageBox.information(d, "Kamera-Animator", "Mindestens zwei Schlüsselbilder anlegen.")
            return
        if record and not win.recording:
            win.toggle_record()
        state = {"i": 0, "t0": time.perf_counter()}

        def step():
            i = state["i"]
            if i >= len(keys) - 1:
                tm.stop()
                if record and win.recording:
                    win.toggle_record()
                return
            a, b = keys[i], keys[i + 1]
            u = min(1.0, (time.perf_counter() - state["t0"]) / max(b["t"], 0.1))
            s = u * u * (3 - 2 * u)
            v.az = a["az"] + (b["az"] - a["az"]) * s
            v.el = a["el"] + (b["el"] - a["el"]) * s
            v.dist = a["dist"] + (b["dist"] - a["dist"]) * s
            v.center = np.array(a["center"]) + (np.array(b["center"]) - np.array(a["center"])) * s
            v.update()
            if u >= 1:
                state["i"] += 1
                state["t0"] = time.perf_counter()

        tm = QTimer(d)
        tm.timeout.connect(step)
        tm.start(16)

    h = QHBoxLayout()
    dur = QDoubleSpinBox()
    dur.setRange(0.2, 60)
    dur.setValue(3.0)
    dur.setSuffix(" s")
    for txt, fn in (("Aktuelle Ansicht hinzufügen", add), ("Entfernen", rem)):
        b = QPushButton(txt)
        b.clicked.connect(fn)
        h.addWidget(b)
    h.addWidget(QLabel("Dauer"))
    h.addWidget(dur)
    l.addLayout(h)
    l.addWidget(lst, 1)
    h2 = QHBoxLayout()
    for txt, rec in (("▶ Abspielen", False), ("● Abspielen und aufnehmen", True)):
        b = QPushButton(txt)
        b.clicked.connect(lambda _=False, r=rec: play(r))
        h2.addWidget(b)
    l.addLayout(h2)
    refill()
    _buttons(d, l, ok=False)
    d.exec()


# ---------------------------------------------------------------- Hilfe
HELP = {
    "start": ("Erste Schritte", """
<h2>Ximaj RoboSim – Erste Schritte</h2>
<ol><li><b>Roboter wählen:</b> Katalog links › Roboter (eigene XR-Reihe oder Kinematiken nach Herstellerdatenblatt).</li>
<li><b>Zelle aufbauen:</b> Förderbänder, Sensoren, Zäune aus dem Katalog einfügen; mit <i>START › Verschieben</i> platzieren,
mit <i>PnP</i> Förderer automatisch aneinander andocken.</li>
<li><b>Signale verbinden:</b> <i>START › Verbinden › Signale</i> oder <i>KONFIGURATION › E/A Verschaltungseditor</i>.</li>
<li><b>Programmieren:</b> Statements (Bausteine) oder XRL-Editor unten; Punkte im Reiter <i>Punkte</i> einlernen.</li>
<li><b>Simulieren:</b> <i>PROGRAMM › Start</i> (F5); Traces und Diagramme unter <i>PROGRAMM › Trace</i>.</li>
<li><b>Prüfen:</b> <i>Projektanalyse</i> zeigt Fehler, unerreichbare Punkte, Lücken zwischen Förderern usw.</li></ol>"""),
    "tasten": ("Tastenkürzel", """
<h2>Tastenkürzel</h2><table cellpadding=4>
<tr><td>F5</td><td>Programm starten</td></tr><tr><td>F10</td><td>Einzelschritt</td></tr>
<tr><td>Strg+N / O / S</td><td>Neu / Öffnen / Speichern</td></tr><tr><td>Strg+I</td><td>VCMX importieren</td></tr>
<tr><td>Strg+C / V</td><td>Kopieren / Einfügen</td></tr><tr><td>Entf</td><td>Auswahl löschen</td></tr>
<tr><td>Strg+G / Strg+Umschalt+G</td><td>Gruppieren / Gruppierung aufheben</td></tr>
<tr><td>Strg+A</td><td>Alles auswählen</td></tr><tr><td>M</td><td>Verschieben-Modus</td></tr>
<tr><td>Esc</td><td>Werkzeug beenden</td></tr><tr><td>Strg+F1</td><td>Menüband ein-/ausklappen</td></tr>
<tr><td>Strg+R</td><td>Video aufnehmen</td></tr><tr><td>Strg+Klick</td><td>Auswahl ergänzen</td></tr>
<tr><td>Umschalt+Ziehen</td><td>Rahmenauswahl</td></tr><tr><td>Linke Maus</td><td>Drehen</td></tr>
<tr><td>Rechte/mittlere Maus</td><td>Verschieben der Ansicht</td></tr><tr><td>Mausrad</td><td>Zoom</td></tr></table>"""),
    "tipps": ("Tipps & Tricks", """
<h2>Tipps &amp; Tricks</h2><ul>
<li>Beim Verschieben rastet die Position im eingestellten <b>Positionsraster</b> ein; „Automatische Größe“ passt das Raster dem Zoom an.</li>
<li>Der gelbe Ring am Achsenkreuz dreht das Objekt in 15°-Schritten (bei „Immer fangen“).</li>
<li><b>Bewegungsmodus Hierarchie</b> bewegt angehängte Objekte mit, <b>Ausgewählt</b> nur das Objekt selbst.</li>
<li>Mit <b>Messen</b> und Strg-Klick wird der Objektursprung gefangen.</li>
<li><b>Interagieren</b>: Klick auf ein Förderband hält es an, Klick auf einen Teile-Erzeuger erzeugt ein Teil.</li>
<li>Eigene Roboter mit CAD-Geometrie je Achse: <i>KONFIGURATION › Maschinendaten Editor</i>.</li></ul>"""),
    "fehler": ("Fehlerbehebung", """
<h2>Fehlerbehebung</h2><ul>
<li><b>Punkt nicht erreichbar:</b> Status/Turn prüfen, Roboter näher platzieren oder <i>Konfigurationsvorschlag</i> nutzen.</li>
<li><b>Teile werden nicht erzeugt:</b> Signalverbindung des Teile-Erzeugers prüfen (CreationSignal) – im Original oft an $OUT des Roboters.</li>
<li><b>Programm wartet:</b> Meldungen zeigen die Zeile mit WAIT FOR; E/A im Reiter E/A setzen oder Verbindung anlegen.</li>
<li><b>Skripte aus VCMX:</b> beim Import „Ausführen“ bestätigen; Ausgaben der Skripte stehen in den Meldungen.</li></ul>"""),
    "python": ("Python-API", """
<h2>Python-API (Skriptkonsole und VS-Code-Projekte)</h2>
<p>Im Reiter <i>Python-Skript</i> stehen diese Objekte bereit:</p>
<pre>sim            # Simulation (Welt)
sim.robots     # Liste der Roboter;  r = sim.active
r.q            # Achswinkel A1..A6 (Grad, numpy-Array)
r.tcp_world()  # 4x4-Matrix des Werkzeugpunkts in Weltkoordinaten
r.load_program(text); sim.start_all(); sim.stop_all()
sim.io.set_in(n, True); sim.io.get_out(n)
sim.scene      # Objekte: name, kind, pos, rot, size, color
sim.links      # Signalverbindungen [{"src": (obj, sig), "dst": (obj, sig)}]
import editing; editing.move(sim, obj, 100, 0, 0)
import analysis; analysis.analyze(sim)</pre>
<h3>Komponentenskripte (vcCore)</h3><p>Eigene Skripte aus .vcmx-Dateien laufen in einer kompatiblen Umgebung:
<code>getComponent()</code>, <code>findBehavior()</code>, Signale mit <code>.Value</code> und <code>.signal()</code>,
Ereignisse <code>OnStart</code>, <code>OnSignal</code>, <code>OnFinalize</code>, <code>OnSimulationUpdate</code>, Materialien.</p>"""),
    "opcua": ("OPC-UA-API", """
<h2>OPC UA</h2>
<h3>Server (Ximaj RoboSim stellt Daten bereit)</h3>
<p>Start im Reiter <i>Konnektivität</i>. Ist der Port belegt (z. B. 4840 durch einen anderen OPC-UA-Dienst), wählt der Server
automatisch den nächsten freien Port und zeigt ihn an. Endpunkt: <code>opc.tcp://&lt;PC-Name&gt;:&lt;Port&gt;/ximaj/robosim</code>,
Namespace <code>urn:ximaj:robosim</code>.</p>
<ul><li><b>Simulation</b>: State, Time, SpeedFactor (schreibbar), RobotCount; Methoden StartAll, StopAll, ResetAll</li>
<li><b>Robots/&lt;Name&gt;</b>: State, Line, Message, Model, Override (schreibbar), Collision, CycleTime, EnergyWh, E1,
Axes/A1–A6, JointPosition, Tcp/X–C in BASE, TcpWorld/X–C in Welt, Points/&lt;Name&gt;; Methoden Start, Stop, Pause, Reset, LoadProgram(text)</li>
<li><b>Robot</b>: dasselbe für den aktiven Roboter (kompatibel zu älteren Versionen)</li>
<li><b>IO/In/I1…</b>, <b>IO/Out/O1…</b>: lesen und schreiben (Anzahl einstellbar, Beschreibung = E/A-Name)</li>
<li><b>Components</b>: Sensoren (Signal), Förderer (Running, Speed schreibbar), Teile-Erzeuger (Created),
Farbsensoren (Detected, Color), Signalleuchten (Color)</li></ul>
<p><b>Roboterpunkte / OPC-UA-Knoten</b> zeigt die tatsächlichen String-NodeIds, Einheiten und Werte. Doppelklick kopiert die NodeId;
CSV-/JSON-Export enthält auch Namespace-URI und Identifier. Alte numerische NodeIds müssen neu zugeordnet werden.</p>
<p>Teach-Punkte: X/Y/Z in mm, A/B/C in Grad; WorldPose nur bei WorldKnown=true verwenden. Neue Punkte speichern ihren Weltbezug,
bei älteren Punkten bleibt er unbekannt. Ein externer OPC-UA-Server benötigt einen Client/Adapter, um diese Knoten einzulesen.</p>
<h3>Clients (Ximaj RoboSim verbindet sich mit SPS, Steuerung, Leitsystem)</h3>
<p><i>Konnektivität › OPC-UA-Clients › Neu</i>: URL eintragen, „Verbinden und Variablen durchsuchen“, Variablen auswählen und
zuordnen. <b>lesen</b> überträgt den externen Wert in die Simulation (IN:n, OUT:n, OVERRIDE, SPEED), <b>schreiben</b> überträgt
Simulationswerte zum externen Knoten (IN:n, OUT:n, AXIS:Roboter:1–6, TCP:Roboter:X–C, STATE:Roboter).
Verbindungen werden im Projekt gespeichert (Passwörter nicht).</p>"""),
    "xrl": ("XRL-Referenz", """
<h2>XRL – Roboterprogrammiersprache</h2><pre>DEF main()
  PTP HOME
  LIN {X 500, Y 0, Z 300, A 0, B 90, C 0} C_DIS
  CIRC P1, P2
  $OUT[1] = TRUE
  WAIT FOR $IN[1]
  WAIT SEC 0.5
  FOR i = 1 TO 5 ... ENDFOR
  IF $IN[2] THEN ... ELSE ... ENDIF
  SWITCH nr  CASE 1 ... DEFAULT ... ENDSWITCH
END</pre><p>Kompatibel zu gängigen Robotersprachen: SPTP/SLIN/SCIRC, WITH, DEFDAT, Unterprogramme, Funktionen, PULSE.</p>"""),
}


def help_dialog(win, topic=None):
    d, l = _dlg(win, "Hilfe – Ximaj RoboSim", 980, 680)
    sp = QSplitter()
    nav = QListWidget()
    tb = QTextBrowser()
    tb.setOpenExternalLinks(True)
    keys = list(HELP)
    for k in keys:
        nav.addItem(HELP[k][0])
    sp.addWidget(nav)
    sp.addWidget(tb)
    sp.setSizes([220, 760])
    l.addWidget(sp, 1)
    nav.currentRowChanged.connect(lambda i: tb.setHtml(HELP[keys[i]][1]))
    idx = 0
    if topic:
        t = topic.lower()
        if t in HELP:
            idx = keys.index(t)
        else:
            hits = [i for i, k in enumerate(keys) if t in HELP[k][1].lower() or t in HELP[k][0].lower()]
            idx = hits[0] if hits else 0
    nav.setCurrentRow(idx)
    if topic and topic.lower() not in HELP:
        tb.find(topic)
    _buttons(d, l, ok=False)
    d.exec()


def bug_report(win):
    from version import VERSION
    import platform, traceback
    desk = os.path.join(os.path.expanduser("~"), "Desktop")
    p, _ = QFileDialog.getSaveFileName(win, "Fehlerbericht speichern", os.path.join(desk, f"XimajRoboSim_Fehlerbericht_{time.strftime('%Y%m%d_%H%M')}.zip"),
                                       "ZIP (*.zip)")
    if not p:
        return
    with zipfile.ZipFile(p, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("info.txt", f"Version {VERSION}\nPython {platform.python_version()}\n{platform.platform()}\n"
                               f"Roboter {len(win.sim.robots)}, Objekte {len(win.sim.scene)}\nZeit {time.ctime()}\n")
        z.writestr("meldungen.txt", "\n".join(str(x) for x in (win.sim.log if isinstance(win.sim.log, list) else [])))
        try:
            z.writestr("projekt.xrsim", json.dumps(win.sim.to_dict(), default=str))
        except Exception:
            z.writestr("projekt_fehler.txt", traceback.format_exc())
    QMessageBox.information(win, "Fehlerbericht", f"Fehlerbericht gespeichert:\n{p}\n\nBitte an den Ximaj-Support senden.")


API_STUB = '''"""Ximaj RoboSim – Skript-Vorlage. In der App: Reiter Python-Skript › Datei laden, oder per OPC UA ansteuern."""
# Verfügbare Objekte in der Skriptkonsole: sim (Simulation), np (numpy)

def main(sim):
    r = sim.active
    print("Roboter:", r.name, "Achsen:", list(r.q))
    for o in sim.scene:
        print(o.name, o.kind, o.pos)


if "sim" in globals():
    main(sim)
'''


def vscode_project(win, new=True):
    import shutil, subprocess
    if new:
        folder = QFileDialog.getExistingDirectory(win, "Ordner für das neue VS-Code-Projekt wählen")
        if not folder:
            return
        os.makedirs(os.path.join(folder, ".vscode"), exist_ok=True)
        src = os.path.dirname(os.path.abspath(__file__))
        json.dump({"python.analysis.extraPaths": [src], "python.languageServer": "Pylance"},
                  open(os.path.join(folder, ".vscode", "settings.json"), "w", encoding="utf-8"), indent=2)
        open(os.path.join(folder, "skript.py"), "w", encoding="utf-8").write(API_STUB)
        open(os.path.join(folder, "README.md"), "w", encoding="utf-8").write(
            "# Ximaj RoboSim Skriptprojekt\n\nSkripte in der App im Reiter *Python-Skript* ausführen. API: Hilfe › Python-API.\n")
    else:
        folder = QFileDialog.getExistingDirectory(win, "VS-Code-Projekt öffnen")
        if not folder:
            return
    code = shutil.which("code") or shutil.which("code.cmd")
    if code:
        subprocess.Popen([code, folder])
    else:
        os.startfile(folder)
        QMessageBox.information(win, "VS Code", "Visual Studio Code wurde nicht gefunden – der Ordner wurde im Explorer geöffnet.")


def guided_workflow(win):
    d, l = _dlg(win, "Geführter Arbeitsablauf", 640, 460)
    st = QStackedWidget()
    steps = [("Roboter", "Wählen Sie einen Roboter im Katalog (links) oder legen Sie im Maschinendaten-Editor einen eigenen an.",
              lambda: win.ribbon.focus_left("Katalog")),
             ("Werkzeug", "Wählen Sie ein Werkzeug im Katalog › Werkzeuge oder stellen Sie den TCP im Reiter Roboter ein.",
              lambda: win.ribbon.focus_left("Roboter")),
             ("Zelle", "Fügen Sie Förderer, Sensoren und Zäune hinzu und platzieren Sie sie mit Verschieben/PnP.",
              lambda: win.ribbon.set_mode("pnp")),
             ("Signale", "Verbinden Sie Sensoren und Aktoren mit den Roboter-E/A.", lambda: signal_editor(win)),
             ("Programm", "Lernen Sie Punkte ein und erstellen Sie das Programm als Statements oder in XRL.",
              lambda: win.ribbon.focus_bottom("Statements")),
             ("Simulation", "Starten Sie die Simulation und prüfen Sie Taktzeit, Kollisionen und die Projektanalyse.",
              lambda: win.run_prog())]
    for i, (t, txt, fn) in enumerate(steps):
        w = QWidget()
        v = QVBoxLayout(w)
        h = QLabel(f"Schritt {i + 1} von {len(steps)}: {t}")
        h.setObjectName("heading")
        v.addWidget(h)
        lb = QLabel(txt)
        lb.setWordWrap(True)
        v.addWidget(lb)
        b = QPushButton(f"{t} jetzt öffnen")
        b.setObjectName("primary")
        b.clicked.connect(fn)
        v.addWidget(b)
        v.addStretch(1)
        st.addWidget(w)
    l.addWidget(st, 1)
    h = QHBoxLayout()
    bp, bn = QPushButton("Zurück"), QPushButton("Weiter")
    bp.clicked.connect(lambda: st.setCurrentIndex(max(0, st.currentIndex() - 1)))
    bn.clicked.connect(lambda: st.setCurrentIndex(min(st.count() - 1, st.currentIndex() + 1)))
    h.addWidget(bp)
    h.addStretch(1)
    h.addWidget(bn)
    l.addLayout(h)
    _buttons(d, l, ok=False)
    d.exec()


# ---------------------------------------------------------------- OPC-UA-Client
def opcua_nodes_dialog(win, service, run=True):
    """Die echten Serverknoten filtern, kopieren und als Integrationsliste exportieren."""
    from PyQt6.QtWidgets import QApplication
    from opcua_nodes import NAMESPACE_URI, export_nodes
    d, l = _dlg(win, "Roboterpunkte und OPC-UA-Knoten", 1120, 650)
    d.setObjectName("opcNodesDialog")
    info = QLabel("Namespace: " + NAMESPACE_URI + "\n" + "\n".join(service.endpoints()))
    info.setWordWrap(True)
    info.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    l.addWidget(info)
    hint = QLabel("Achsen: Grad · X/Y/Z: mm · A/B/C: Grad (ZYX). Tcp: aktuelle BASE · TcpWorld: Welt.\n"
                  "Points: eingelernte Punkte. WorldPose gilt nur bei WorldKnown=true. Doppelklick kopiert die NodeId.")
    hint.setWordWrap(True)
    l.addWidget(hint)
    flt = QLineEdit()
    flt.setObjectName("opcNodesFilter")
    flt.setPlaceholderText("Knoten filtern, z. B. Points, TcpWorld oder Robotername …")
    l.addWidget(flt)
    table = QTableWidget(0, 7)
    table.setObjectName("opcNodesTable")
    table.setHorizontalHeaderLabels(["Pfad / NodeId", "Typ", "Zugriff", "Einheit", "Bezug", "Wert", "Namespace"])
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
    table.setColumnWidth(0, 400)
    table.setColumnWidth(1, 75)
    table.setColumnWidth(2, 95)
    table.setColumnWidth(3, 70)
    table.setColumnWidth(4, 140)
    table.setColumnWidth(5, 140)
    table.setColumnHidden(6, True)  # Namespace steht oben und im Export; mehr Platz für Koordinaten.
    l.addWidget(table, 1)
    state = QLabel()
    l.addWidget(state)
    buttons = QHBoxLayout()
    copy_btn = QPushButton("NodeId kopieren")
    export_btn = QPushButton("Alle Knoten exportieren …")
    buttons.addWidget(copy_btn)
    buttons.addWidget(export_btn)
    buttons.addStretch(1)
    l.addLayout(buttons)

    def refresh():
        selected = table.item(table.currentRow(), 0)
        selected_id = selected.data(Qt.ItemDataRole.UserRole) if selected else None
        rows = service.catalog() if service.running else []
        query = flt.text().strip().casefold()
        shown = [r for r in rows if query in (r["path"] + r["node_id"] + r["frame"]).casefold()]
        table.setRowCount(len(shown))
        for i, row in enumerate(shown):
            vals = (row["node_id"], row["data_type"] or row["node_class"], row["access"], row["unit"],
                    row["frame"], str(row["value"]) if row["value"] is not None else "", row["namespace_uri"])
            for j, value in enumerate(vals):
                it = QTableWidgetItem(value)
                it.setToolTip(value)
                if j == 0:
                    it.setData(Qt.ItemDataRole.UserRole, row["node_id"])
                table.setItem(i, j, it)
            if row["node_id"] == selected_id:
                table.selectRow(i)
        state.setText((f"{len(shown)} / {len(rows)} Knoten · Werte aus der laufenden Simulation" if service.running else "Server gestoppt")
                      + (f" · Fehler: {service.error}" if service.error else ""))
        export_btn.setEnabled(service.running and bool(rows))

    def copy_id():
        item = table.item(table.currentRow(), 0)
        if item:
            QApplication.clipboard().setText(item.data(Qt.ItemDataRole.UserRole))

    def export():
        path, _ = QFileDialog.getSaveFileName(d, "OPC-UA-Knoten exportieren", "RoboSim-Knoten.json", "JSON (*.json);;CSV (*.csv)")
        if path:
            try:
                export_nodes(path, service.catalog(), service.endpoints())
                state.setText(f"Alle Knoten exportiert: {path}")
            except Exception as e:
                QMessageBox.warning(d, "Export fehlgeschlagen", str(e))

    table.cellDoubleClicked.connect(lambda *_: copy_id())
    copy_btn.clicked.connect(copy_id)
    export_btn.clicked.connect(export)
    flt.textChanged.connect(lambda _: refresh())
    timer = QTimer(d)
    timer.timeout.connect(refresh)
    timer.start(1000)
    refresh()
    _buttons(d, l, ok=False)
    if run:
        d.exec()
    return d


def opcua_client_dialog(win, c):
    """Verbindung zu einem externen OPC-UA-Server einrichten: URL, Anmeldung, Variablen durchsuchen und zuordnen"""
    from opcua_client import TARGET_HELP
    d, l = _dlg(win, f"OPC-UA-Verbindung – {c.name}", 1180, 720)
    f = QFormLayout()
    name = QLineEdit(c.name)
    url = QComboBox()
    url.setEditable(True)
    sugg = [c.url] if c.url else []
    srv = getattr(win, "opc", None)
    if srv is not None and srv.running:
        sugg += srv.endpoints()[:1]
    sugg += ["opc.tcp://localhost:4840"]
    for u in dict.fromkeys(sugg):
        url.addItem(u)
    url.setCurrentText(c.url or sugg[0])
    user = QLineEdit(c.user)
    pw = QLineEdit(c.password)
    pw.setEchoMode(QLineEdit.EchoMode.Password)
    per = QDoubleSpinBox()
    per.setRange(0.02, 10)
    per.setDecimals(2)
    per.setSuffix(" s")
    per.setValue(c.period)
    f.addRow("Name", name)
    f.addRow("Server-URL", url)
    f.addRow("Benutzer (optional)", user)
    f.addRow("Passwort", pw)
    f.addRow("Abfragezyklus", per)
    l.addLayout(f)
    sp = QSplitter()
    left = QWidget()
    lv = QVBoxLayout(left)
    lv.setContentsMargins(0, 0, 0, 0)
    hb = QHBoxLayout()
    bbrowse = QPushButton("Verbinden und Variablen durchsuchen")
    bbrowse.setObjectName("primary")
    flt = QLineEdit()
    flt.setPlaceholderText("Filter …")
    hb.addWidget(bbrowse)
    hb.addWidget(flt, 1)
    lv.addLayout(hb)
    vars_t = QTableWidget(0, 4)
    vars_t.setHorizontalHeaderLabels(["Variable", "NodeId", "Typ", "Wert"])
    vars_t.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
    vars_t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    vars_t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    lv.addWidget(vars_t, 1)
    status = _hint(lv, "Noch nicht durchsucht.")
    sp.addWidget(left)
    right = QWidget()
    rv = QVBoxLayout(right)
    rv.setContentsMargins(0, 0, 0, 0)
    rv.addWidget(QLabel("Zuordnungen (Variable ↔ Simulation)"))
    map_t = QTableWidget(0, 4)
    map_t.setHorizontalHeaderLabels(["NodeId", "Richtung", "Ziel in der Simulation", "Zustand"])
    map_t.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
    map_t.setToolTip(TARGET_HELP)
    rv.addWidget(map_t, 1)
    hb2 = QHBoxLayout()
    badd = QPushButton("← Ausgewählte zuordnen")
    bman = QPushButton("Leere Zeile")
    bdel = QPushButton("Zuordnung entfernen")
    for b in (badd, bman, bdel):
        hb2.addWidget(b)
    rv.addLayout(hb2)
    _hint(rv, "Richtung „lesen“: externer Wert → Simulation. „schreiben“: Simulation → externer Knoten.\n" + TARGET_HELP)
    sp.addWidget(right)
    sp.setSizes([560, 600])
    l.addWidget(sp, 1)
    found = []

    def target_box(val):
        cb = QComboBox()
        cb.setEditable(True)
        items = [f"IN:{i}" for i in range(1, 17)] + [f"OUT:{i}" for i in range(1, 17)] + ["OVERRIDE", "SPEED"]
        for r in win.sim.robots:
            items += [f"AXIS:{r.name}:{i}" for i in range(1, 7)] + [f"TCP:{r.name}:{a}" for a in "XYZABC"] + [f"STATE:{r.name}"]
        cb.addItems(items)
        cb.setCurrentText(val)
        return cb

    def dir_box(val):
        cb = QComboBox()
        cb.addItems(["lesen", "schreiben"])
        cb.setCurrentIndex(0 if val == "read" else 1)
        return cb

    def add_map(node="", direction="read", target="IN:1", state=""):
        r = map_t.rowCount()
        map_t.insertRow(r)
        map_t.setItem(r, 0, QTableWidgetItem(node))
        map_t.setCellWidget(r, 1, dir_box(direction))
        map_t.setCellWidget(r, 2, target_box(target))
        map_t.setItem(r, 3, QTableWidgetItem(state))

    for m in c.mappings:
        st = m.get("error") or (f"Wert {c.values.get(m.get('node'))!r}" if m.get("node") in c.values else "")
        add_map(m.get("node", ""), m.get("dir", "read"), m.get("target", ""), st)

    def apply_fields():
        c.name = name.text().strip() or "Verbindung"
        c.url = url.currentText().strip()
        c.user = user.text().strip()
        c.password = pw.text()
        c.period = per.value()

    def fill(rows):
        q = flt.text().lower()
        vars_t.setRowCount(0)
        for path, nid, vt, val in rows:
            if q and q not in path.lower() and q not in nid.lower():
                continue
            r = vars_t.rowCount()
            vars_t.insertRow(r)
            for j, txt in enumerate((path, nid, vt, "" if val is None else str(val)[:40])):
                vars_t.setItem(r, j, QTableWidgetItem(txt))

    def browse():
        apply_fields()
        status.setText("Verbinde …")
        QApplication_process()
        try:
            rows = c.browse()
        except Exception as e:
            status.setText(f"Fehler: {type(e).__name__}: {e}")
            return
        found[:] = rows
        fill(rows)
        status.setText(f"{len(rows)} Variablen gefunden auf {c.url}")

    def used_inputs():
        out = set()
        for r in range(map_t.rowCount()):
            t = map_t.cellWidget(r, 2).currentText().upper()
            if t.startswith("IN:") or t.startswith("OUT:"):
                out.add(t)
        return out

    def add_selected():
        rows = sorted({i.row() for i in vars_t.selectedIndexes()})
        for r in rows:
            nid = vars_t.item(r, 1).text()
            vt = vars_t.item(r, 2).text()
            used = used_inputs()
            if vt == "Boolean":
                n = next(i for i in range(1, 1025) if f"IN:{i}" not in used)
                add_map(nid, "read", f"IN:{n}")
            else:
                add_map(nid, "read", "OVERRIDE")

    def del_map():
        for r in sorted({i.row() for i in map_t.selectedIndexes()} | ({map_t.currentRow()} if map_t.currentRow() >= 0 else set()), reverse=True):
            map_t.removeRow(r)

    bbrowse.clicked.connect(browse)
    flt.textChanged.connect(lambda _: fill(found))
    badd.clicked.connect(add_selected)
    bman.clicked.connect(lambda: add_map())
    bdel.clicked.connect(del_map)
    _buttons(d, l)
    if not d.exec():
        return False
    apply_fields()
    maps = []
    for r in range(map_t.rowCount()):
        nid = (map_t.item(r, 0).text() if map_t.item(r, 0) else "").strip()
        if nid:
            maps.append({"node": nid, "dir": "read" if map_t.cellWidget(r, 1).currentIndex() == 0 else "write",
                         "target": map_t.cellWidget(r, 2).currentText().strip()})
    c.mappings[:] = maps            # gleiche Liste: wirkt auch bei laufender Verbindung sofort
    return True


def QApplication_process():
    from PyQt6.QtWidgets import QApplication
    QApplication.processEvents()
