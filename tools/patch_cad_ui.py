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
    ('''KINDS = ("box", "cylinder", "mesh", "conveyor", "conveyor_arc", "sensor", "spawner", "sink", "workpiece", "zone")''',
     '''KINDS = ("box", "cylinder", "mesh", "conveyor", "conveyor_arc", "sensor", "spawner", "sink", "workpiece", "zone",
         "drawing")'''),
    ('''        self.mesh = None         # (verts Nx3, faces Mx3) lokal
        self.mesh_path = ""''', '''        self.mesh = None         # (verts Nx3, faces Mx3) lokal
        self.mesh_path = ""
        self.mesh_max_tris = 200000
        self.lines = []          # DXF-Grundriss: Liste (N,2) lokal'''),
    ('''              "max_parts", "part_size", "part_color", "mesh_path", "visible", "alpha", "belt_color", "frame_color",''',
     '''              "max_parts", "part_size", "part_color", "mesh_path", "mesh_max_tris", "visible", "alpha", "belt_color",
              "frame_color",'''),
    ('''        if o.mesh_path:
            try:
                o.load_mesh(o.mesh_path)
            except Exception:
                pass
        return o

    def load_mesh(self, path):
        import trimesh
        m = trimesh.load(path, force="mesh")
        m.apply_translation(-m.bounds.mean(axis=0) * np.array([1, 1, 0]) - np.array([0, 0, m.bounds[0][2]]))
        self.mesh = (np.asarray(m.vertices, float), np.asarray(m.faces, int))
        self.mesh_path = path
        ext = m.bounds[1] - m.bounds[0]
        self.size = [float(ext[0]), float(ext[1]), float(ext[2])]
        self.kind = "mesh"''', '''        if o.mesh_path:
            try:
                if o.kind == "drawing":
                    o.load_dxf(o.mesh_path, keep_pos=True)
                else:
                    o.load_mesh(o.mesh_path, o.mesh_max_tris, keep_size=True)
            except Exception:
                pass
        return o

    def load_mesh(self, path, max_tris=200000, keep_size=False):
        """CAD-Datei laden (STEP/IGES/STL/OBJ/PLY/GLB/3MF), Einheit mm, Unterseite auf Z=0"""
        import cad
        V, F = cad.load_cad(path, max_tris=max_tris)
        self.mesh = (V, F)
        self.mesh_path = path
        self.mesh_max_tris = max_tris
        ext = V.max(axis=0) - V.min(axis=0)
        if not keep_size:
            self.size = [float(ext[0]), float(ext[1]), float(ext[2])]
        self.kind = "mesh"

    def simplify_mesh(self, target_tris):
        import cad
        if self.mesh is not None:
            self.mesh = cad.simplify(self.mesh[0], self.mesh[1], target_tris)
            self.mesh_max_tris = int(target_tris)
            self._glcache = None

    def load_dxf(self, path, keep_pos=False):
        import cad
        lines, lo, hi = cad.load_dxf(path)
        c = (lo + hi) / 2
        self.lines = [l - c for l in lines]
        self.mesh_path = path
        self.kind = "drawing"
        self.size = [float(hi[0] - lo[0]), float(hi[1] - lo[1]), 1.0]
        self.obstacle = False
        if not keep_pos:
            self.pos = [float(c[0]), float(c[1]), 0.0]'''),
])

patch("viewer.py", [
    ('''            elif o.kind == "mesh" and o.mesh is not None:''', '''            elif o.kind == "drawing":
                if self._shadow:
                    continue
                glDisable(GL_LIGHTING)
                glLineWidth(1.6)
                glPushMatrix()
                glMultMatrixf(np.ascontiguousarray(M.T, dtype=np.float32))
                glColor4f(*c, 1)
                for pl in o.lines:
                    glBegin(GL_LINE_STRIP)
                    for p in pl:
                        glVertex3f(p[0], p[1], 1.5)
                    glEnd()
                glPopMatrix()
                glEnable(GL_LIGHTING)
            elif o.kind == "mesh" and o.mesh is not None:'''),
])

patch("main.py", [
    ("import processes as proc\n", "import processes as proc\nimport cad\n"),
    ('''        self._act(m, "CAD-Modell importieren (STL/OBJ/PLY/GLB/3MF) …", self.import_cad)
        self._act(m, "Szene als 3D-Datei exportieren (GLB/OBJ/STL) …", self.export_scene3d)''',
     '''        self._act(m, "CAD-Modell importieren (STEP/IGES/STL/OBJ/PLY/GLB/3MF) …", self.import_cad)
        self._act(m, "2D-Hallenlayout importieren (DXF) …", self.import_dxf)
        self._act(m, "Szene als 3D-Datei exportieren (GLB/OBJ/STL) …", self.export_scene3d)
        self._act(m, "3D-Präsentation exportieren (HTML, im Browser drehbar) …", self.export_html)'''),
    ('''        self._act(m, "Animation aufnehmen/stoppen (GIF + PNG-Folge)", self.toggle_record, "Ctrl+R")''',
     '''        self._act(m, "Video aufnehmen/stoppen (MP4 oder GIF)", self.toggle_record, "Ctrl+R")'''),
    ('''        f.addRow("Spawn-Intervall", self.p_int)''', '''        f.addRow("Spawn-Intervall", self.p_int)
        self.p_simpl = self._btn("CAD-Netz vereinfachen …", self.simplify_selected)
        f.addRow(self.p_simpl)'''),
    ('''    def import_cad(self):
        p, _ = QFileDialog.getOpenFileName(self, "CAD-Modell", "", "3D-Modelle (*.stl *.obj *.ply *.glb *.gltf *.3mf *.off)")
        if not p:
            return
        try:
            o = SceneObj(os.path.splitext(os.path.basename(p))[0], "mesh", (600, 0, 0), color="#94a3b8")
            o.load_mesh(p)''', '''    def import_cad(self):
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
                         f"{o.size[0]:.0f}×{o.size[1]:.0f}×{o.size[2]:.0f} mm")'''),
    ('''    def export_scene3d(self):''', '''    def import_dxf(self):
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

    def export_scene3d(self):'''),
    ('''        d = QFileDialog.getExistingDirectory(self, "Ordner für Animation (GIF + PNG-Folge)")
        if not d:
            return
        from PIL import Image''', '''        p, flt = QFileDialog.getSaveFileName(self, "Video speichern", "simulation.mp4", "Video MP4 (*.mp4);;Animiertes GIF (*.gif)")
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
        from PIL import Image'''),
    ('''        imgs[0].save(os.path.join(d, "animation.gif"), save_all=True, append_images=imgs[1:], duration=50, loop=0)''',
     '''        imgs[0].save(p, save_all=True, append_images=imgs[1:], duration=50, loop=0)
        for i in range(len(self.frames)):
            try:
                os.remove(os.path.join(d, f"frame_{i:04d}.png"))
            except OSError:
                pass'''),
])
print("ok")
