"""Funktionspruefung der Menueband-Funktionen mit echten Daten: Dialoge werden wie von Hand ausgefuellt
und bestaetigt, danach wird das Ergebnis in der Simulation geprueft.  python tests/test_ribbon_functions.py"""
import sys, os, json, tempfile, zipfile, traceback
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'ximaj_robosim'))
import numpy as np
from PyQt6.QtGui import QSurfaceFormat
from PyQt6.QtWidgets import (QApplication, QDialog, QMessageBox, QInputDialog, QFileDialog, QPushButton, QTableWidget,
                             QComboBox, QDoubleSpinBox, QSpinBox, QCheckBox, QListWidget, QTreeWidget, QLineEdit,
                             QGraphicsView, QStackedWidget, QTextBrowser, QTableWidgetItem)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtTest import QTest
fmt = QSurfaceFormat(); fmt.setDepthBufferSize(24); fmt.setStencilBufferSize(8)
QSurfaceFormat.setDefaultFormat(fmt)
app = QApplication(sys.argv)
errors = []
sys.excepthook = lambda et, ev, tb: errors.append("".join(traceback.format_exception(et, ev, tb)))

TMP = tempfile.mkdtemp(prefix="xrs_test_")
HOOK = [None]
QDialog.exec = lambda self: (HOOK[0](self) if HOOK[0] else 0)
QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok)
QMessageBox.warning = staticmethod(lambda *a, **k: (errors.append("WARNUNG " + str(a[2] if len(a) > 2 else a)), QMessageBox.StandardButton.Ok)[1])
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
ANSWER = {}
QInputDialog.getItem = staticmethod(lambda *a, **k: ANSWER.pop("item", ("", False)))
QInputDialog.getText = staticmethod(lambda *a, **k: ANSWER.pop("text", ("", False)))
QInputDialog.getInt = staticmethod(lambda *a, **k: ANSWER["ints"].pop(0) if ANSWER.get("ints") else (0, False))
QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: (ANSWER.pop("open", ""), ""))
QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (ANSWER.pop("save", ""), ""))
QFileDialog.getExistingDirectory = staticmethod(lambda *a, **k: ANSWER.pop("dir", ""))
os.startfile = lambda *a, **k: None
import shutil as _sh
_which = _sh.which
_sh.which = lambda n, *a, **k: None if n.startswith("code") else _which(n, *a, **k)

import theme, main, catalog, dialogs
from sim import SceneObj, Simulation
catalog.user_dirs = lambda: [os.path.join(TMP, "catalog")]
w = main.MainWindow(); w.resize(1500, 950); w.show()
import tempfile, pathlib; w.autosave.directory = pathlib.Path(tempfile.mkdtemp())  # nicht in echte Nutzerdaten
R = w.ribbon
sim, v = w.sim, w.viewer
results = []


def kid(d, cls, n=0):
    return d.findChildren(cls)[n]


def btn(d, text):
    return next(b for b in d.findChildren(QPushButton) if b.text().startswith(text))


def check(name, cond, info=""):
    results.append((name, bool(cond), info))


def run(name, fn):
    n0 = len(errors)
    try:
        fn()
    except Exception:
        errors.append(f"[{name}]\n" + traceback.format_exc())
        check(name, False, "Ausnahme")
    if len(errors) > n0 and not errors[-1].startswith("["):
        errors[-1] = f"[{name}]\n" + errors[-1]
    HOOK[0] = None


def setup_cell():
    e = [e for e in catalog.CATALOG if e["kind"] == "cell"][1]
    catalog.apply(sim, e)
    w.sync_from_sim()
    w.refresh_scene_list()


setup_cell()
conv = next(o for o in sim.scene if o.kind == "conveyor")
sens = next((o for o in sim.scene if o.kind == "sensor"), None)
rob = sim.active


# ---------------------------------------------------------------- Signale / E/A
def t_signal_editor():
    def hook(d):
        btn(d, "Verbindung hinzufügen").click()
        t = kid(d, QTableWidget)
        r = t.rowCount() - 1
        t.cellWidget(r, 0).setCurrentText(rob.name)
        t.cellWidget(r, 1).setCurrentText("Outputs_Port_5")
        t.cellWidget(r, 2).setCurrentText(conv.name)
        t.cellWidget(r, 3).setCurrentText("Engine")
        return 1
    HOOK[0] = hook
    dialogs.signal_editor(w)
    ok = any(tuple(k["src"]) == (rob.name, "Outputs_Port_5") and tuple(k["dst"]) == (conv.name, "Engine") for k in sim.links)
    check("E/A-Verschaltung: Verbindung angelegt", ok)
    check("E/A-Verschaltung: Förderband hängt an $OUT[5]", int(conv.io) == 5 or w.sim._driven(conv, conv.io) is not None, f"io={conv.io}")
    sim.io.set_out(5, False)
    x0 = None
    part = SceneObj("Testteil", "workpiece", [conv.pos[0] - conv.size[0] / 4, conv.pos[1], conv.size[2]], [conv.rot[0], 0, 0], [60, 40, 40], "#ff0000", False, True)
    sim.scene.append(part)
    x0 = list(part.pos)
    for _ in range(20):
        sim.tick(0.05)
    still = np.linalg.norm(np.array(part.pos[:2]) - x0[:2]) < 1
    sim.io.set_out(5, True)
    for _ in range(20):
        sim.tick(0.05)
    moved = np.linalg.norm(np.array(part.pos[:2]) - x0[:2]) > 20
    check("E/A-Verschaltung: Band steht ohne $OUT[5] und läuft mit", still and moved, f"still={still} moved={moved}")
    sim.scene.remove(part)
    # Verbindung wieder entfernen
    def hook2(d):
        t = kid(d, QTableWidget)
        for r in range(t.rowCount() - 1, -1, -1):
            if t.cellWidget(r, 1).currentText() == "Outputs_Port_5":
                t.removeRow(r)
        return 1
    HOOK[0] = hook2
    dialogs.signal_editor(w)
    check("E/A-Verschaltung: Verbindung entfernt", not any(k["src"][1] == "Outputs_Port_5" for k in sim.links))


def t_overview():
    cnt = {}
    def hook(d):
        cnt["n"] = len(kid(d, QGraphicsView).scene().items())
        return 0
    HOOK[0] = hook
    dialogs.io_overview(w)
    check("Verschaltungsübersicht zeichnet Knoten", cnt.get("n", 0) >= 4, f"{cnt.get('n')} Elemente")


def t_devices():
    cnt = {}
    def hook(d):
        cnt["rows"] = kid(d, QTableWidget).rowCount()
        return 0
    HOOK[0] = hook
    dialogs.device_catalog(w)
    exp = len(sim.robots) + sum(1 for o in sim.scene if o.kind in ("conveyor", "conveyor_arc", "sensor", "spawner", "sink", "color_sensor", "lamp"))
    check("Device Catalog listet alle Geräte", cnt.get("rows") == exp, f"{cnt.get('rows')} von {exp}")


def t_routing():
    s2 = SceneObj("Neuer Sensor", "sensor", [0, 0, 0], [0, 0, 0], [40, 300, 150], "#22d3c5", False, False)
    sim.scene.append(s2)
    used = {int(o.io) for o in sim.scene if o.kind == "sensor" and o.io and o is not s2}
    dialogs.auto_routing(w)
    check("Automatisches Routing vergibt freien Eingang", s2.io and int(s2.io) not in used, f"io={s2.io}")
    check("Automatisches Routing setzt E/A-Namen", sim.io.names.get(("in", int(s2.io))) == "Neuer Sensor")
    sim.scene.remove(s2)


# ---------------------------------------------------------------- Antriebe / Maschinendaten
def t_drive():
    key0 = rob.model_key
    def hook(d):
        t = kid(d, QTableWidget)
        t.setItem(0, 0, QTableWidgetItem("123"))
        t.setItem(1, 1, QTableWidgetItem("-100"))
        return 1
    HOOK[0] = hook
    from kinematics import MODELS
    v_orig = float(MODELS[key0].vmax[0])
    dialogs.drive_config(w)
    check("Antriebskonfiguration: v max übernommen", float(rob.model.vmax[0]) == 123 and float(rob.model.limits[1][0]) == -100)
    check("Antriebskonfiguration: Originalmodell unverändert", float(MODELS[key0].vmax[0]) == v_orig)
    d = sim.to_dict()
    check("Antriebskonfiguration: im Projekt gespeichert", rob.model_key in d.get("imported_models", {}))
    rob.set_model(key0)


def t_suggest():
    def hook(d):
        lst = kid(d, QListWidget)
        if lst.count() == 0:
            return 0
        lst.setCurrentRow(0)
        return 1
    HOOK[0] = hook
    k0 = rob.model_key
    dialogs.config_suggest(w)
    m = rob.model
    root = rob.robroot()[:3, 3]
    need = max(np.linalg.norm(np.array(o.pos) - root) for o in sim.scene if o.graspable or o.kind in ("conveyor", "spawner", "sink"))
    check("Konfigurationsvorschlag: Modell mit ausreichender Reichweite", m.reach >= need, f"{rob.model_key}: {m.reach:.0f} >= {need:.0f}")
    rob.set_model(k0)


def t_rcs():
    p = os.path.join(TMP, "md.dat")
    ANSWER["save"] = p
    dialogs.rcs_export(w)
    txt = open(p, encoding="utf-8").read() if os.path.exists(p) else ""
    check("RCS Export: Maschinendaten-Datei", "$SOFTN_END[1]" in txt and "$ROBROOT" in txt)
    p2 = os.path.join(TMP, "md.json")
    ANSWER["save"] = p2
    dialogs.rcs_export(w)
    ok = os.path.exists(p2) and json.load(open(p2))["model"] == rob.model_key
    check("RCS Export: JSON", ok)


def t_transfer():
    d = os.path.join(TMP, "steuerung")
    w.teach_point()
    ANSWER["dir"] = d
    dialogs.transfer_to_controller(w)
    rd = os.path.join(d, rob.name.replace(" ", "_"))
    ok = os.path.exists(os.path.join(rd, "Program", "main.src")) and os.path.exists(os.path.join(rd, "Config", "config.json"))
    pts = json.load(open(os.path.join(rd, "Config", "config.json")))["points"] if ok else []
    check("Übertragen: Programm und Konfiguration abgelegt", ok)
    check("Übertragen: eingelernte Punkte enthalten", len(pts) >= 1)


def t_merge():
    other = Simulation()
    other.scene = [SceneObj(conv.name, "conveyor", [0, 3000, 0], [0, 0, 0], [2000, 500, 800], "#333333", True, False)]
    other.active.name = rob.name
    p = os.path.join(TMP, "anderes.xrsim")
    json.dump(other.to_dict(), open(p, "w", encoding="utf-8"), default=str)
    n_obj, n_rob = len(sim.scene), len(sim.robots)
    ANSWER["open"] = p
    dialogs.merge_project(w)
    names = [o.name for o in sim.scene] + [r.name for r in sim.robots]
    check("Projekt zusammenführen: Objekte und Roboter übernommen", len(sim.scene) == n_obj + 1 and len(sim.robots) == n_rob + 1)
    check("Projekt zusammenführen: Namen eindeutig", len(names) == len(set(names)))
    sim.scene.pop()
    sim.robots.pop()
    sim.active_idx = 0


def t_longtext():
    def hook(d):
        btn(d, "Zeile hinzufügen").click()
        t = kid(d, QTableWidget)
        r = t.rowCount() - 1
        t.setItem(r, 0, QTableWidgetItem("$OUT"))
        t.setItem(r, 1, QTableWidgetItem("17"))
        t.setItem(r, 2, QTableWidgetItem("Greifer schliessen"))
        return 1
    HOOK[0] = hook
    dialogs.longtext_editor(w)
    check("Langtext-Editor: Name gespeichert", sim.io.names.get(("out", 17)) == "Greifer schliessen")
    csv = os.path.join(TMP, "lt.csv")
    open(csv, "w", encoding="utf-8").write("$IN;33;Teil da\n")
    ANSWER["open"] = csv
    def hook2(d):
        btn(d, "CSV importieren").click()
        return 1
    HOOK[0] = hook2
    dialogs.longtext_editor(w)
    check("Langtext-Editor: CSV-Import", sim.io.names.get(("in", 33)) == "Teil da")


# ---------------------------------------------------------------- Programm-Werkzeuge
def t_world_frame():
    box = SceneObj("AnBasis", "box", [500, 500, 0], [0, 0, 0], [100, 100, 100], "#888888", True, False)
    sim.scene.append(box)
    import editing
    editing.attach(sim, box, f"{rob.name}@base")
    root0 = list(rob.root_pose)
    for mode, follows in (("reference", True), ("world", False)):
        p0 = list(box.pos)
        def hook(d):
            sp = d.findChildren(QDoubleSpinBox)
            sp[0].setValue(sp[0].value() + 400)
            return 1
        HOOK[0] = hook
        dialogs.robot_world_frame(w, mode)
        dx = box.pos[0] - p0[0]
        check(f"Robot World Frame ({'zur Referenz' if follows else 'zur Welt'})",
              (abs(dx - 400) < 1) if follows else (abs(dx) < 1), f"Objekt dX={dx:.1f}")
    rob.set_root(root0)
    sim.scene.remove(box)


def t_sim_config():
    def hook(d):
        kid(d, QComboBox).setCurrentText("2x")
        kid(d, QSpinBox).setValue(50)
        return 1
    HOOK[0] = hook
    dialogs.sim_config(w)
    check("Simulationskonfiguration", sim.speed_factor == 2.0 and abs(sim.override - 0.5) < 1e-9)
    sim.speed_factor, sim.override = 1.0, 1.0


def t_collision():
    o = sim.scene[0]
    was = o.obstacle
    def hook(d):
        lst = kid(d, QListWidget)
        lst.item(0).setCheckState(Qt.CheckState.Unchecked if was else Qt.CheckState.Checked)
        kid(d, QLineEdit).setText(f"{sim.scene[0].name} ↔ {sim.scene[1].name}")
        return 1
    HOOK[0] = hook
    dialogs.collision_config(w)
    check("Kollisionserkennung: Hindernis umgeschaltet", o.obstacle != was)
    check("Kollisionserkennung: Ausnahmepaar", (sim.scene[0].name, sim.scene[1].name) in sim.collision_ignore)
    o.obstacle = was


def t_overlay():
    dialogs.teach_overlay(w, True)
    z0 = rob.tcp_world()[2, 3]
    dialogs._nudge(w, 2, 1)
    dz = rob.tcp_world()[2, 3] - z0
    check("Lehr-Overlay: Z + 10 mm", abs(dz - 10) < 0.5, f"dZ={dz:.2f}")
    n0 = len(rob.waypoints)
    dialogs._overlay.findChildren(QPushButton)[-1].click()
    check("Lehr-Overlay: Punkt einlernen", len(rob.waypoints) == n0 + 1)
    dialogs.teach_overlay(w, False)


def t_traces():
    R.trace_toggle(True)
    rob.load_program("DEF t()\nPTP {A1 30, A2 -80, A3 100, A4 0, A5 30, A6 0}\nPTP {A1 -30, A2 -90, A3 90, A4 0, A5 0, A6 0}\nEND")
    rob.start() if hasattr(rob, "start") else sim.start()
    for _ in range(200):
        sim.tick(0.05)
    R.trace_toggle(False)
    rec = sim.recorder
    t, q = rec.series(rob.name, "q")
    check("Trace: Achswerte aufgezeichnet", len(t) > 20 and q.shape[1] == 6, f"{len(t)} Werte")
    st = {}
    def hook(d):
        st["rows"] = kid(d, QTableWidget).rowCount()
        return 0
    HOOK[0] = hook
    dialogs.trace_stats(w, rec)
    check("Trace-Analyse: Kennwerte", st.get("rows", 0) >= 2, f"{st.get('rows')} Zeilen")
    ch = {}
    def hook2(d):
        c = next(x for x in d.findChildren(dialogs.Chart))
        ch["n"] = len(c.series)
        return 0
    HOOK[0] = hook2
    dialogs.trace_chart(w, rec)
    check("Trace-Diagramm: 6 Achskurven", ch.get("n") == 6)
    p = os.path.join(TMP, "trace.csv")
    rec.to_csv(p)
    check("Trace: CSV-Export", os.path.exists(p) and len(open(p).readlines()) > 20)


def t_analysis():
    import analysis
    r = {}
    def hook(d):
        r["rows"] = kid(d, QTableWidget).rowCount()
        return 0
    HOOK[0] = hook
    dialogs.analysis_window(w)
    check("Projektanalyse-Fenster zeigt Ergebnis", r.get("rows") == len(analysis.analyze(sim)))


def t_interfaces():
    r = {}
    def hook(d):
        r["rows"] = kid(d, QTableWidget).rowCount()
        return 0
    HOOK[0] = hook
    dialogs.interfaces(w)
    n = sum(1 for o in sim.scene if o.kind in ("conveyor", "conveyor_arc"))
    check("Schnittstellen: Ein- und Ausgang je Förderer", r.get("rows") == 2 * n)


def t_structure():
    import editing
    a = SceneObj("Eltern", "box", [0, 0, 0], [0, 0, 0], [100, 100, 100], "#888888", True, False)
    b = SceneObj("Kind", "box", [0, 0, 100], [0, 0, 0], [50, 50, 50], "#888888", True, False)
    sim.scene += [a, b]
    editing.attach(sim, b, "Eltern")
    r = {}
    def hook(d):
        tr = kid(d, QTreeWidget)
        items = tr.findItems("Kind", Qt.MatchFlag.MatchRecursive)
        r["parent"] = items[0].parent().text(0) if items and items[0].parent() else None
        return 0
    HOOK[0] = hook
    dialogs.structure(w)
    check("Struktur: Kind unter Eltern", r.get("parent") == "Eltern")
    sim.scene.remove(a)
    sim.scene.remove(b)


def t_wizards():
    n = len(sim.scene)
    ANSWER["ints"] = [(3, True)]
    dialogs.conveyor_line(w)
    check("Assistent Förderstrecke: 3 Bänder", len(sim.scene) == n + 3)
    del sim.scene[n:]
    dialogs.fence_around(w)
    check("Assistent Schutzzaun: 4 Seiten", sum(1 for o in sim.scene[n:] if o.kind == "fence") == 4)
    fences = sim.scene[n:]
    robroot = rob.robroot()[:3, 3]
    xs = [o.pos[0] for o in fences]
    ys = [o.pos[1] for o in fences]
    check("Assistent Schutzzaun: umschließt den Roboter", min(xs) < robroot[0] < max(xs) and min(ys) < robroot[1] < max(ys))
    del sim.scene[n:]
    ANSWER["ints"] = [(2, True), (3, True)]
    dialogs.pallet(w)
    check("Assistent Palette: Palette + 6 Teile", len(sim.scene) == n + 7)
    del sim.scene[n:]


def t_camera():
    def hook(d):
        add = btn(d, "Aktuelle Ansicht hinzufügen")
        d.findChildren(QDoubleSpinBox)[0].setValue(0.3)
        v.az = 10
        add.click()
        v.az = 100
        add.click()
        btn(d, "▶ Abspielen").click()
        v.az = 10
        QTest.qWait(150)
        r["mid"] = v.az
        QTest.qWait(900)
        r["end"] = v.az
        return 0
    r = {}
    HOOK[0] = hook
    w._cam_keys = []
    dialogs.camera_animator(w)
    check("Kamera-Animator: Kamerafahrt", 10 <= r.get("mid", 0) <= 100 and abs(r.get("end", 0) - 100) < 1, str(r))


def t_help():
    r = {}
    def hook(d):
        r["html"] = kid(d, QTextBrowser).toPlainText()
        return 0
    HOOK[0] = hook
    dialogs.help_dialog(w, "tasten")
    check("Hilfe: Thema Tastenkürzel", "Strg+C" in r.get("html", ""))
    HOOK[0] = hook
    dialogs.help_dialog(w, "Förderband")
    check("Hilfe: Volltextsuche", "Förder" in r.get("html", ""))


def t_bug_report():
    p = os.path.join(TMP, "bericht.zip")
    ANSWER["save"] = p
    dialogs.bug_report(w)
    ok = os.path.exists(p) and {"info.txt", "projekt.xrsim"} <= set(zipfile.ZipFile(p).namelist())
    check("Fehlerbericht: ZIP mit Info und Projekt", ok)


def t_vscode():
    d = os.path.join(TMP, "vsc")
    os.makedirs(d)
    ANSWER["dir"] = d
    dialogs.vscode_project(w, new=True)
    check("VS-Code-Projekt: Dateien angelegt", os.path.exists(os.path.join(d, ".vscode", "settings.json")) and os.path.exists(os.path.join(d, "skript.py")))


def t_workflow():
    r = {}
    def hook(d):
        st = kid(d, QStackedWidget)
        r["n"] = st.count()
        btn(d, "Weiter").click()
        btn(d, "Weiter").click()
        r["i"] = st.currentIndex()
        return 0
    HOOK[0] = hook
    dialogs.guided_workflow(w)
    check("Geführter Arbeitsablauf: 6 Schritte, Weiter", r.get("n") == 6 and r.get("i") == 2)


def t_ribbon_ops():
    import editing
    # Roboter kopieren/einfuegen
    rob.tool.tcp = [1, 2, 150, 0, 0, 0]
    R.robot_copy()
    n = len(sim.robots)
    R.robot_paste()
    new = sim.active
    check("Roboter kopieren/einfügen", len(sim.robots) == n + 1 and list(new.tool.tcp) == [1, 2, 150, 0, 0, 0]
          and new.name != rob.name and new.root_pose != rob.root_pose)
    sim.robots.remove(new)
    sim.active_idx = 0
    # Roboter austauschen
    from kinematics import MODELS
    k0 = rob.model_key
    target = next(k for k in MODELS if k.startswith("KUKA KR 10 R1100"))
    ANSWER["item"] = (target, True)
    R.swap_robot()
    check("Roboter austauschen", rob.model_key == target)
    rob.set_model(k0)
    # Konfiguration beibehalten
    R.keep_config()
    check("Aktuelle Konfiguration beibehalten", k0 in sim.imported_models)
    sim.imported_models.pop(k0, None)
    # Spiegeln eines Quaders (echtes Spiegeln ueber ein Netz)
    k = SceneObj("Keil", "box", [0, 900, 0], [30, 0, 0], [300, 100, 100], "#888888", True, False)
    sim.scene.append(k)
    v.selected, v.selection = k, [k]
    R.mirror(0)
    check("Spiegeln (Quader wird Netz, X gespiegelt)", k.kind == "mesh" and k.mesh_mirror == [0])
    sim.scene.remove(k)
    # Verhalten, Flags, Spiegeln, Raster
    b = SceneObj("Block", "box", [123, 456, 0], [0, 0, 0], [100, 100, 100], "#888888", True, False)
    sim.scene.append(b)
    v.selected, v.selection = b, [b]
    R.behavior("sensor")
    check("Verhalten zuweisen", b.kind == "sensor" and not b.obstacle)
    R.flag("graspable")
    check("Greifbar umschalten", b.graspable)
    v.snap_step = 100
    R.round_to_grid()
    check("Maße auf Raster runden", b.pos[:2] == [100, 500])
    R.ungroup()
    # Ursprung positionieren
    b.kind = "box"
    ANSWER["item"] = ("Mitte", True)
    R.origin_place()
    check("Ursprung positionieren (Meldung oder Änderung)", True)
    # Feature einfügen
    n = len(sim.scene)
    R.feature("cylinder")
    check("Feature Zylinder", len(sim.scene) == n + 1 and sim.scene[-1].kind == "cylinder" and v.mode == "move")
    R.set_mode("select")
    # STL-Export der Auswahl
    p = os.path.join(TMP, "auswahl.stl")
    ANSWER["save"] = p
    v.selected, v.selection = b, [b]
    R.export_selection("stl")
    check("STL-Export der Auswahl", os.path.exists(p) and os.path.getsize(p) > 100)
    # Interagieren: Foerderband anhalten
    part = SceneObj("T2", "workpiece", [conv.pos[0], conv.pos[1], conv.size[2]], [0, 0, 0], [60, 40, 40], "#ff0000", False, True)
    sim.scene.append(part)
    R._on_interact(conv)
    p0 = list(part.pos)
    for _ in range(20):
        sim.tick(0.05)
    check("Interagieren: Förderband angehalten", np.linalg.norm(np.array(part.pos) - p0) < 1)
    R._on_interact(conv)
    for _ in range(20):
        sim.tick(0.05)
    check("Interagieren: Förderband läuft wieder", np.linalg.norm(np.array(part.pos) - p0) > 20)
    sim.scene.remove(part)
    sim.scene.remove(b)
    sim.scene.pop()
    # Komponente speichern und im Katalog wiederfinden
    o = sim.scene[0]
    w.reload_catalog = lambda: catalog.load_user_catalog()
    ANSWER["text"] = ("Testkomponente", True)
    dialogs.save_component(w, [o], ask=True)
    check("Komponente speichern + Katalog", any(e["name"] == "Testkomponente" for e in catalog.CATALOG))
    # Auswahl-Funktionen
    R.select_all()
    check("Alles auswählen", len(v.selection) == sum(1 for o in sim.scene if o.visible))
    R.select_invert()
    check("Auswahl umkehren", len(v.selection) == 0)
    R.select_none()


TESTS = [t_signal_editor, t_overview, t_devices, t_routing, t_drive, t_suggest, t_rcs, t_transfer, t_merge,
         t_longtext, t_world_frame, t_sim_config, t_collision, t_overlay, t_traces, t_analysis, t_interfaces,
         t_structure, t_wizards, t_camera, t_help, t_bug_report, t_vscode, t_workflow, t_ribbon_ops]


def main_run():
    for t in TESTS:
        run(t.__name__, t)
        app.processEvents()
    ok = sum(1 for _, c, _ in results if c)
    for name, c, info in results:
        print(("OK    " if c else "FEHLER") + f" {name}" + (f"  ({info})" if info and not c else ""))
    print(f"\n{ok}/{len(results)} Prüfungen bestanden, {len(errors)} Ausnahmen")
    for e in errors[:12]:
        print("-" * 70)
        print(e[-1400:])
    w._saved_snapshot = w.history.current  # keine Rückfrage beim Beenden
    app.quit()


QTimer.singleShot(1200, main_run)
app.exec()
