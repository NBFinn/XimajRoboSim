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


patch("xrl.py", [
    # '.' als Operator (Feldzugriff nach Index)
    ('''    (?P<op><>|<=|>=|==|[-+*/<>=\\[\\]\\(\\),:{}])''', '''    (?P<op><>|<=|>=|==|[-+*/<>=\\[\\]\\(\\),:{}.])'''),
    ('''            if self.is_("["):
                self.nxt()
                i = self.expr()
                self.expect("]")
                a = ("idx", a, i)''', '''            if self.is_("["):
                self.nxt()
                i = self.expr()
                while self.accept(","):          # mehrdimensional: weitere Indizes ignorieren
                    if not self.is_("]"):
                        self.expr()
                self.expect("]")
                a = ("idx", a, i)
            elif self.is_("."):
                self.nxt()
                a = ("field", a, self.nxt().v)'''),
    ('''        if k == "agg":
            return {kk: self.ev(v, env) for kk, v in e[1].items()}''', '''        if k == "agg":
            return {kk: self.ev(v, env) for kk, v in e[1].items()}
        if k == "field":
            base = self.ev(e[1], env)
            for f in e[2].split("."):
                base = base.get(f, 0) if isinstance(base, dict) else 0
            return base'''),
    ('''        if tgt[0] == "idx":
            base = tgt[1]''', '''        if tgt[0] == "field":
            obj = self.ev(tgt[1], env)
            parts = tgt[2].split(".")
            if isinstance(obj, dict):
                for f in parts[:-1]:
                    obj = obj.setdefault(f, {})
                obj[parts[-1]] = val
            return
        if tgt[0] == "idx":
            base = tgt[1]'''),
    ('''        raise XrlError("Ziel ist kein Positions-/Achsaggregat", 0)''',
     '''        raise XrlError(f"Ziel ist kein Positions-/Achsaggregat (Wert: {str(v)[:40]})", 0)'''),
])

patch("vcmx_import.py", [
    ('''def _read_programs(z, log):
    files = {}''', '''_PRELUDE_RE = None


def _config_prelude(z):
    """Globale Punkte/Variablen aus der System-$config.dat als Datenliste (z. B. XHOME)."""
    import re as _re
    out = []
    for n in z.namelist():
        if n.lower().endswith("$config.dat"):
            t = z.read(n).decode("latin1", "replace")
            for ln in t.splitlines():
                if _re.match(r"\\s*DECL\\s+(?:GLOBAL\\s+)?(E6AXIS|E6POS|AXIS|POS|FRAME|INT|REAL|BOOL)\\s+\\w+\\s*=", ln, _re.I):
                    out.append(ln.strip())
    if not out:
        return ""
    return "DEFDAT CONFIG_PRELUDE\\n" + "\\n".join(out) + "\\nENDDAT\\n"


def _read_programs(z, log):
    files = {}'''),
    ('''            rep["main_program"] = progs[main] + "\\n\\n; ===== weitere Module =====\\n" + "\\n\\n".join(others)''',
     '''            rep["main_program"] = progs[main] + "\\n\\n; ===== weitere Module =====\\n" + "\\n\\n".join(others) \\
                + "\\n\\n; ===== globale Daten aus $config.dat =====\\n" + _config_prelude(z)'''),
])
print("ok")
