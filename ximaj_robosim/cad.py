"""CAD-Import/-Export und Geometrie-Vereinfachung der Ximaj RoboSim.

Import:  STEP/STP, IGES/IGS (OpenCASCADE ueber cascadio), STL, OBJ, PLY, GLB/GLTF, 3MF, OFF  -> Dreiecksnetz in mm
         DXF -> 2D-Linien (Hallengrundriss)
Export:  3D-Szene als GLB, interaktive HTML-Praesentation, Video MP4
"""
import base64
import io
import os
import numpy as np

CAD_EXT = (".step", ".stp", ".iges", ".igs", ".stl", ".obj", ".ply", ".glb", ".gltf", ".3mf", ".off")


def load_cad(path, tol=0.5, max_tris=None, recenter=True):
    """-> (V Nx3 mm, F Mx3) ; Bauteil liegt mit Unterseite auf Z=0, mittig in X/Y (recenter=False: Originalkoordinaten)"""
    import trimesh
    ext = os.path.splitext(path)[1].lower()
    if ext in (".step", ".stp", ".iges", ".igs"):
        import cascadio
        data = open(path, "rb").read()
        glb = cascadio.load(data, file_type="iges" if ext in (".iges", ".igs") else "step",
                            tol_linear=float(tol), tol_angular=0.5)
        if not glb:
            raise ValueError("CAD-Datei konnte nicht gelesen werden")
        sc = trimesh.load(io.BytesIO(glb), file_type="glb", force="scene")
        m = sc.to_geometry() if hasattr(sc, "to_geometry") else sc.dump(concatenate=True)
        m.apply_scale(1000.0)                      # glTF arbeitet in Metern
    else:
        m = trimesh.load(path, force="mesh")
        if ext in (".glb", ".gltf"):
            m.apply_scale(1000.0)
    V = np.asarray(m.vertices, float)
    F = np.asarray(m.faces, int)
    if max_tris and len(F) > max_tris:
        V, F = simplify(V, F, max_tris)
    if recenter:
        lo, hi = V.min(axis=0), V.max(axis=0)
        V = V - np.array([(lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, lo[2]])
    return V, F


def simplify(V, F, target_tris):
    """Netz auf ca. target_tris Dreiecke reduzieren (fast_simplification, sonst Vertex-Clustering)."""
    target_tris = max(int(target_tris), 12)
    if len(F) <= target_tris:
        return V, F
    try:
        import fast_simplification
        red = 1.0 - target_tris / float(len(F))
        V2, F2 = fast_simplification.simplify(V.astype(np.float32), F.astype(np.int32), target_reduction=red)
        return np.asarray(V2, float), np.asarray(F2, int)
    except Exception:
        pass
    # Vertex-Clustering: Rasterweite schrittweise vergroessern, bis Ziel erreicht
    ext = float(np.max(V.max(axis=0) - V.min(axis=0))) or 1.0
    cell = ext / 200.0
    for _ in range(12):
        key = np.floor((V - V.min(axis=0)) / cell).astype(np.int64)
        _, inv_idx, cnt = np.unique(key, axis=0, return_inverse=True, return_counts=True)
        inv_idx = inv_idx.ravel()
        newV = np.zeros((cnt.size, 3))
        np.add.at(newV, inv_idx, V)
        newV /= cnt[:, None]
        newF = inv_idx[F]
        ok = (newF[:, 0] != newF[:, 1]) & (newF[:, 1] != newF[:, 2]) & (newF[:, 0] != newF[:, 2])
        newF = np.unique(np.sort(newF[ok], axis=1), axis=0) if False else newF[ok]
        if len(newF) <= target_tris:
            return newV, newF
        cell *= 1.5
    return newV, newF


def load_dxf(path):
    """DXF -> Liste von Polylinien [(N,2) mm] (LINE, LWPOLYLINE, POLYLINE, CIRCLE, ARC, SPLINE)."""
    import ezdxf
    from ezdxf import path as ezpath
    doc = ezdxf.readfile(path)
    units = doc.header.get("$INSUNITS", 4)
    scale = {1: 25.4, 2: 304.8, 4: 1.0, 5: 10.0, 6: 1000.0}.get(units, 1.0)
    out = []
    for e in doc.modelspace():
        try:
            p = ezpath.make_path(e)
        except Exception:
            continue
        pts = [(v.x * scale, v.y * scale) for v in p.flattening(distance=2.0)]
        if len(pts) >= 2:
            out.append(np.array(pts, float))
    if not out:
        raise ValueError("Keine darstellbaren Linien in der DXF-Datei gefunden")
    allp = np.vstack(out)
    return out, allp.min(axis=0), allp.max(axis=0)


# ------------------------------------------------------------------ Export
def scene_to_trimesh(sim, robot_detail=True):
    """Szene + Roboter als trimesh.Scene (mm) mit Farben"""
    import trimesh
    from processes import object_mesh
    sc = trimesh.Scene()

    def col(h, a=255):
        h = h.lstrip("#")
        return [int(h[i:i + 2], 16) for i in (0, 2, 4)] + [a]
    for o in sim.scene:
        if not o.visible or o.kind in ("sensor", "spawner", "sink", "zone", "drawing"):
            continue
        try:
            if o.kind == "conveyor_arc":
                m = trimesh.creation.annulus(r_min=o.radius - o.size[1] / 2, r_max=o.radius + o.size[1] / 2,
                                             height=40, sections=48)
                m.apply_translation([0, (-1 if o.turn_right else 1) * o.radius, o.size[2] - 20])
                m.apply_transform(o.matrix())
                c = o.belt_color
            else:
                m = object_mesh(o)
                c = o.belt_color if o.kind == "conveyor" else o.color
            m.visual.vertex_colors = col(c, int(255 * min(1.0, o.alpha)))
            sc.add_geometry(m, node_name=o.name)
        except Exception:
            continue
    from kinematics import tr
    for r in sim.robots:
        for i, (a, b, rad, nm) in enumerate(r.capsules()):
            L = float(np.linalg.norm(b - a))
            if L < 1:
                continue
            m = trimesh.creation.capsule(height=L, radius=float(rad), count=[16, 16])
            d = (b - a) / L
            m.apply_transform(trimesh.geometry.align_vectors([0, 0, 1], d))
            m.apply_translation((a + b) / 2)
            m.visual.vertex_colors = col("#0e74bb" if nm != "Werkzeug" else "#c3c9d1")
            sc.add_geometry(m, node_name=f"{r.name}_{nm}")
    return sc


def export_html(sim, path, title="Ximaj RoboSim – 3D-Präsentation"):
    """Interaktive 3D-Ansicht als einzelne HTML-Datei (Drehen/Zoomen im Browser, GLB eingebettet)."""
    sc = scene_to_trimesh(sim)
    sc.apply_scale(0.001)                         # glTF in Metern
    import trimesh
    rot = trimesh.transformations.rotation_matrix(-np.pi / 2, [1, 0, 0])   # Z-oben -> Y-oben
    sc.apply_transform(rot)
    glb = sc.export(file_type="glb")
    b64 = base64.b64encode(glb).decode("ascii")
    html = f"""<!doctype html><html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>{title}</title>
<script type="module" src="https://unpkg.com/@google/model-viewer@3.5.0/dist/model-viewer.min.js"></script>
<style>body{{margin:0;font-family:Roboto,Segoe UI,sans-serif;background:#f3f6fa;color:#212529}}
header{{background:linear-gradient(65deg,#061e44 40%,#000);color:#fff;padding:14px 22px;font-size:20px;letter-spacing:1px}}
model-viewer{{width:100vw;height:calc(100vh - 92px);background:#e9ecef}}
footer{{padding:8px 22px;font-size:13px;color:#5d6670}}</style></head><body>
<header>XIMAJ ROBOSIM &nbsp;·&nbsp; {title}</header>
<model-viewer src="data:model/gltf-binary;base64,{b64}" camera-controls shadow-intensity="1" exposure="1.05"
 environment-image="neutral" touch-action="pan-y" alt="Roboterzelle"></model-viewer>
<footer>Erstellt mit Ximaj RoboSim · Ximaj IT-Solutions · Maus: drehen (links), verschieben (rechts), zoomen (Rad)</footer>
</body></html>"""
    open(path, "w", encoding="utf8").write(html)
    return len(html)


def export_mp4(frames, path, fps=20):
    """frames: Liste QImage -> MP4 (H.264) ueber imageio-ffmpeg"""
    import imageio.v2 as imageio
    from PyQt6.QtGui import QImage
    w = imageio.get_writer(path, fps=fps, codec="libx264", quality=8, macro_block_size=16)
    try:
        for img in frames:
            img = img.convertToFormat(QImage.Format.Format_RGB888)
            W, H = img.width() - img.width() % 16, img.height() - img.height() % 16
            img = img.copy(0, 0, W, H)
            ptr = img.constBits()
            ptr.setsize(img.sizeInBytes())
            arr = np.frombuffer(ptr, np.uint8).reshape(H, img.bytesPerLine())[:, :W * 3].reshape(H, W, 3)
            w.append_data(arr.copy())
    finally:
        w.close()
