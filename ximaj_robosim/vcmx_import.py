"""Import alter Projekte/Modelle (.vcmx / .vcm) in die Ximaj RoboSim.

Nur fuer eigene, rechtmaessig vorhandene Projektdateien (Interoperabilitaet). Es werden keine
Fremd-Geometrien in den Ximaj-Katalog uebernommen; Netzgeometrie wird durch Platzhalter-Koerper ersetzt.

Uebernommen werden:
  * Layout: Komponenten mit Position/Drehung, Grundkoerper (Quader/Zylinder/Kugel) mit Massen
  * Roboter: Gliederlaengen, Achsgrenzen, Achsgeschwindigkeiten, Montageposition -> eigenes Modell
  * Steuerungsdaten: Programme (.src/.dat), Punkte (E6POS/E6AXIS), Werkzeuge/Basen aus _config.dat
"""
import base64
import math
import os
import re
import zipfile
from pathlib import Path
from urllib.parse import unquote, urlparse

import numpy as np

from kinematics import MODELS, RobotModel, mat_to_pose, pose_to_mat, R2D
from rsc_parser import parse, location, unq
from sim import SceneObj, signal_color

STD_COLORS = {
    "white": "#f2f4f7", "black": "#1f2328", "blue": "#2563eb", "red": "#dc2626", "green": "#16a34a",
    "yellow": "#facc15", "orange": "#f97316", "grey": "#9ca3af", "gray": "#9ca3af", "blue_grey": "#64748b",
    "light_aqua": "#a5f3fc", "metal": "#b8bec6", "steel": "#9aa3ad", "aluminum": "#c3c9d1", "aluminium": "#c3c9d1",
    "ral7031": "#4e5754", "ral7035": "#cbd0cc", "ral9005": "#0e0e10", "ral1023": "#f7b500", "ral5015": "#2271b3",
    "transp_red": "#ef4444", "dark_grey": "#374151",
}


def _materials(text):
    """Materialtabelle der Datei: Name -> Hex-Farbe (Diffuse, sonst Ambient)"""
    out = {}
    for m in re.finditer(r'\n\s*Material\s+"([^"]+)"\s*\n\s*\{', text):
        body = text[m.end():m.end() + 700]
        blk = re.search(r"Diffuse\s*\{([^}]*)\}", body) or re.search(r"Ambient\s*\{([^}]*)\}", body)
        if not blk:
            continue
        rgb = []
        for k in ("Red", "Green", "Blue"):
            mm = re.search(k + r"\s+([-\d.eE]+)", blk.group(1))
            rgb.append(float(mm.group(1)) if mm else 0.0)
        out[m.group(1)] = "#%02x%02x%02x" % tuple(int(max(0, min(1, c)) * 255) for c in rgb)
    return out


def _comp_material(comp):
    """Direkte Materialzuweisung einer Komponente (z. B. Material "SORT_ROT")"""
    for c in comp.walk():
        if c.k == "Material" and c.a:
            return unq(c.a)
    return None


def _color(name, mats, default):
    if not name:
        return default
    return mats.get(name) or STD_COLORS.get(name.lower()) or default


SKIP_NAMES = ("workspace", "trace_schema", "synchronization", "safety", "world", "drawing")
NUM = re.compile(r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?")


def _num(s, default=None):
    if s is None:
        return default
    m = NUM.search(str(s))
    return float(m.group()) if m else default


def _var_value(var):
    """Wert einer Variable: direkt ('Value 575') oder als Ausdruck ('Value { Expression "200 {mm}" }')"""
    v = var.find("Value")
    if v is None:
        return None
    if v.a:
        return unq(v.a)
    for c in v.walk():
        if c.k == "Expression":
            return unq(c.a)
    return None


def _vars(node, deep=False):
    out = {}
    spaces = [node.find("VariableSpace"), node.find("NodeVariableSpace")]
    if deep:
        spaces = [n for n in node.walk() if n.k in ("VariableSpace", "NodeVariableSpace")]
    for sp in spaces:
        if sp is None:
            continue
        for v in sp.findall("Variable"):
            nm = v.find("Name")
            if nm is not None and nm.arg() not in out:
                out[nm.arg()] = _var_value(v)
    return out


def _mat(loc):
    return np.array(loc, float).reshape(4, 4).T          # spaltenweise gespeichert


def _expr_matrix(expr):
    """Einfacher Auswerter fuer 'Tx(10).Ty(5).Rz(90)' (nur Zahlenwerte)."""
    M = np.eye(4)
    for fn, arg in re.findall(r"(T[xyz]|R[xyz])\(([^()]*)\)", expr or ""):
        v = _num(arg, 0.0)
        if fn[0] == "T":
            d = [0, 0, 0]
            d["xyz".index(fn[1])] = v
            M = M @ pose_to_mat(*d, 0, 0, 0)
        else:
            a = [0, 0, 0]
            a[{"z": 0, "y": 1, "x": 2}[fn[1]]] = v
            M = M @ pose_to_mat(0, 0, 0, *a)
    return M


# ------------------------------------------------------------------ Geometrie
def _primitives(comp):
    """Grundkoerper einer Komponente mit lokalem Transform -> [(kind, size, M, name)]"""
    out = []

    def rec(node, M):
        cur = M
        for c in node.c:
            if c.k == "Feature":
                t = c.arg()
                v = _vars(c)
                if t == "rTransformFeature":
                    cur = cur @ _expr_matrix(v.get("Expression") or "")
                elif t == "rPrimitiveBoxFeature":
                    s = [_num(v.get("Length"), 100), _num(v.get("Width"), 100), _num(v.get("Height"), 100)]
                    out.append(("box", s, cur.copy(), v.get("Name") or "Quader"))
                elif t == "rPrimitiveCylinderFeature":
                    r = _num(v.get("Radius"), 50)
                    out.append(("cylinder", [2 * r, 2 * r, _num(v.get("Height"), 100)], cur.copy(), v.get("Name") or "Zylinder"))
                elif t == "rPrimitiveSphereFeature" and "Safety" not in (v.get("Name") or ""):
                    r = _num(v.get("Radius"), 50)
                    out.append(("cylinder", [2 * r, 2 * r, 2 * r], cur.copy() @ pose_to_mat(0, 0, -r, 0, 0, 0), v.get("Name") or "Kugel"))
                rec(c, cur)
            elif c.k in ("NodeClass", "ANON"):
                rec(c, cur)
    rec(comp, np.eye(4))
    return out


def _has_geo(comp):
    return any(n.k == "Feature" and n.arg() == "rGeoFeature" for n in comp.walk())


def _guess_kind(name):
    n = name.lower()
    if any(k in n for k in ("farbsensor", "color sensor", "colorsensor", "colour sensor")):
        return "color_sensor"
    if any(k in n for k in ("feeder", "creator", "source", "spawn")):
        return "spawner"
    if "sensor" in n or "lichtschranke" in n:
        return "sensor"
    if any(k in n for k in ("conveyor", "förder", "foerder", "band", "belt", "roller")):
        return "conveyor"
    if "sensor" in n or "lichtschranke" in n:
        return "sensor"
    if "fence" in n or "zaun" in n:
        return "fence"
    if any(k in n for k in ("feeder", "creator", "source", "spawn")):
        return "spawner"
    if any(k in n for k in ("block", "box", "part", "teil", "product", "karton")):
        return "workpiece"
    return "box"


def _size_from_params(v):
    def pick(*keys):
        for k in keys:
            for kk, val in v.items():
                if kk.lower() == k.lower():
                    x = _num(val)
                    if x and x > 0:
                        return x
        return None
    L = pick("ConveyorLength", "Length", "FenceLength", "SizeX", "Laenge")
    W = pick("ConveyorWidth", "Width", "SizeY", "Breite")
    H = pick("ConveyorHeight", "Height", "FenceHeight", "SizeZ", "Hoehe")
    return L, W, H


def _parametric(name, gk, v, M, scene, sensor_no, color=None):
    """Foerderer/Sensoren/Erzeuger aus Komponenten-Parametern"""
    f = lambda k, d=None: _num(v.get(k), d)
    if gk == "conveyor":
        H = f("ConveyorHeight", 800.0)
        W = f("ConveyorWidth", 600.0)
        if f("ConveyorRadius"):
            q = mat_to_pose(M)
            o = SceneObj(name, "conveyor_arc", q[:3], q[3:], [0, W, H], "#c3c9d1", False, False)
            o.radius = f("ConveyorRadius")
            o.angle = f("ConveyorAngle", 90.0)
            o.turn_right = str(v.get("TurnRight", "1")).strip() in ("1", "True", "true")
            o.size[0] = 2 * o.radius + W
            o.speed = f("ConveyorSpeed", 250.0)
            o.feet = int(f("AmountOfFeet", 3) or 3)
            if color:
                o.belt_color = color
            return o
        L = f("ConveyorLength", 1500.0)
        C = M @ pose_to_mat(L / 2, 0, 0, 0, 0, 0)
        q = mat_to_pose(C)
        o = SceneObj(name, "conveyor", q[:3], q[3:], [L, W, H], "#c3c9d1", True, False)
        o.speed = f("ConveyorSpeed", 250.0)
        o.feet = int(f("AmountOfFeet", 2) or 2)
        if color:
            o.belt_color = color
        o.io = 0
        return o
    if gk in ("sensor", "color_sensor"):
        H = f("H", 150.0)
        W = f("ConveyorWidth", 600.0)
        C = M @ pose_to_mat(0, 0, H / 2, 0, 0, 0)
        q = mat_to_pose(C)
        o = SceneObj(name, gk, q[:3], q[3:], [40, W, H], "#22d3c5", False, False)
        o.io = sensor_no if gk == "sensor" else 0
        return o
    if gk == "lamp":
        q = mat_to_pose(M)
        return SceneObj(name, "lamp", q[:3], q[3:], [100, 100, 100], "#64748b", False, False)
    if gk == "spawner":
        # Advanced Creator uses a corner origin; parts leave at belt height
        # on the centre of its outgoing edge, transformed into world space.
        creator_dims = [f("Length_X"), f("Width_Y"), f("Height_Z")]
        C = M
        if all(x is not None and x > 0 for x in creator_dims):
            length, width, height = creator_dims
            C = M @ pose_to_mat(length, width / 2, height, 0, 0, 0)
        q = mat_to_pose(C)
        z = q[2]
        for b in scene:
            if b.kind == "conveyor":
                L = (np.linalg.inv(b.matrix()) @ np.array([q[0], q[1], 0, 1.0]))[:3]
                if abs(L[0]) <= b.size[0] / 2 + 1 and abs(L[1]) <= b.size[1] / 2 + 1:
                    z = max(z, b.top_z() + 5)
        o = SceneObj(name, "spawner", [q[0], q[1], z], q[3:], [100, 100, 100], "#f5b83d", False, False)
        o.interval = max(0.01, f("Creator::Interval", f("Interval", f("CreationInterval", 4.0))) or 4.0)
        dims = [f("ProductsDimension::Block_Length"),
                f("ProductsDimension::Block_Width"), f("ProductsDimension::Block_Height")]
        if all(x is not None and x > 0 for x in dims):
            o.part_size = dims
        material = str(v.get("Creator::Material1", "")).strip('"').lower()
        o.part_color = STD_COLORS.get(material, o.part_color)
        return o
    return None


def _function_name(node):
    return node.name() or _vars(node).get("Name") or ""


def _signals(comp):
    return {_function_name(n) for n in comp.c if n.k == "Functionality" and "Signal" in str(n.arg())} - {""}


def _scripts(comp):
    scripts = []
    for node in comp.c:
        if node.k != 'Functionality' or 'PythonScript' not in str(node.arg()):
            continue
        raw = str(_vars(node).get('Script', ''))
        raw = raw.replace('\\\r\n', '').replace('\\\n', '')
        # Decode RSC escapes once, preserving literal Python backslashes.
        raw = re.sub(r'\\([nrt"\\])', lambda m: {'n': '\n', 'r': '\r', 't': '\t', '"': '"', '\\': '\\'}[m[1]], raw)
        raw = raw.split('# Begin signature block', 1)[0].strip()
        if raw:
            scripts.append(raw)
    return scripts


def _runtime_data(comp):
    signals = {}
    for node in comp.c:
        if node.k != 'Functionality' or not str(node.arg()).startswith('rSim') or 'Signal' not in str(node.arg()):
            continue
        name = _function_name(node)
        values = _vars(node)
        kind = next((kind for token, kind in (('String', 'string'), ('Integer', 'int'), ('Int', 'int'),
                                             ('Real', 'real')) if token in str(node.arg())), 'bool')
        raw = values.get('Value', values.get('InitialValue', '' if kind == 'string' else 0))
        value = str(raw) if kind == 'string' else bool(_num(raw, 0)) if kind == 'bool' else _num(raw, 0)
        signals[name] = {'kind': kind, 'value': value, 'AutomaticReset': str(values.get('AutomaticReset', '1')).lower() not in ('0', 'false')}
    props = {name: _num(value, value) for name, value in _vars(comp).items()}
    return {'signals': signals, 'scripts': _scripts(comp), 'properties': props}


def _product_templates(comp, project_path, log):
    values = _vars(comp)
    templates = []
    if str(values.get('Creator::Costumized', '0')) == '1':
        count = max(1, int(_num(values.get('Creator::PartAmount'), 1)))
        for i in range(1, min(count, 5) + 1):
            uri = str(values.get(f'Creator::Part{i}', ''))
            parsed = urlparse(uri)
            if not uri or parsed.scheme not in ('', 'file') or parsed.netloc:
                continue
            path = Path(unquote(parsed.path).lstrip('/') if parsed.scheme == 'file' else uri)
            if not path.is_absolute():
                path = Path(project_path).parent / path
            try:
                with zipfile.ZipFile(path) as archive:
                    names = sorted((n for n in archive.namelist() if n.endswith('.rsc')), key=lambda n: (n != 'layout.rsc', n))
                    root = parse(archive.read(names[0]).decode('utf8', 'replace'))
                resource = next(n for n in root.walk() if n.k == 'Node' and n.arg() == 'rSimResource')
                templates.append(_runtime_data(resource))
            except (OSError, zipfile.BadZipFile, StopIteration, KeyError, IndexError) as exc:
                log.append(f"Warnung: Teilskript aus '{path.name}' nicht gelesen: {exc}")
    else:
        resources = [n for n in comp.walk() if n is not comp and n.k == 'Node' and n.arg() == 'rSimResource']
        templates = [_runtime_data(n) for n in resources if _scripts(n)]
    return templates


def _signal_role(obj, signal):
    if re.fullmatch(r"Outputs_Port_([1-9]\d*)", signal):
        return "src" if int(signal.rsplit('_', 1)[1]) <= 1024 else None
    if re.fullmatch(r"Inputs_Port_([1-9]\d*)", signal):
        return "dst" if int(signal.rsplit('_', 1)[1]) <= 1024 else None
    if obj is None:
        return None
    if obj.kind == "sensor" and signal == "SensorBooleanSignal":
        return "src"
    if obj.kind == "color_sensor":
        if signal == "ColorTrigger":
            return "dst"
        if signal_color(signal) is not None or signal in ("ColorDetected", "Detected"):
            return "src"
    if obj.kind == "spawner" and signal == "CreationSignal":
        return "dst"
    if obj.kind in ("conveyor", "conveyor_arc") and signal == "Engine":
        return "dst"
    if obj.kind == "lamp" and signal_color(signal) is not None:
        return "dst"
    return None


def _read_links(comps, sim, log, append=False):
    """Resolve full names, including underscores; interface pointer is a hint only."""
    known = {c.name(): _signals(c) for c in comps if c.name()}
    objects = {o.name: o for o in sim.scene}
    robots = {r.name for r in sim.robots}
    if not append:
        sim.links = []
    seen = {(tuple(x['src']), tuple(x['dst'])) for x in sim.links}
    for comp in comps:
        own = comp.name()
        for node in comp.c:
            if node.k != "Functionality" or node.arg() != "rSimInterface":
                continue
            name = _function_name(node)
            if not name.startswith("Conn_"):
                continue
            body = name[5:]
            pointer = _vars(node, deep=True).get('Signal')
            matches = []
            for other, signals in known.items():
                for signal in signals:
                    suffix = '_' + other + '_' + signal
                    if body.endswith(suffix):
                        own_signal = body[:-len(suffix)]
                        if own_signal not in known.get(own, set()) and pointer in known.get(own, set()):
                            own_signal = pointer
                        if own_signal in known.get(own, set()):
                            matches.append((len(suffix), own_signal, other, signal))
            if not matches:
                log.append(f"Warnung: Verbindung '{own}: {name}' nicht auflösbar")
                continue
            _, own_signal, other, signal = max(matches)
            a, b = (own, own_signal), (other, signal)
            roles = [_signal_role(objects.get(ep[0]), ep[1]) if ep[0] in objects or ep[0] in robots else None for ep in (a, b)]
            if roles == ['dst', 'src']:
                a, b = b, a
            elif roles != ['src', 'dst']:
                log.append(f"Warnung: Verbindung '{own}: {name}' nicht unterstützt")
                continue
            if (a, b) not in seen:
                sim.links.append({'src': a, 'dst': b})
                seen.add((a, b))
            log.append(f"Verbindung: {a[0]}.{a[1]} → {b[0]}.{b[1]}")
    sim.wire_links()


def _script_colors(comp):
    """Extract literal RGB tuples and material names as data, never run scripts."""
    colors = []
    for node in comp.walk():
        if node.k != 'Functionality' or node.arg() != 'rPythonScript':
            continue
        script = '\n'.join(_scripts(type(comp)(comp.k, comp.a, [node])))
        # Only colour/material list assignments; do not treat arbitrary vectors as RGB.
        lists = re.findall(r'(?:FARBEN|COLORS|COLOURS|MATERIALS|farben|colors|colours|materials)\s*=\s*\[([^\]]*)\]', script)
        for data in lists:
            for match in re.finditer(r'\(\s*(\d+(?:\.\d+)?)\s*,\s*(\d+(?:\.\d+)?)\s*,\s*(\d+(?:\.\d+)?)\s*\)', data):
                rgb = tuple(float(x) for x in match.groups())
                if all(0 <= x <= 1 for x in rgb):
                    colors.append('#%02x%02x%02x' % tuple(round(x * 255) for x in rgb))
            if not colors:
                colors.extend(STD_COLORS[x.lower()] for x in re.findall(r'[\'"]([^\'"]+)[\'"]', data) if x.lower() in STD_COLORS)
    return list(dict.fromkeys(colors))


def _creator_colors(comp, mats, project_path, log):
    v = _vars(comp)
    colors = _script_colors(comp)
    count = max(1, int(_num(v.get('Creator::Products'), 1)))
    colors += [_color(v.get(f'Creator::Material{i}'), mats, None) for i in range(1, min(count, 5) + 1)]
    if str(v.get('Creator::Costumized', '0')) == '1':
        colors = []
        count = max(1, int(_num(v.get('Creator::PartAmount'), 1)))
        for i in range(1, min(count, 5) + 1):
            uri = str(v.get(f'Creator::Part{i}', ''))
            if not uri:
                continue
            parsed = urlparse(uri)
            if parsed.scheme not in ('', 'file') or parsed.netloc:
                log.append(f"Warnung: Externe Teilreferenz nicht gelesen: {uri}")
                continue
            path = Path(unquote(parsed.path).lstrip('/') if parsed.scheme == 'file' else uri)
            if not path.is_absolute():
                path = Path(project_path).parent / path
            try:
                with zipfile.ZipFile(path) as z:
                    text = z.read(next(n for n in z.namelist() if n.endswith('.rsc'))).decode('utf8', 'replace')
                colors += _script_colors(parse(text))
            except (OSError, zipfile.BadZipFile, StopIteration, KeyError) as e:
                log.append(f"Warnung: Teilfarben aus '{path.name}' nicht gelesen: {e}")
    return list(dict.fromkeys(c for c in colors if c))


# ------------------------------------------------------------------ Roboter
def _robot_from_comp(comp, name, gen_limits):
    v = _vars(comp, deep=True)
    if "L01Z" not in v:
        return None
    g = lambda k, d=0.0: _num(v.get(k), d)
    a1, d1 = g("L12X"), g("L01Z")
    a2 = math.hypot(g("L23X"), g("L23Z"))
    a3 = -g("L34X")
    d4 = g("L34Z") + g("L45Z")
    d6 = g("L56Z") or 100.0
    speeds = [float(x) for x in re.findall(r"MaxSpeed\s*\n?\s*Value\s+([-\d.]+)", "")] or None
    vmax = []
    for n in comp.walk():
        if n.k == "Name" and n.arg() == "MaxSpeed":
            pass
    # MaxSpeed-Variablen in Reihenfolge der Achsen
    for sp in [n for n in comp.walk() if n.k in ("VariableSpace", "NodeVariableSpace")]:
        for var in sp.findall("Variable"):
            nm = var.find("Name")
            if nm is not None and nm.arg() == "MaxSpeed":
                x = _num(_var_value(var))
                if x:
                    vmax.append(x)
    vmax = (vmax + [180, 160, 180, 250, 250, 360])[:6] if vmax else [180, 160, 180, 250, 250, 360]
    limits = gen_limits or [(-185, 185), (-140, -5), (-120, 155), (-350, 350), (-125, 125), (-350, 350)]
    pm = re.search(r"(\d+)\s*R\s*\d", name)
    payload = int(pm.group(1)) if pm else 0
    return dict(dims=[a1, d1, a2, a3, d4, d6], limits=[list(map(float, l)) for l in limits], vmax=vmax, payload=payload)


def _generation_info(z, log):
    """Achsgrenzen/Montage aus generationinfo.xml (Base64) – falls vorhanden."""
    for n in z.namelist():
        if n.endswith("generationinfo.xml"):
            t = z.read(n).decode("utf8", "replace")
            m = re.search(r"<RobotGenerationDetector>([^<]+)<", t)
            if not m:
                continue
            try:
                s = base64.b64decode(m.group(1)).decode("utf8", "replace")
            except Exception:
                continue
            lim = re.findall(r"\((-?[\d.]+):(-?[\d.]+)\)", s.split("\n")[0])
            if len(lim) >= 6:
                log.append("Achsgrenzen aus Steuerungsdaten übernommen")
                return [(float(a), float(b)) for a, b in lim[:6]]
    return None


# ------------------------------------------------------------------ Steuerungsdaten
_KEYS = ("X", "Y", "Z", "A", "B", "C")


def _agg(txt):
    return {k.upper(): float(v) for k, v in re.findall(r"\b([XYZABC])\s+(-?[\d.]+(?:E[-+]?\d+)?)", txt, re.I)}


def _read_config(z, sim, log):
    for n in z.namelist():
        if n.lower().endswith("system/$config.dat") or n.lower().endswith("/_config.dat") or n.lower().endswith("$config.dat"):
            t = z.read(n).decode("latin1", "replace")
            for kind, table in (("TOOL", sim.tool_table), ("BASE", sim.base_table)):
                names = {int(a): b for a, b in re.findall(kind + r'_NAME\[(\d+),\]\s*=\s*"([^"]*)"', t)}
                for idx, body in re.findall(kind + r"_DATA\[(\d+)\]\s*=\s*\{([^}]*)\}", t):
                    f = _agg(body)
                    fr = [f.get(k, 0.0) for k in _KEYS]
                    nm = names.get(int(idx), "").strip()
                    if any(abs(x) > 1e-9 for x in fr) or nm:
                        table[str(int(idx))] = {"name": nm or f"{kind} {idx}", "frame": fr}
            log.append(f"Werkzeuge: {len(sim.tool_table)}, Basen: {len(sim.base_table)} aus {os.path.basename(n)}")
            return


_PRELUDE_RE = None


def _config_prelude(z):
    """Globale Punkte/Variablen aus der System-$config.dat als Datenliste (z. B. XHOME)."""
    import re as _re
    out = []
    for n in z.namelist():
        if n.lower().endswith(("$config.dat", "/_config.dat")):
            t = z.read(n).decode("latin1", "replace")
            for ln in t.splitlines():
                if _re.match(r"\s*(?:DECL\s+)?(?:GLOBAL\s+)?(E6AXIS|E6POS|AXIS|POS|FRAME|FDAT|PDAT|LDAT|INT|REAL|BOOL)\s+\w+\s*=", ln, _re.I):
                    s = ln.strip()
                    out.append(s if s.upper().startswith("DECL") else "DECL " + s)
    if not out:
        return ""
    return "DEFDAT CONFIG_PRELUDE\n" + "\n".join(out) + "\nENDDAT\n"


def _read_programs(z, log):
    files = {}
    for n in z.namelist():
        ln = n.lower()
        if not ln.endswith((".src", ".dat", ".sub")) or "/krc/" not in ln:
            continue
        rel = ln.split("/krc/", 1)[1]
        if any(rel.startswith(p) for p in ("r1/system/", "r1/tp/", "r1/mada/", "steu/", "r1/cfg")) or "/tp/" in rel:
            continue
        if rel.endswith("$config.dat"):
            continue
        files[rel] = z.read(n).decode("latin1", "replace")
    mods = {}
    for rel, txt in files.items():
        base = rel.rsplit(".", 1)[0]
        mods.setdefault(base, {})[rel.rsplit(".", 1)[1]] = txt
    progs = {}
    for base, parts in sorted(mods.items()):
        txt = (parts.get("dat", "") + "\n" + parts.get("src", "") + "\n" + parts.get("sub", "")).strip()
        if "DEF" in txt.upper():
            progs[base.replace("r1/", "")] = txt
    log.append(f"Programme/Module: {len(progs)}")
    return progs


def _points_from_programs(progs):
    pts = []
    for name, txt in progs.items():
        for nm, body in re.findall(r"DECL\s+(?:GLOBAL\s+)?E6POS\s+(\w+)\s*=\s*\{([^}]*)\}", txt, re.I):
            f = _agg(body)
            s = re.search(r"\bS\s+(\d+)", body)
            t = re.search(r"\bT\s+(\d+)", body)
            pts.append({"name": f"{nm} ({name.split('/')[-1]})", "pos": [f.get(k, 0.0) for k in _KEYS],
                        "S": int(s.group(1)) if s else 2, "T": int(t.group(1)) if t else 0})
    return pts


def _pick_main(progs):
    if not progs:
        return None
    for pref in ("hauptprogramm", "main", "cell", "program/main"):
        for k in progs:
            if k.split("/")[-1] == pref or k.endswith("/" + pref):
                return k

    def score(k):
        t = progs[k].upper()
        return t.count("PTP ") + t.count("LIN ") + t.count("CIRC ")
    return max(progs, key=score)


def program_source(report, name):
    """Ausgewähltes Startmodul mit Unterprogrammen und globalen Daten bündeln."""
    progs = report["programs"]
    others = [text for key, text in progs.items() if key != name]
    return (progs[name] + "\n\n; ===== weitere Module =====\n" + "\n\n".join(others)
            + "\n\n; ===== globale Daten aus $config.dat =====\n" + report.get("config_prelude", ""))


# ------------------------------------------------------------------ Hauptfunktion
def import_file(sim, path, run_scripts=False):
    log = [f"Import: {path}"]
    rep = {"log": log, "programs": {}, "main_program": None, "scripts": []}
    sim.script_host = None
    sim.run_scripts = bool(run_scripts)
    try:
        z = zipfile.ZipFile(path)
    except zipfile.BadZipFile:
        z = None
    if z is None:
        text = open(path, encoding="utf8", errors="replace").read()
        names = []
    else:
        names = z.namelist()
        rscs = sorted([n for n in names if n.endswith(".rsc")], key=lambda n: (n != "layout.rsc", n))
        text = z.read(rscs[0]).decode("utf8", "replace") if rscs else ""
    root = parse(text)
    mats = _materials(text)
    if mats:
        log.append(f"Materialien/Farben übernommen: {', '.join(list(mats)[:12])}")
    gen_limits = _generation_info(z, log) if z else None

    # Komponenten bestimmen
    world = None
    for n in root.walk():
        if n.k == "Node" and n.arg() == "rSimWorld" and n.name() == "ROOT":
            world = n
            break
    comps = [c for c in (world.c if world else []) if c.k == "Node" and c.arg() == "rSimResource"]
    single = not comps
    if single:
        comps = [n for n in root.c if n.k == "Node"] or [n for n in root.walk() if n.k == "Node" and n.arg() == "rSimResource"][:1]
    # Mounted sensors are child resources (e.g. a light barrier on a conveyor).
    # Keep their parent transform, without importing creator template parts.
    mounted = {}
    additions = []
    def collect(parent, matrix):
        for child in parent.c:
            if child.k != 'Node' or child.arg() != 'rSimResource':
                continue
            loc = location(child)
            world_matrix = matrix @ (_mat(loc) if loc else np.eye(4))
            signals = _signals(child)
            if 'SensorBooleanSignal' in signals or _guess_kind(child.name() or '') == 'color_sensor':
                additions.append(child)
                mounted[id(child)] = world_matrix
            collect(child, world_matrix)
    for comp in comps:
        loc = location(comp)
        collect(comp, _mat(loc) if loc else np.eye(4))
    comps += additions
    new_scene = [] if not single else list(sim.scene)
    robot_done = False
    sensor_no = 1
    for comp in comps:
        name = comp.name() or "Komponente"
        if any(s in name.lower() for s in SKIP_NAMES):
            continue
        loc = location(comp)
        M = mounted.get(id(comp), _mat(loc) if loc else np.eye(4))
        rnode = None
        for n in comp.walk():
            if n.k == "Node" and n.arg() == "rSimResource" and "L01Z" in _vars(n, deep=True):
                rnode = n            # tiefster Treffer = eigentlicher Roboter (z. B. auf Linearachse)
        rb = _robot_from_comp(rnode, rnode.name() or name, gen_limits) if rnode is not None else None
        track = None
        if rb and rnode is not comp:
            sub = location(rnode)
            if sub:
                M = M @ _mat(sub)
            cv = _vars(comp)
            travel = _num(cv.get("Rated_travel")) or _num(cv.get("TravelLength")) or _num(cv.get("Length"))
            if travel:
                # Software-Endschalter wie in der Achse hinterlegt (typisch: -Verfahrweg+200 ... +150)
                lo = -(travel - 200.0) if "Softn_end" in cv else 0.0
                hi = 150.0 if "Softp_end" in cv else travel
                track = (lo, hi)
                log.append(f"'{rnode.name()}' auf Linearachse '{name}': E1 {lo:.0f} … {hi:.0f} mm")
            else:
                log.append(f"'{rnode.name()}' ist auf '{name}' montiert (Zusatzachse ohne Verfahrweg)")
            name = rnode.name() or name
        if rb:
            key = f"Import: {name}"
            MODELS[key] = RobotModel(key, *rb["dims"], rb["limits"], rb["vmax"], rb["payload"])
            sim.imported_models[key] = rb
            if robot_done:
                sim.add_robot(key, name=name)
            sim.set_model(key)
            sim.active.name = name
            p = mat_to_pose(M)
            sim.set_root([float(x) for x in p])
            if track and hasattr(sim, "set_track"):
                sim.set_track(e_min=track[0], e_max=track[1], vmax=1500.0, name="Linearachse")
            robot_done = True
            d = rb["dims"]
            log.append(f"Roboter '{name}': a1={d[0]:.0f} d1={d[1]:.0f} a2={d[2]:.0f} a3={d[3]:.0f} d4={d[4]:.0f} d6={d[5]:.0f} mm, "
                       f"Fuß bei ({p[0]:.0f}, {p[1]:.0f}, {p[2]:.0f})")
            continue
        p = mat_to_pose(M)
        gk = _guess_kind(name)
        v = _vars(comp, deep=False)
        signals = _signals(comp)
        if 'ColorTrigger' in signals and any(signal_color(s) is not None for s in signals):
            gk = 'color_sensor' if 'sensor' in name.lower() else 'lamp'
        elif any(signal_color(s) is not None for s in signals) and gk == 'box':
            gk = 'lamp'
        if gk in ("conveyor", "sensor", "spawner", "color_sensor", "lamp"):
            o = _parametric(name, gk, v, M, new_scene, sensor_no, _color(_comp_material(comp), mats, None))
            if o is not None:
                if o.kind == "sensor":
                    sensor_no += 1
                elif o.kind == 'spawner':
                    o.colors = _creator_colors(comp, mats, path, log)
                    if len(o.colors) == 1:
                        o.part_color = o.colors[0]
                elif o.kind == 'color_sensor':
                    o.color_outs = {s: 0 for s in sorted(signals) if signal_color(s) is not None}
                new_scene.append(o)
                log.append(f"Komponente '{name}': {o.kind} {o.size[0]:.0f}×{o.size[1]:.0f}×{o.size[2]:.0f} mm"
                           + (f", E/A {o.io}" if o.io else "") + (f", {o.speed:.0f} mm/s" if o.kind == "conveyor" else ""))
                continue
        prims = _primitives(comp)
        if prims:
            for kind, size, L, pname in prims:
                W = M @ L
                q = mat_to_pose(W)
                o = SceneObj(f"{name}/{pname}" if len(prims) > 1 else name, kind, q[:3], q[3:], size,
                             _color(_comp_material(comp), mats, "#94a3b8"), True, False)
                gk = _guess_kind(name)
                if gk == "workpiece":
                    o.kind, o.graspable, o.obstacle, o.color = "workpiece", True, False, "#f5b83d"
                new_scene.append(o)
            log.append(f"Komponente '{name}': {len(prims)} Grundkörper")
        else:
            v = _vars(comp, deep=False)
            L_, W_, H_ = _size_from_params(v)
            gk = _guess_kind(name)
            size = [L_ or 400, W_ or 400, H_ or 400]
            kind = {"fence": "fence", "spawner": "spawner"}.get(gk, gk if gk in ("conveyor", "sensor", "workpiece") else "box")
            o = SceneObj(name, kind, p[:3], p[3:], size, _color(_comp_material(comp), mats, "#64748b"),
                         kind in ("box", "conveyor"), kind == "workpiece")
            if gk == "fence":
                o.color = "#f5b83d"
                o.size[2] = o.size[2] if o.size[2] > 500 else 1800.0
            elif kind == "box" and _has_geo(comp):
                o.alpha = 0.55
            new_scene.append(o)
            log.append(f"Komponente '{name}': Platzhalter {kind} {size[0]:.0f}×{size[1]:.0f}×{size[2]:.0f} mm"
                       + (" (Netzgeometrie nicht übernommen)" if _has_geo(comp) else ""))
    sim.scene = new_scene
    for comp in comps:
        name = comp.name()
        data = _runtime_data(comp)
        # A visual component may have multiple imported primitive objects.
        objects = [o for o in sim.scene if o.name == name or o.name.startswith(name + '/')]
        objects += [r for r in sim.robots if r.name == name]
        for obj in objects:
            obj.vc_data = data
            if isinstance(obj, SceneObj):
                obj.vc_component = name
                if obj.kind == 'spawner':
                    obj.product_templates = _product_templates(comp, path, log)
        for source in data['scripts']:
            handlers = re.findall(r'^\s*def\s+(On\w+)\s*\(', source, re.M)
            rep['scripts'].append({'component': name, 'handlers': handlers})
            log.append(f"Skript gefunden: {name} ({', '.join(handlers)})")
        for obj in objects:
            for template in getattr(obj, 'product_templates', []):
                for source in template['scripts']:
                    handlers = re.findall(r'^\s*def\s+(On\w+)\s*\(', source, re.M)
                    rep['scripts'].append({'component': name + '/Produkt', 'handlers': handlers})
    sim.set_active(0)
    _read_links(comps, sim, log, append=single)

    if z is not None:
        _read_config(z, sim, log)
        progs = _read_programs(z, log)
        rep["programs"] = progs
        main = _pick_main(progs)
        rep["config_prelude"] = _config_prelude(z)
        rep["main_name"] = main
        if main:
            rep["main_program"] = program_source(rep, main)
            log.append(f"Hauptprogramm: {main}")
        pts = _points_from_programs(progs)
        if pts:
            sim.waypoints = pts
            log.append(f"Punkte übernommen: {len(pts)}")
        if sim.tool_table:
            n0 = sorted(sim.tool_table, key=int)[0]
            t = sim.tool_table[n0]
            sim.tool.tcp = list(t["frame"])
            sim.tool.name = t["name"]
            log.append(f"Aktives Werkzeug: {t['name']} (TOOL_DATA[{n0}])")
    sim.reset()
    sim.init_scripts()
    if rep["main_program"]:
        sim.active.mode = "xrl"
        sim.load_program(rep["main_program"])
        log.append("Startbereit im XRL-Modus. WAIT FOR wartet auf die tatsächliche E/A-Bedingung; Eingänge unter Bedienung → E/A prüfen.")
    else:
        log.append("Kein Roboterprogramm gefunden: Geometrie/Komponenten importiert; ein Programm muss separat erstellt oder geladen werden.")
    log.append("Fertig. Hinweis: Achs-Vorzeichen und Sonderfunktionen (Interrupts, Trigger, Feldbus) bitte prüfen.")
    return rep
