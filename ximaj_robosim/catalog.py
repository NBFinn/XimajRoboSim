"""Komponenten-Katalog der Ximaj RoboSim - eigene, parametrische Bauteile (keine Fremd-CAD-Daten).

Eintragsarten:
  obj    -> eine oder mehrere Szene-Objekte (Liste von Specs)
  tool   -> Werkzeug-Preset (TCP, Greifer-Ausgang, Radius)
  robot  -> Robotermodell
  cell   -> komplette Beispielzelle (Modell, Objekte, Werkzeug, Programm)
Eigene Eintraege: JSON-Dateien in %APPDATA%/XimajRoboSim/catalog/*.json (Liste von Eintraegen gleicher Form),
z. B. {"cat":"Meine Teile","name":"Kiste","desc":"...","kind":"obj","data":[{"name":"Kiste","kind":"box","size":[400,300,200]}]}
"""
import glob
import json
import os

from kinematics import MODELS

CATALOG = []


def E(cat, name, desc, kind, data):
    CATALOG.append({"cat": cat, "name": name, "desc": desc, "kind": kind, "data": data})


def O(name, kind="box", size=(100, 100, 100), color="#8a9bb8", off=(0, 0, 0), rot=(0, 0, 0), obstacle=True,
      graspable=False, alpha=1.0, io=0, speed=200.0, interval=4.0, max_parts=20, style=""):
    return dict(name=name, kind=kind, size=list(size), color=color, off=list(off), rot=list(rot), obstacle=obstacle,
                graspable=graspable, alpha=alpha, io=io, speed=speed, interval=interval, max_parts=max_parts, style=style)


# ------------------------------------------------------------------ Roboter
for _k, _m in MODELS.items():
    _maker = getattr(_m, "maker", None)
    E(f"Roboter · {_maker}" if _maker else "Roboter", _k,
      f"6-Achs-Knickarmroboter · Reichweite {_m.reach:.0f} mm · Nutzlast {_m.payload:g} kg"
      + (" · Kinematik nach Herstellerdatenblatt, ohne Gewähr" if _maker and _maker != "Eigene" else ""), "robot", _k)

# ------------------------------------------------------------------ Werkzeuge
_T = lambda tcp, out, rng, rad: {"tcp": tcp, "grip_out": out, "grip_range": rng, "radius": rad}
E("Werkzeuge", "Parallelgreifer", "Greift kleine Teile; Schließen über $OUT[1]", "tool", {"name": "Parallelgreifer", **_T([0, 0, 140, 0, 0, 0], 1, 60, 22)})
E("Werkzeuge", "Sauggreifer (Vakuum)", "Saugt flache Teile an; Vakuum über $OUT[1]", "tool", {"name": "Sauggreifer", **_T([0, 0, 90, 0, 0, 0], 1, 40, 35)})
E("Werkzeuge", "Zangengreifer groß", "Für große Teile, hohe Greifreichweite", "tool", {"name": "Zangengreifer", **_T([0, 0, 220, 0, 0, 0], 1, 120, 45)})
E("Werkzeuge", "Schweißbrenner", "TCP an der Drahtspitze, 30° geneigt (ohne Greifer)", "tool", {"name": "Schweißbrenner", **_T([0, 0, 280, 0, 30, 0], 0, 0, 16)})
E("Werkzeuge", "Klebedüse", "Dosierdüse für Kleben/Dichten (ohne Greifer)", "tool", {"name": "Klebedüse", **_T([0, 0, 130, 0, 0, 0], 0, 0, 12)})
E("Werkzeuge", "Frässpindel", "Bearbeitungsspindel, großer Durchmesser", "tool", {"name": "Frässpindel", **_T([0, 0, 220, 0, 0, 0], 0, 0, 55)})
E("Werkzeuge", "Messspitze", "Tastspitze zum Einlernen von Punkten", "tool", {"name": "Messspitze", **_T([0, 0, 110, 0, 0, 0], 0, 0, 8)})

# ------------------------------------------------------------------ Fördertechnik
E("Fördertechnik", "Förderband 1,0 m", "Gurtband, läuft mit $OUT[n] (0 = immer an)", "obj",
  [O("Band1m", "conveyor", (1000, 300, 300), "#475569", obstacle=True, io=2)])
E("Fördertechnik", "Förderband 1,5 m", "Gurtband, 1500 mm lang", "obj",
  [O("Band1.5m", "conveyor", (1500, 400, 350), "#475569", obstacle=True, io=2)])
E("Fördertechnik", "Förderband 3,0 m", "Langes Zuführband", "obj",
  [O("Band3m", "conveyor", (3000, 500, 400), "#475569", obstacle=True, io=2)])
E("Fördertechnik", "Rollenbahn 2,0 m", "Rollenbahn (Bewegung wie Band)", "obj",
  [O("Rollenbahn", "conveyor", (2000, 600, 500), "#64748b", obstacle=True, io=2, speed=300, style="roller")])
E("Fördertechnik", "Teile-Zuführung (Spawner)", "Erzeugt im Intervall Teile (greifbar)", "obj",
  [O("Zufuhr", "spawner", (100, 100, 100), "#f5b83d", obstacle=False, interval=4.0)])
E("Fördertechnik", "Senke (Teile-Abnahme)", "Entfernt ankommende Teile und zählt den Durchsatz", "obj",
  [O("Senke", "sink", (400, 400, 300), "#16a34a", obstacle=False)])
E("Roboter", "Linearachse 4 m (für aktiven Roboter)", "Roboter fährt auf einer 4-m-Bodenschiene (E1)", "track",
  {"min": 0, "max": 4000, "vmax": 1500})
E("Roboter", "Linearachse 8 m (für aktiven Roboter)", "Roboter fährt auf einer 8-m-Bodenschiene (E1)", "track",
  {"min": 0, "max": 8000, "vmax": 2000})
_FARBEN = {"ROT": 2, "GRUEN": 3, "BLAU": 4, "GELB": 5, "WEISS": 6}
E("Fördertechnik", "Farbsensor", "Erkennt die Teilefarbe: $IN[2] rot, $IN[3] grün, $IN[4] blau, $IN[5] gelb, $IN[6] weiß; $IN[7] Teil erkannt", "obj",
  [{**O("Farbsensor", "color_sensor", (40, 300, 150), "#22d3c5", obstacle=False), "color_outs": dict(_FARBEN), "detected": 7, "trigger": 0}])
E("Fördertechnik", "Farbanzeige (Signalleuchte)", "Leuchtet in der Farbe, deren Eingang aktiv ist ($IN[2] … $IN[6] wie Farbsensor)", "obj",
  [{**O("Farbanzeige", "lamp", (120, 120, 260), "#33373d"), "inputs": dict(_FARBEN)}])
E("Werkstücke", "Zuführung mit Zufallsfarben", "Erzeugt Teile in zufälliger Farbe (rot, grün, blau, gelb, weiß)", "obj",
  [{**O("Zufuhr bunt", "spawner", (100, 100, 100), "#f5b83d", obstacle=False, interval=4.0),
    "colors": ["#e61f1a", "#26bf40", "#1a59f2", "#ffd91a", "#f7f7f7"]}])
E("Fördertechnik", "Lichtschranke / Endlagensensor", "Setzt $IN[1], wenn ein Teil im Feld ist", "obj",
  [O("Sensor1", "sensor", (40, 300, 150), "#22d3c5", obstacle=False, io=1)])

# ------------------------------------------------------------------ Zellenbau
E("Zellenbau", "Sicherheitszaun 2 m", "Schutzgitter-Segment, halbtransparent, Hindernis", "obj",
  [O("Zaun", "fence", (2000, 20, 1800), "#f5b83d", obstacle=True, alpha=0.3)])
E("Zellenbau", "Sicherheitszaun-Käfig 4×4 m", "Vier Zaunsegmente um die Zelle", "obj",
  [O("Zaun_N", "fence", (4000, 20, 1800), "#f5b83d", off=(0, 2000, 0), alpha=0.25),
   O("Zaun_S", "fence", (4000, 20, 1800), "#f5b83d", off=(0, -2000, 0), alpha=0.25),
   O("Zaun_O", "fence", (20, 4000, 1800), "#f5b83d", off=(2000, 0, 0), alpha=0.25),
   O("Zaun_W", "fence", (20, 4000, 1800), "#f5b83d", off=(-2000, 0, 0), alpha=0.25)])
E("Zellenbau", "Roboter-Sockel 300 mm", "Podest unter dem Roboter (Fuß auf 300 mm setzen)", "obj",
  [O("Sockel300", "box", (500, 500, 300), "#334155", style="pedestal")])
E("Zellenbau", "Roboter-Sockel 600 mm", "Hoher Sockel", "obj", [O("Sockel600", "box", (600, 600, 600), "#334155", style="pedestal")])
E("Zellenbau", "Schaltschrank", "Steuerungsschrank (Hindernis)", "obj", [O("Schaltschrank", "box", (800, 600, 1900), "#94a3b8", style="cabinet")])
E("Zellenbau", "Arbeitstisch", "Stabiler Tisch 1200×800", "obj", [O("Tisch", "box", (1200, 800, 800), "#64748b", style="table")])
E("Zellenbau", "Spannvorrichtung", "Vorrichtung zur Werkstückaufnahme", "obj",
  [O("Vorrichtung", "box", (300, 300, 120), "#475569", style="fixture"), O("Anschlag", "box", (20, 300, 60), "#22d3c5", off=(-150, 0, 120))])
E("Zellenbau", "Euro-Palette", "1200×800×144 mm, Zielfläche zum Palettieren", "obj", [O("Palette", "box", (1200, 800, 144), "#b08968", style="pallet")])
E("Zellenbau", "Gitterbox", "1200×800×900 Behälter", "obj", [O("Gitterbox", "box", (1200, 800, 900), "#94a3b8", style="gitterbox")])
E("Zellenbau", "Regal", "Lagerregal 1500×500×2000", "obj", [O("Regal", "box", (1500, 500, 2000), "#64748b", style="shelf")])
E("Zellenbau", "Säule / Pfosten", "Rundsäule Ø 300", "obj", [O("Säule", "cylinder", (300, 300, 2500), "#64748b", style="column")])
E("Zellenbau", "Lichtgitter-Zone", "Warnfeld (Zone, kein Hindernis)", "obj", [O("Lichtgitter", "zone", (1500, 100, 1200), "#ef4444", obstacle=False)])

# ------------------------------------------------------------------ Werkstücke
E("Werkstücke", "Quader 60×40×40", "Standardteil, greifbar", "obj", [O("Teil", "workpiece", (60, 40, 40), "#f5b83d", obstacle=False, graspable=True)])
E("Werkstücke", "Würfel 80", "Würfel 80 mm", "obj", [O("Würfel", "workpiece", (80, 80, 80), "#60a5fa", obstacle=False, graspable=True)])
E("Werkstücke", "Platte 300×200×10", "Blechplatte", "obj", [O("Platte", "workpiece", (300, 200, 10), "#cbd5e1", obstacle=False, graspable=True)])
E("Werkstücke", "Zylinder Ø60", "Rundteil/Dose", "obj", [O("Dose", "cylinder", (60, 60, 120), "#34d399", obstacle=False, graspable=True)])
E("Werkstücke", "Karton 400×300×200", "Großer Karton", "obj", [O("Karton", "workpiece", (400, 300, 200), "#d4a373", obstacle=False, graspable=True, style="carton")])

# ------------------------------------------------------------------ Beispielzellen
_PNP = """; Pick & Place
DEF pick_place()
  DECL INT i
  DECL POS pHome
  pHome = {X 450, Y 0, Z 600, A 0, B 0, C 180}
  $VEL_CP = 1.0
  PTP pHome
  FOR i = 1 TO 3
    PTP {X 450, Y 250, Z 350, A 0, B 0, C 180}
    LIN {X 450, Y 250, Z 45, A 0, B 0, C 180}
    $OUT[1] = TRUE
    WAIT SEC 0.3
    LIN {X 450, Y 250, Z 350, A 0, B 0, C 180}
    PTP {X 450, Y -250, Z 350, A 0, B 0, C 180}
    LIN {X 450, Y -250, Z 45, A 0, B 0, C 180}
    $OUT[1] = FALSE
    WAIT SEC 0.3
    LIN {X 450, Y -250, Z 350, A 0, B 0, C 180}
  ENDFOR
  PTP pHome
END
"""
_CONV = """; Förderband-Zelle: Teil erkennen, greifen, ablegen
DEF conveyor_cell()
  DECL INT n
  $VEL_CP = 1.5
  $OUT[2] = TRUE
  PTP {X 800, Y 0, Z 900, A 0, B 0, C 180}
  FOR n = 0 TO 4
    WAIT FOR $IN[1]
    $OUT[2] = FALSE
    PTP {X 1200, Y -600, Z 600, A 0, B 0, C 180}
    LIN {X 1200, Y -600, Z 325, A 0, B 0, C 180}
    $OUT[1] = TRUE
    WAIT SEC 0.3
    LIN {X 1200, Y -600, Z 600, A 0, B 0, C 180}
    $OUT[2] = TRUE
    PTP {X 780+n*70, Y 600, Z 400, A 0, B 0, C 180}
    LIN {X 780+n*70, Y 600, Z 45, A 0, B 0, C 180}
    $OUT[1] = FALSE
    WAIT SEC 0.3
    LIN {X 780+n*70, Y 600, Z 400, A 0, B 0, C 180}
  ENDFOR
  PTP {X 800, Y 0, Z 900, A 0, B 0, C 180}
END
"""
_PAL = """; Palettierzelle: 6 Teile von der Ablage auf die Palette (3 x 2)
DEF palettieren()
  DECL INT i, r, c
  $VEL_CP = 1.5
  PTP {X 600, Y 0, Z 700, A 0, B 0, C 180}
  FOR i = 0 TO 5
    PTP {X 450+i*80, Y -450, Z 300, A 0, B 0, C 180}
    LIN {X 450+i*80, Y -450, Z 45, A 0, B 0, C 180}
    $OUT[1] = TRUE
    WAIT SEC 0.2
    LIN {X 450+i*80, Y -450, Z 300, A 0, B 0, C 180}
    r = i / 3
    c = i MOD 3
    PTP {X 620+c*90, Y 450+r*70, Z 300, A 0, B 0, C 180}
    LIN {X 620+c*90, Y 450+r*70, Z 125, A 0, B 0, C 180}
    $OUT[1] = FALSE
    WAIT SEC 0.2
    LIN {X 620+c*90, Y 450+r*70, Z 300, A 0, B 0, C 180}
  ENDFOR
  PTP {X 600, Y 0, Z 700, A 0, B 0, C 180}
END
"""

E("Beispielzellen", "Pick & Place (Tisch)", "Roboter setzt ein Teil mehrfach von A nach B um", "cell", {
    "model": "XR-9 (0.9 m, 6 kg)", "program": _PNP, "tool": "Parallelgreifer",
    "objs": [O("Tisch", "box", (600, 1000, 20), "#64748b", off=(500, 0, 0)),
             O("Teil1", "workpiece", (60, 40, 40), "#f5b83d", off=(450, 250, 20), obstacle=False, graspable=True),
             O("Ablage", "box", (120, 120, 20), "#334155", off=(450, -250, 0), obstacle=False)]})
E("Beispielzellen", "Förderband mit Lichtschranke", "Zuführung → Band → Sensor → Roboter legt auf Ablage", "cell", {
    "model": "XR-20 (2.0 m, 16 kg)", "program": _CONV, "tool": "Parallelgreifer",
    "objs": [O("Band", "conveyor", (1400, 300, 300), "#475569", off=(700, -600, 0), io=2),
             O("Zufuhr", "spawner", (100, 100, 100), "#f5b83d", off=(100, -600, 305), obstacle=False, interval=4.0, max_parts=8),
             O("Sensor", "sensor", (40, 300, 150), "#22d3c5", off=(1200, -600, 375), obstacle=False, io=1),
             O("Ablage", "box", (600, 300, 20), "#334155", off=(950, 600, 0), obstacle=False)]})
_pal_parts = [O(f"Teil{i + 1}", "workpiece", (60, 40, 40), "#f5b83d", off=(450 + i * 80, -450, 20), obstacle=False, graspable=True)
              for i in range(6)]
E("Beispielzellen", "Palettierzelle 3×2", "Sechs Teile werden auf eine Palette gesetzt", "cell", {
    "model": "XR-20 (2.0 m, 16 kg)", "program": _PAL, "tool": "Parallelgreifer",
    "objs": [O("Zuführtisch", "box", (700, 160, 20), "#64748b", off=(700, -450, 0)),
             O("Palette", "box", (400, 300, 100), "#b08968", off=(760, 520, 0)),
             *_pal_parts]})


# ------------------------------------------------------------------ Nutzerkatalog
def user_dirs():
    d = [os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "XimajRoboSim", "catalog")]
    here = os.path.join(os.path.dirname(os.path.abspath(__file__)), "catalog_extra")
    return d + [here]


def load_user_catalog():
    n = 0
    for d in user_dirs():
        for f in sorted(glob.glob(os.path.join(d, "*.json"))):
            try:
                for e in json.load(open(f, encoding="utf8")):
                    e.setdefault("cat", "Eigene Teile")
                    e.setdefault("desc", "Eigener Katalogeintrag")
                    if e.get("kind") == "obj":
                        # Zusatzfelder (Farbausgaenge, Signale, Farben) erhalten
                        e["data"] = [{**s, **O(**{k: v for k, v in s.items() if k in O.__code__.co_varnames})} for s in e["data"]]
                    CATALOG.append(e)
                    n += 1
            except Exception as ex:
                print("Katalogdatei fehlerhaft:", f, ex)
    return n


# ------------------------------------------------------------------ Anwenden
def apply(sim, entry, at=(800.0, 0.0, 0.0)):
    """Fuehrt einen Katalogeintrag aus. -> Anzahl hinzugefuegter Objekte oder Textmeldung"""
    from sim import SceneObj
    k = entry["kind"]
    if k == "robot":
        sim.set_model(entry["data"])
        return f"Robotermodell {entry['data']}"
    if k == "track":
        t = entry["data"]
        sim.set_track(e_min=t["min"], e_max=t["max"], vmax=t.get("vmax", 1500), lift=True)
        return "Linearachse"
    if k == "tool":
        t = dict(entry["data"])
        sim.tool.name = t.get("name", sim.tool.name)
        sim.tool.tcp = list(t["tcp"])
        sim.tool.grip_out = t["grip_out"]
        sim.tool.grip_range = t["grip_range"]
        sim.tool.radius = t["radius"]
        return f"Werkzeug {sim.tool.name}"
    specs = entry["data"] if k == "obj" else entry["data"]["objs"]
    base = (0, 0, 0) if k == "cell" else at
    if k == "cell":
        if hasattr(sim, "clear_robots"):
            sim.clear_robots()
        sim.set_model(entry["data"]["model"])
        sim.scene = []
        sim.src = entry["data"]["program"]
        tool = next((e for e in CATALOG if e["kind"] == "tool" and e["name"] == entry["data"].get("tool")), None)
        if tool:
            apply(sim, tool)
    out = []
    for s in specs:
        o = SceneObj(s["name"], s["kind"], [base[i] + s["off"][i] for i in range(3)], s["rot"], s["size"], s["color"],
                     s["obstacle"], s["graspable"])
        o.alpha = s.get("alpha", 1.0)
        o.io = s.get("io", 0)
        o.speed = s.get("speed", 200.0)
        o.interval = s.get("interval", 4.0)
        o.max_parts = s.get("max_parts", 20)
        o.style = s.get("style", "")
        for key in ("color_outs", "detected", "trigger", "inputs", "colors"):
            if key in s:
                setattr(o, key, s[key])
        sim.scene.append(o)
        out.append(o)
    sim.reset()
    return out
