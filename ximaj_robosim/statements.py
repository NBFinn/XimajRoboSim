"""Statement-Programmierung: Programme aus Befehlsbausteinen (ohne Code), Erzeugung von XRL.

Ein Statement ist ein dict {"type": ..., Parameter...}. Bloecke (LOOP/IF) werden ueber Start-/End-Statements
gebildet (LOOP ... LOOP_END, IF ... ELSE ... IF_END), damit die Liste flach und einfach editierbar bleibt.
"""

TYPES = {
    # typ: (Anzeigename, Standardparameter)
    "PTP": ("Achsbewegung (PTP)", {"pos": [450, 0, 600, 0, 0, 180], "S": None, "T": None, "E1": None, "vel": 100, "name": ""}),
    "LIN": ("Linearbewegung (LIN)", {"pos": [450, 0, 600, 0, 0, 180], "E1": None, "vel": 1.0, "name": ""}),
    "CIRC": ("Kreisbewegung (CIRC)", {"aux": [450, 100, 600, 0, 0, 180], "pos": [450, 200, 600, 0, 0, 180], "vel": 1.0}),
    "WAIT_TIME": ("Warten (Zeit)", {"sec": 1.0}),
    "WAIT_IN": ("Warten auf Signal", {"kind": "IN", "nr": 1, "value": True}),
    "SET_OUT": ("Ausgang setzen", {"nr": 1, "value": True}),
    "PULSE": ("Impuls ausgeben", {"nr": 1, "sec": 0.5}),
    "GRIP": ("Greifer schließen", {"nr": 1}),
    "RELEASE": ("Greifer öffnen", {"nr": 1}),
    "LOOP": ("Schleife (n-mal)", {"count": 3}),
    "LOOP_END": ("Ende Schleife", {}),
    "LOOP_FOREVER": ("Endlosschleife", {}),
    "IF": ("Wenn Signal …", {"kind": "IN", "nr": 1, "value": True}),
    "ELSE": ("Sonst", {}),
    "IF_END": ("Ende Wenn", {}),
    "VEL": ("Geschwindigkeit", {"cp": 1.0, "ptp": 100}),
    "CALL": ("Unterprogramm aufrufen", {"name": "unterprogramm"}),
    "MSG": ("Meldung", {"text": "Hallo"}),
    "COMMENT": ("Kommentar", {"text": "Kommentar"}),
    "HALT": ("Anhalten (HALT)", {}),
}
OPENERS = {"LOOP": "LOOP_END", "LOOP_FOREVER": "LOOP_END", "IF": "IF_END"}


def new(t, **kw):
    d = {"type": t}
    d.update({k: (list(v) if isinstance(v, list) else v) for k, v in TYPES[t][1].items()})
    d.update(kw)
    return d


def _pos(p, S=None, T=None, E1=None):
    s = f"{{X {p[0]:.2f}, Y {p[1]:.2f}, Z {p[2]:.2f}, A {p[3]:.2f}, B {p[4]:.2f}, C {p[5]:.2f}"
    if S is not None and T is not None:
        s += f", S {int(S)}, T {int(T)}"
    if E1 is not None:
        s += f", E1 {float(E1):.2f}"
    return s + "}"


def label(st):
    """Kurztext fuer die Listenanzeige"""
    t = st["type"]
    p = st.get("pos")
    nm = (st.get("name") or "").strip()
    if t in ("PTP", "LIN"):
        tag = f" {nm}" if nm else ""
        e = f"  E1 {st['E1']:.0f}" if st.get("E1") is not None else ""
        v = f"{st['vel']:.0f} %" if t == "PTP" else f"{st['vel']:.2f} m/s"
        return f"{t}{tag}   X {p[0]:.0f}  Y {p[1]:.0f}  Z {p[2]:.0f}  A {p[3]:.0f}  B {p[4]:.0f}  C {p[5]:.0f}{e}   ·  {v}"
    if t == "CIRC":
        return f"CIRC   über X {st['aux'][0]:.0f} Y {st['aux'][1]:.0f} Z {st['aux'][2]:.0f}  →  X {p[0]:.0f} Y {p[1]:.0f} Z {p[2]:.0f}"
    if t == "WAIT_TIME":
        return f"Warte {st['sec']:.2f} s"
    if t == "WAIT_IN":
        return f"Warte bis ${st['kind']}[{st['nr']}] = {'EIN' if st['value'] else 'AUS'}"
    if t == "SET_OUT":
        return f"$OUT[{st['nr']}] = {'EIN' if st['value'] else 'AUS'}"
    if t == "PULSE":
        return f"Impuls $OUT[{st['nr']}] für {st['sec']:.2f} s"
    if t == "GRIP":
        return f"Greifer schließen ($OUT[{st['nr']}])"
    if t == "RELEASE":
        return f"Greifer öffnen ($OUT[{st['nr']}])"
    if t == "LOOP":
        return f"Wiederhole {st['count']}×"
    if t == "LOOP_FOREVER":
        return "Wiederhole endlos"
    if t == "LOOP_END":
        return "Ende Wiederholung"
    if t == "IF":
        return f"Wenn ${st['kind']}[{st['nr']}] = {'EIN' if st['value'] else 'AUS'}"
    if t == "ELSE":
        return "Sonst"
    if t == "IF_END":
        return "Ende Wenn"
    if t == "VEL":
        return f"Geschwindigkeit  Bahn {st['cp']:.2f} m/s · Achsen {st['ptp']:.0f} %"
    if t == "CALL":
        return f"Unterprogramm  {st['name']}()"
    if t == "MSG":
        return f"Meldung: {st['text']}"
    if t == "COMMENT":
        return f"// {st['text']}"
    if t == "HALT":
        return "HALT"
    return t


def indents(stmts):
    """Einrueckung je Statement fuer die Anzeige"""
    out, d = [], 0
    for st in stmts:
        t = st["type"]
        if t in ("LOOP_END", "IF_END", "ELSE"):
            d = max(0, d - 1)
        out.append(d)
        if t in ("LOOP", "LOOP_FOREVER", "IF", "ELSE"):
            d += 1
    return out


def validate(stmts):
    """-> Liste Fehlertexte (Blockstruktur)"""
    errs, stack = [], []
    for i, st in enumerate(stmts):
        t = st["type"]
        if t in OPENERS:
            stack.append((t, i))
        elif t == "ELSE":
            if not stack or stack[-1][0] != "IF":
                errs.append(f"Baustein {i + 1}: 'Sonst' ohne 'Wenn'")
        elif t in ("LOOP_END", "IF_END"):
            if not stack:
                errs.append(f"Baustein {i + 1}: '{TYPES[t][0]}' ohne Anfang")
                continue
            o, _ = stack.pop()
            if OPENERS[o] != t:
                errs.append(f"Baustein {i + 1}: '{TYPES[t][0]}' passt nicht zu '{TYPES[o][0]}'")
    for o, i in stack:
        errs.append(f"Baustein {i + 1}: '{TYPES[o][0]}' ist nicht geschlossen")
    return errs


def generate(stmts, prog_name="statements"):
    """-> (XRL-Text, Zeilennummer -> Statement-Index)"""
    lines = [f"; erzeugt aus Statements (Ximaj RoboSim)", f"DEF {prog_name}()", "  DECL INT ximaj_i1, ximaj_i2, ximaj_i3"]
    linemap = {}
    depth = 1
    loopvar = 0
    stack = []
    for idx, st in enumerate(stmts):
        t = st["type"]
        if t in ("LOOP_END", "IF_END", "ELSE"):
            depth = max(1, depth - 1)
        ind = "  " * depth

        def add(s):
            lines.append(ind + s)
            linemap[len(lines)] = idx
        if t == "PTP":
            add(f"BAS(#PTP_PARAMS, {float(st.get('vel', 100)):.1f})")
            add(f"PTP {_pos(st['pos'], st.get('S'), st.get('T'), st.get('E1'))}")
        elif t == "LIN":
            add(f"$VEL_CP = {float(st.get('vel', 1.0)):.3f}")
            add(f"LIN {_pos(st['pos'], None, None, st.get('E1'))}")
        elif t == "CIRC":
            add(f"$VEL_CP = {float(st.get('vel', 1.0)):.3f}")
            add(f"CIRC {_pos(st['aux'])}, {_pos(st['pos'])}")
        elif t == "WAIT_TIME":
            add(f"WAIT SEC {float(st['sec']):.3f}")
        elif t == "WAIT_IN":
            add(f"WAIT FOR ${st['kind']}[{int(st['nr'])}] == {'TRUE' if st['value'] else 'FALSE'}")
        elif t == "SET_OUT":
            add(f"$OUT[{int(st['nr'])}] = {'TRUE' if st['value'] else 'FALSE'}")
        elif t == "PULSE":
            add(f"PULSE($OUT[{int(st['nr'])}], TRUE, {float(st['sec']):.3f})")
        elif t == "GRIP":
            add(f"$OUT[{int(st['nr'])}] = TRUE")
            add("WAIT SEC 0.2")
        elif t == "RELEASE":
            add(f"$OUT[{int(st['nr'])}] = FALSE")
            add("WAIT SEC 0.2")
        elif t == "LOOP":
            loopvar = min(loopvar + 1, 3)
            stack.append(("FOR", loopvar))
            add(f"FOR ximaj_i{loopvar} = 1 TO {int(st['count'])}")
            depth += 1
        elif t == "LOOP_FOREVER":
            stack.append(("LOOP", 0))
            add("LOOP")
            depth += 1
        elif t == "LOOP_END":
            kind, v = stack.pop() if stack else ("FOR", 0)
            add("ENDFOR" if kind == "FOR" else "ENDLOOP")
            if kind == "FOR":
                loopvar = max(0, loopvar - 1)
        elif t == "IF":
            stack.append(("IF", 0))
            add(f"IF ${st['kind']}[{int(st['nr'])}] == {'TRUE' if st['value'] else 'FALSE'} THEN")
            depth += 1
        elif t == "ELSE":
            add("ELSE")
            depth += 1
        elif t == "IF_END":
            if stack:
                stack.pop()
            add("ENDIF")
        elif t == "VEL":
            add(f"$VEL_CP = {float(st['cp']):.3f}")
            add(f"BAS(#PTP_PARAMS, {float(st['ptp']):.1f})")
        elif t == "CALL":
            add(f"{st['name']}()")
        elif t == "MSG":
            add(f'MSG "{st["text"]}"')
        elif t == "COMMENT":
            add(f"; {st['text']}")
        elif t == "HALT":
            add("HALT")
    lines.append("END")
    return "\n".join(lines) + "\n", linemap
