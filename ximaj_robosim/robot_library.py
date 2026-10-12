"""Hersteller-Presets und eigene Roboter, ohne Abhaengigkeit zur Kinematik.

mm, Grad, Grad/s, kg; dims = a1,d1,a2,a3,d4,d6. Gerundete Simulation
mit kugelfoermigem Handgelenk, keine kalibrierten Maschinenparameter.
Hersteller-Nullstellungen sind auf A2=-90/A3=90 umgelegt; die Grenzen
anderer Hersteller sind angenaeherte, unabhaengige Simulationsgrenzen.
Gekoppelte Achsgrenzen, Kabeloptionen und Lastdiagramme sind nicht enthalten.
reach ist die Hersteller-Reichweite, nicht die Summe der Gliedlaengen.

Quellen: oeffentliche Datenblaetter/Arbeitsraumzeichnungen der Modellreihen:
https://www.kuka.com/en-hu/products/robotics-systems/industrial-robots/kr-quantec
https://www.kuka.com/-/media/kuka-downloads/imported/8350ff3ca11642998dbdc81dcc2ed44c/0000255784_en.pdf
https://www.abb.com/global/en/areas/robotics/products/robots/articulated-robots
https://www.fanuc.eu/~/media/files/pdf/products/robots/brochures/mbr-00119-ro-product-overview/v-23/robot-brochure-en.pdf
https://www.cz.yaskawa.eu.com/Global%20Assets/Downloads/Brochures_Catalogues/Robotics/MOTOMAN_Robots/GP-Series/Yas_GP_Serie_Gesamt_E.pdf
https://www.staubli.com/global/de/robotics/produkte/industrieroboter/6-achs/tx2-60.html
"""

import json
import math
import os
from pathlib import Path
import tempfile


def _preset(maker, model, dims, limits, vmax, payload, reach):
    return dict(key=f"{maker} {model}", maker=maker, model=model,
                dims=list(dims), limits=[list(pair) for pair in limits],
                vmax=list(vmax), payload=payload, reach=reach)


def _limits(a1, a2, a3, a4, a5, a6):
    return [(-a1, a1), a2, a3, (-a4, a4), (-a5, a5), (-a6, a6)]


PRESETS = [
    _preset("KUKA", "KR 3 R540", [25, 345, 260, 20, 240, 65],
            _limits(170, (-170, 50), (-110, 155), 175, 120, 350), [250, 250, 250, 320, 320, 420], 3, 541),
    _preset("KUKA", "KR 6 R700 sixx", [25, 400, 315, 35, 365, 80],
            _limits(170, (-190, 45), (-120, 156), 185, 120, 350), [360, 300, 360, 381, 388, 615], 6, 706),
    _preset("KUKA", "KR 6 R900 sixx", [25, 400, 455, 35, 420, 80],
            _limits(170, (-190, 45), (-120, 156), 185, 120, 350), [360, 300, 360, 381, 388, 615], 6, 901),
    _preset("KUKA", "KR 10 R1100 sixx", [25, 400, 560, 35, 515, 80],
            _limits(170, (-190, 45), (-120, 156), 185, 120, 350), [300, 225, 225, 381, 311, 492], 10, 1101),
    _preset("KUKA", "KR 10 R1420", [150, 450, 610, 20, 650, 80],
            _limits(170, (-185, 65), (-137, 163), 185, 120, 350), [220, 210, 270, 381, 311, 492], 10, 1420),
    _preset("KUKA", "KR 16 R1610-2", [160, 520, 690, 35, 760, 100],
            _limits(185, (-185, 65), (-138, 175), 350, 130, 350), [200, 175, 190, 360, 360, 630], 16, 1612),
    _preset("KUKA", "KR 20 R1810-2", [160, 520, 790, 35, 860, 100],
            _limits(185, (-185, 65), (-138, 175), 350, 130, 350), [200, 175, 190, 360, 360, 630], 20, 1813),
    _preset("KUKA", "KR 50 R2500", [280, 675, 1150, 50, 1060, 215],
            _limits(185, (-140, -5), (-120, 168), 350, 125, 350), [175, 158, 160, 230, 230, 320], 50, 2500),
    _preset("KUKA", "KR 120 R2700-2", [350, 750, 1150, 55, 1200, 215],
            _limits(185, (-140, -5), (-120, 168), 350, 125, 350), [120, 115, 120, 190, 180, 260], 120, 2701),
    _preset("KUKA", "KR 210 R2700-2", [350, 750, 1150, 55, 1200, 215],
            _limits(185, (-140, -5), (-120, 168), 350, 125, 350), [105, 101, 107, 150, 130, 200], 210, 2701),
    _preset("KUKA", "KR 240 R2900-2", [350, 750, 1250, 55, 1300, 215],
            _limits(185, (-140, -5), (-120, 168), 350, 125, 350), [100, 90, 95, 150, 130, 200], 240, 2901),
    _preset("KUKA", "KR 300 R2500 ultra", [350, 750, 1000, 55, 1100, 215],
            _limits(185, (-140, -5), (-120, 155), 350, 122.5, 350), [105, 101, 107, 122, 113, 175], 300, 2495),
    _preset("KUKA", "KR 500 R2830", [500, 1045, 1300, 55, 1025, 250],
            _limits(185, (-130, 20), (-100, 144), 350, 120, 350), [69, 57, 57, 84, 78, 120], 500, 2826),
    # ABB: native A2/A3 zero is shifted to our upright/horizontal HOME.
    _preset("ABB", "IRB 120", [0, 290, 270, 70, 302, 72],
            _limits(165, (-200, 20), (-140, 140), 160, 120, 400), [250, 250, 250, 320, 320, 420], 3, 580),
    _preset("ABB", "IRB 1200-7/0.7", [0, 399, 350, 42, 351, 82],
            _limits(170, (-190, 40), (-110, 160), 270, 130, 400), [288, 240, 297, 400, 405, 600], 7, 703),
    _preset("ABB", "IRB 1600-10/1.45", [150, 486, 700, 110, 600, 65],
            _limits(180, (-180, 60), (-155, 155), 200, 115, 400), [150, 160, 170, 320, 400, 460], 10, 1450),
    _preset("ABB", "IRB 2600-20/1.65", [150, 445, 700, 115, 795, 85],
            _limits(180, (-185, 65), (-90, 165), 400, 120, 400), [175, 175, 175, 360, 360, 500], 20, 1650),
    _preset("ABB", "IRB 4600-60/2.05", [175, 495, 900, 175, 960, 135],
            _limits(180, (-180, 60), (-90, 165), 400, 125, 400), [175, 175, 175, 250, 250, 360], 60, 2050),
    _preset("ABB", "IRB 6700-200/2.60", [320, 780, 1100, 200, 1180, 200],
            _limits(180, (-155, 0), (-90, 160), 300, 130, 360), [100, 90, 90, 170, 120, 190], 200, 2600),
    # FANUC envelopes are expressed about our HOME, not controller zero.
    _preset("FANUC", "LR Mate 200iD", [50, 330, 330, 35, 335, 80],
            _limits(170, (-190, 45), (-115, 180), 190, 125, 360), [450, 380, 520, 550, 545, 1000], 7, 717),
    _preset("FANUC", "M-10iD/12", [75, 450, 640, 40, 700, 100],
            _limits(170, (-190, 45), (-170, 285), 190, 140, 270), [260, 240, 260, 430, 450, 720], 12, 1441),
    _preset("FANUC", "M-20iD/25", [75, 525, 790, 40, 900, 100],
            _limits(170, (-200, 60), (-170, 288), 200, 140, 270), [210, 210, 265, 420, 420, 720], 25, 1831),
    _preset("FANUC", "R-2000iC/165F", [312, 670, 1075, 225, 1280, 215],
            _limits(180, (-150, 0), (-140, 180), 360, 125, 360), [105, 105, 110, 150, 150, 220], 165, 2655),
    # MOTOMAN L/U axes use HOME offsets -90/+90 respectively.
    _preset("Yaskawa", "GP8", [40, 330, 345, 40, 340, 80],
            _limits(170, (-155, 55), (-155, 130), 190, 135, 360), [455, 385, 520, 550, 550, 1000], 8, 727),
    _preset("Yaskawa", "GP25", [155, 450, 760, 40, 795, 100],
            _limits(180, (-195, 65), (4, 250), 200, 150, 455), [210, 210, 265, 420, 420, 885], 25, 1730),
    _preset("Yaskawa", "GP180", [325, 650, 1150, 200, 1250, 200],
            _limits(180, (-150, 0), (-90, 165), 360, 130, 360), [100, 90, 97, 120, 120, 190], 180, 2702),
    # TX2 represented by an ideal spherical wrist; transverse offsets omitted.
    _preset("Staubli", "TX2-60", [0, 375, 290, 0, 310, 70],
            _limits(180, (-217.5, 37.5), (-55, 235), 270, 120, 270), [400, 400, 400, 500, 500, 800], 4.5, 670),
]

USER_FILE = (Path(os.environ["APPDATA"]) / "XimajRoboSim" / "robots.json"
             if os.environ.get("APPDATA") else Path.home() / ".ximaj_robosim" / "robots.json")
FAMILIES = {}


def _families(users=()):
    FAMILIES.clear()
    for entry in PRESETS + list(users):
        keys = FAMILIES.setdefault(entry["maker"], [])
        if entry["key"] not in keys:
            keys.append(entry["key"])


def _number(value):
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def validate(entry):
    """Alle Schemafehler als deutsche Meldungen; auch fuer kaputte JSON-Werte."""
    if not isinstance(entry, dict):
        return ["Der Roboter muss ein Objekt sein."]
    errors = []
    for field in ("key", "maker", "model"):
        if not isinstance(entry.get(field), str) or not entry[field].strip():
            errors.append(f"{field}: Ein nicht leerer Text ist erforderlich.")
    dims = entry.get("dims")
    if not isinstance(dims, (list, tuple)) or len(dims) != 6 or not all(_number(v) for v in dims):
        errors.append("dims: Sechs endliche Zahlen sind erforderlich.")
    elif dims[2] <= 0 or dims[4] <= 0:
        errors.append("Oberarm a2 und Unterarm d4 muessen groesser als 0 sein.")
    limits = entry.get("limits")
    if (not isinstance(limits, (list, tuple)) or len(limits) != 6
            or any(not isinstance(p, (list, tuple)) or len(p) != 2
                   or not all(_number(v) for v in p) or p[0] >= p[1] for p in limits)):
        errors.append("limits: Sechs endliche Grenzpaare mit Minimum < Maximum sind erforderlich.")
    vmax = entry.get("vmax")
    if (not isinstance(vmax, (list, tuple)) or len(vmax) != 6
            or any(not _number(v) or v <= 0 for v in vmax)):
        errors.append("vmax: Sechs endliche Geschwindigkeiten groesser als 0 sind erforderlich.")
    for field in ("payload", "reach"):
        if not _number(entry.get(field)) or entry[field] < 0:
            errors.append(f"{field}: Eine endliche Zahl groesser oder gleich 0 ist erforderlich.")
    return errors


def _read_user(strict=False):
    try:
        with Path(USER_FILE).open(encoding="utf-8-sig") as stream:
            entries = json.load(stream)
        if not isinstance(entries, list):
            raise ValueError("robots.json muss eine Liste enthalten.")
    except FileNotFoundError:
        return []
    except (OSError, ValueError, RecursionError):
        if strict:
            raise ValueError("robots.json kann nicht gelesen werden; Datei bleibt unveraendert.") from None
        return []
    return [e for e in entries if not validate(e) and e["maker"] == "Eigene"]


def load_user():
    entries = _read_user()
    _families(entries)
    return entries


def _write_user(entries):
    path = Path(USER_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix="robots-", suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(entries, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    _families(entries)


def save_user(entry):
    errors = validate(entry)
    if errors:
        raise ValueError("\n".join(errors))
    entry = dict(entry, maker="Eigene")
    entries = [e for e in _read_user(strict=True) if e["key"] != entry["key"]]
    _write_user(entries + [entry])


def delete_user(key):
    entries = _read_user(strict=True)
    remaining = [e for e in entries if e["key"] != key]
    if len(remaining) != len(entries):
        _write_user(remaining)


def register(models, RobotModel):
    """Modelle hinzufuegen, vorhandene Schluessel unveraendert lassen."""
    added = []
    for entry in PRESETS + load_user():
        if validate(entry) or entry["key"] in models:
            continue
        model = RobotModel(entry["key"], *entry["dims"], entry["limits"],
                           entry["vmax"], entry["payload"])
        model.maker = entry["maker"]
        model.cad = dict(entry.get("cad") or {})       # Glied-Index -> CAD-Datei (Nullstellung, Fusskoordinaten)
        model.paint = entry.get("paint")               # Lackfarbe "#rrggbb" oder None
        models[entry["key"]] = model
        added.append(entry["key"])
    return added


_families()
