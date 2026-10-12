"""Ximaj Copilot: Layout und Simulation per Texteingabe (deutsch, lokal, regelbasiert).

Beispiele:
  füge ein förderband 3 m bei x 1500 y -800 hinzu      |  tisch bei 800, 0
  neuer roboter xr-20 bei x 2500 y 0                   |  roboter xr-15   (Modell des aktiven Roboters)
  linearachse 6 m                                      |  zaun um die zelle
  verschiebe tisch nach x 900 y 200                    |  drehe band1 um 90 grad   |  lösche palette
  starte simulation | stopp | pause | reset            |  geschwindigkeit 50 %  |  zeit 5x
  beispielzelle palettieren                            |  erreichbarkeit prüfen  |  hilfe
"""
import re

from kinematics import MODELS

NUM = r"(-?\d+(?:[.,]\d+)?)"

HELP = ("Ich verstehe zum Beispiel:\n"
        "• füge ein Förderband 3 m bei x 1500 y -800 hinzu\n"
        "• Tisch / Palette / Sensor / Senke / Zuführung / Säule / Schaltschrank bei 800, 0\n"
        "• neuer Roboter XR-20 bei x 2500 y 0   ·   Roboter XR-15   ·   Linearachse 6 m\n"
        "• Zaun um die Zelle   ·   Beispielzelle Palettieren / Förderband / Pick\n"
        "• verschiebe Tisch nach x 900 y 200   ·   drehe Band1 um 90 Grad   ·   lösche Palette\n"
        "• starte Simulation · Stopp · Pause · Reset · Geschwindigkeit 50 % · Zeit 5x\n"
        "• Erreichbarkeit prüfen · Werkzeug Sauggreifer")

OBJECTS = {
    "förderband": ("Fördertechnik", "Förderband 1,5 m"), "band": ("Fördertechnik", "Förderband 1,5 m"),
    "rollenbahn": ("Fördertechnik", "Rollenbahn 2,0 m"), "sensor": ("Fördertechnik", "Lichtschranke / Endlagensensor"),
    "lichtschranke": ("Fördertechnik", "Lichtschranke / Endlagensensor"), "senke": ("Fördertechnik", "Senke (Teile-Abnahme)"),
    "zuführung": ("Fördertechnik", "Teile-Zuführung (Spawner)"), "spawner": ("Fördertechnik", "Teile-Zuführung (Spawner)"),
    "tisch": ("Zellenbau", "Arbeitstisch"), "palette": ("Zellenbau", "Euro-Palette"), "säule": ("Zellenbau", "Säule / Pfosten"),
    "schaltschrank": ("Zellenbau", "Schaltschrank"), "regal": ("Zellenbau", "Regal"), "gitterbox": ("Zellenbau", "Gitterbox"),
    "sockel": ("Zellenbau", "Roboter-Sockel 600 mm"), "vorrichtung": ("Zellenbau", "Spannvorrichtung"),
    "zaun": ("Zellenbau", "Sicherheitszaun 2 m"), "teil": ("Werkstücke", "Quader 60×40×40"),
    "werkstück": ("Werkstücke", "Quader 60×40×40"), "karton": ("Werkstücke", "Karton 400×300×200"),
}
CELLS = {"palett": "Palettierzelle 3×2", "förder": "Förderband mit Lichtschranke", "pick": "Pick & Place (Tisch)"}


def _f(s):
    return float(s.replace(",", "."))


def _length_mm(t):
    m = re.search(NUM + r"\s*(mm|cm|m)\b", t)
    if not m:
        return None
    v = _f(m.group(1))
    return v * {"mm": 1, "cm": 10, "m": 1000}[m.group(2)]


def _xy(t):
    mx = re.search(r"\bx\s*[=:]?\s*" + NUM, t)
    my = re.search(r"\by\s*[=:]?\s*" + NUM, t)
    mz = re.search(r"\bz\s*[=:]?\s*" + NUM, t)
    if mx or my:
        return (_f(mx.group(1)) if mx else 0.0, _f(my.group(1)) if my else 0.0, _f(mz.group(1)) if mz else None)
    m = re.search(r"\b(?:bei|nach|auf|an)\s+" + NUM + r"\s*[,;/ ]\s*" + NUM, t)
    if m:
        return (_f(m.group(1)), _f(m.group(2)), None)
    return None


def _model(t):
    m = re.search(r"xr\s*-?\s*(\d+)", t)
    if not m:
        return None
    for k in MODELS:
        if k.lower().startswith(f"xr-{m.group(1)} "):
            return k
    return None


def _find_obj(win, t):
    names = sorted(((o.name.lower(), o) for o in win.sim.scene), key=lambda x: -len(x[0]))
    for n, o in names:
        if n and n in t:
            return o
    return None


def execute(win, text):
    """Fuehrt einen Befehl aus. -> Antworttext"""
    import catalog
    t = " " + text.lower().strip().rstrip(".!") + " "
    sim = win.sim
    if not t.strip():
        return "Schreib mir, was ich tun soll – z. B. „füge ein Förderband 3 m bei x 1500 y -800 hinzu“."
    if re.search(r"\b(hilfe|help|was kannst du)\b", t):
        return HELP
    # --- Simulation steuern
    if re.search(r"\b(starte|start|los|abspielen)\b", t) and "zelle" not in t:
        win.run_prog()
        return "Simulation gestartet."
    if re.search(r"\b(stopp|stop|anhalten|halt)\b", t):
        sim.stop_all()
        return "Alle Roboter angehalten (STOP 0)."
    if re.search(r"\bpause\b", t):
        sim.pause_all()
        return "Pausiert."
    if re.search(r"\b(reset|zurücksetzen)\b", t):
        win.reset_all()
        return "Zurückgesetzt."
    m = re.search(r"(geschwindigkeit|override)\D*" + NUM + r"\s*%?", t)
    if m:
        v = max(1, min(100, int(_f(m.group(2)))))
        win.ovr.setValue(v)
        return f"Override auf {v} % gesetzt."
    m = re.search(r"\b(zeit|zeitraffer|simulationszeit)\D*" + NUM + r"\s*x", t)
    if m:
        f = _f(m.group(2))
        sim.speed_factor = f
        if win.spd.findText(f"{f:g}x") >= 0:
            win.spd.setCurrentText(f"{f:g}x")
        return f"Simulationszeit {f:g}×."
    # --- Beispielzellen
    if "beispielzelle" in t or "zelle laden" in t:
        for key, nm in CELLS.items():
            if key in t:
                e = next(e for e in catalog.CATALOG if e["name"] == nm)
                catalog.apply(sim, e)
                win.sync_from_sim()
                win.editor.setPlainText(sim.src)
                return f"Beispielzelle „{nm}“ geladen."
        return "Welche Beispielzelle? Palettieren, Förderband oder Pick & Place."
    # --- Analyse
    if "erreichbar" in t:
        win.check_scene_reach()
        win.bottom.setCurrentIndex(4)
        return "Erreichbarkeit geprüft – Ergebnis im Reiter „Analyse“."
    # --- Werkzeug
    if "werkzeug" in t or "greifer" in t and "füge" not in t:
        for e in catalog.CATALOG:
            if e["kind"] == "tool" and e["name"].split()[0].lower() in t:
                catalog.apply(sim, e)
                win.sync_from_sim()
                return f"Werkzeug „{e['name']}“ für {sim.active.name} gesetzt."
    # --- Roboter
    model = _model(t)
    if re.search(r"\b(neuer|weiterer|zusätzlicher|zweiter|noch einen?)\b.*\broboter\b", t) or \
            ("roboter" in t and re.search(r"\b(füge|hinzu|platziere|setze .* bei)\b", t) and _xy(t)):
        pos = _xy(t)
        win.add_robot(model)
        if pos:
            r = sim.active
            r.set_root([pos[0], pos[1], r.root_pose[2]] + list(r.root_pose[3:]))
            win.sync_from_sim()
        return f"{sim.active.name} ({sim.active.model.name}) eingesetzt" + (f" bei X {pos[0]:.0f}, Y {pos[1]:.0f}." if pos else ".")
    if model and "roboter" in t:
        sim.set_model(model)
        win.sync_from_sim()
        return f"{sim.active.name} ist jetzt ein {model}."
    if "linearachse" in t or "verfahrschiene" in t:
        if re.search(r"\b(ohne|entfern|lösch|aus)\b", t):
            sim.active.set_track(None)
            win.sync_from_sim()
            return "Linearachse entfernt."
        L = _length_mm(t) or 4000.0
        sim.active.set_track(e_min=0, e_max=L, vmax=1500, lift=True)
        win.sync_from_sim()
        return f"{sim.active.name} fährt jetzt auf einer {L / 1000:g}-m-Linearachse."
    # --- Zaun um die Zelle
    if "zaun" in t and re.search(r"\b(um|rund|komplett|käfig)\b", t):
        xs = [o.pos[0] for o in sim.scene] + [r.root_pose[0] for r in sim.robots]
        ys = [o.pos[1] for o in sim.scene] + [r.root_pose[1] for r in sim.robots]
        reach = max(r.model.reach for r in sim.robots)
        cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
        w = (max(xs) - min(xs)) + 2 * reach + 600
        h = (max(ys) - min(ys)) + 2 * reach + 600
        from sim import SceneObj
        for nm, pos, size in (("Zaun_N", (cx, cy + h / 2, 0), (w, 20, 1800)), ("Zaun_S", (cx, cy - h / 2, 0), (w, 20, 1800)),
                              ("Zaun_O", (cx + w / 2, cy, 0), (20, h, 1800)), ("Zaun_W", (cx - w / 2, cy, 0), (20, h, 1800))):
            o = SceneObj(nm, "fence", pos, (0, 0, 0), size, "#f5b83d", True, False)
            sim.scene.append(o)
        win.refresh_scene_list()
        return f"Schutzzaun {w / 1000:.1f} × {h / 1000:.1f} m um die Zelle gesetzt."
    # --- Objekt verschieben / drehen / loeschen
    if re.search(r"\b(verschiebe|bewege|setze)\b", t):
        o = _find_obj(win, t)
        pos = _xy(t)
        if o and pos:
            o.pos[0], o.pos[1] = pos[0], pos[1]
            if pos[2] is not None:
                o.pos[2] = pos[2]
            win.refresh_scene_list()
            return f"„{o.name}“ nach X {pos[0]:.0f}, Y {pos[1]:.0f} verschoben."
    m = re.search(r"\bdrehe\b.*?" + NUM + r"\s*(grad|°)?", t)
    if m:
        o = _find_obj(win, t)
        if o:
            o.rot[0] = (o.rot[0] + _f(m.group(1)) + 180) % 360 - 180
            win.refresh_scene_list()
            return f"„{o.name}“ um {_f(m.group(1)):g}° gedreht."
    if re.search(r"\b(lösche|entferne)\b", t):
        o = _find_obj(win, t)
        if o:
            sim.scene.remove(o)
            win.viewer.selected = None
            win.refresh_scene_list()
            return f"„{o.name}“ gelöscht."
    # --- Objekte einfuegen
    for key, (cat, name) in OBJECTS.items():
        if re.search(r"\b" + key, t):
            e = next((e for e in catalog.CATALOG if e["cat"] == cat and e["name"] == name), None)
            if not e:
                continue
            pos = _xy(t) or (win.viewer.center[0], win.viewer.center[1], None)
            objs = catalog.apply(sim, e, (pos[0], pos[1], 0.0))
            L = _length_mm(t)
            if isinstance(objs, list) and objs:
                o = objs[0]
                if L and o.kind in ("conveyor", "box", "fence") and key in ("förderband", "band", "rollenbahn", "zaun", "tisch"):
                    o.size[0] = L
                m2 = re.search(r"(\d+)\s*(grad|°)", t)
                if m2:
                    o.rot[0] = _f(m2.group(1))
            win.refresh_scene_list()
            label = name.split(" ")[0] if L else name
            return f"{label} bei X {pos[0]:.0f}, Y {pos[1]:.0f} eingefügt" + (f" (Länge {L / 1000:g} m)." if L else ".")
    return "Das habe ich nicht verstanden. Tippe „Hilfe“ für Beispiele."
