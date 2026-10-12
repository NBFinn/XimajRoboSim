"""Erweitert xrl.py: tolerantes Parsen, DEFDAT/DEFFCT, #Enums, Punktnotation, BAS-Kompatibilitaet."""
import os
P = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "ximaj_robosim", "xrl.py")
m = open(P, encoding="utf8").read()


def rep(a, b, cnt=1):
    global m
    if a not in m:
        raise SystemExit("NICHT GEFUNDEN:\n" + a[:300])
    m = m.replace(a, b, cnt)


# --- Schluesselwoerter
rep('''    "RETURN", "CONTINUE", "INI", "TRIGGER", "WHEN", "DISTANCE", "DELAY", "DO", "ANOUT", "MSG",
}''', '''    "RETURN", "CONTINUE", "INI", "TRIGGER", "WHEN", "DISTANCE", "DELAY", "DO", "ANOUT", "MSG",
    "DEFDAT", "ENDDAT", "DEFFCT", "ENDFCT",
}''')
# --- Tokenizer: Enums und Punktnotation
rep('''    (?P<id>\\$?[A-Za-z_][A-Za-z_0-9]*)|(?P<str>"[^"\\n]*")|''',
    '''    (?P<enum>\\#[A-Za-z_][A-Za-z_0-9]*)|
    (?P<id>\\$?[A-Za-z_][A-Za-z_0-9]*(?:\\.[A-Za-z_][A-Za-z_0-9]*)*)|(?P<str>"[^"\\n]*")|''')
rep('''        elif k == "str":
            toks.append(Tok("str", v[1:-1], line))''', '''        elif k == "str":
            toks.append(Tok("str", v[1:-1], line))
        elif k == "enum":
            toks.append(Tok("str", v.upper(), line))''')

# --- Parser: tolerant + DEFDAT/DEFFCT + Parameter "name:IN"
rep('''class Parser:
    def __init__(self, toks):
        self.t, self.i = toks, 0''', '''class Parser:
    def __init__(self, toks, lenient=True):
        self.t, self.i = toks, 0
        self.lenient = lenient
        self.warnings = []

    def skipline(self):
        while self.peek().k not in ("nl", "eof"):
            self.i += 1
        self.skipnl()''')
rep('''    def program(self):
        defs = {}
        self.skipnl()
        while self.peek().k != "eof":
            if self.accept("GLOBAL"):
                pass
            self.expect("DEF")
            nm = self.nxt().v
            self.expect("(")
            params = []
            while not self.is_(")"):
                if self.peek().v in ("INT", "REAL", "BOOL", "POS", "E6POS", "FRAME", "AXIS", "E6AXIS"):
                    self.nxt()
                    params.append(self.nxt().v)
                else:
                    self.nxt()
                self.accept(":")
                self.accept(",")
            self.expect(")")
            self.eol()
            body = self.block({"END"})
            self.expect("END")
            self.eol()
            defs[nm] = (params, body)
        return defs''', '''    def program(self):
        defs = {}
        ndat = 0
        self.skipnl()
        while self.peek().k != "eof":
            self.accept("GLOBAL")
            if self.accept("DEFDAT"):
                self.skipline()
                body = self.block({"ENDDAT"})
                self.accept("ENDDAT")
                self.skipnl()
                ndat += 1
                defs[f"__DAT__{ndat}"] = ([], body)
                continue
            fct = False
            if self.accept("DEFFCT"):
                fct = True
                self.nxt()                       # Rueckgabetyp
            elif not self.accept("DEF"):
                if self.lenient:
                    self.warnings.append(f"Zeile {self.peek().line}: ausserhalb DEF ignoriert")
                    self.skipline()
                    continue
                self.expect("DEF")
            nm = self.nxt().v
            self.expect("(")
            params = []
            prev = None
            while not self.is_(")") and self.peek().k != "eof":
                t = self.nxt()
                if t.k == "op" and t.v in (":", ",") and prev is not None and prev.k == "id":
                    if t.v == ":" or prev.v not in ("IN", "OUT"):
                        if prev.v not in ("IN", "OUT"):
                            params.append(prev.v)
                prev = t
            if prev is not None and prev.k == "id" and prev.v not in ("IN", "OUT") and prev.v not in params:
                params.append(prev.v)
            self.expect(")")
            self.skipline()
            ender = "ENDFCT" if fct else "END"
            body = self.block({ender})
            self.expect(ender)
            self.skipnl()
            defs[nm] = (params, body)
        return defs''')
rep('''        while not (self.peek().k == "kw" and self.peek().v in enders) and self.peek().k != "eof":
            s = self.stmt()
            if s:
                out.append(s)
            self.skipnl()
        return out''', '''        while not (self.peek().k == "kw" and self.peek().v in enders) and self.peek().k != "eof":
            if self.lenient:
                start = self.i
                try:
                    s = self.stmt()
                except XrlError as e:
                    self.i = start
                    ln = self.peek().line
                    txt = []
                    while self.peek().k not in ("nl", "eof"):
                        txt.append(str(self.nxt().v))
                    self.warnings.append(f"Zeile {ln}: übersprungen ({' '.join(txt)[:60]})")
                    s = None
            else:
                s = self.stmt()
            if s:
                out.append(s)
            self.skipnl()
        return out''')
# DECL GLOBAL / CONST
rep('''                if v == "DECL":
                    ty = self.nxt().v''', '''                if v == "DECL":
                    while self.peek().v in ("GLOBAL", "CONST"):
                        self.nxt()
                    ty = self.nxt().v''')
rep('''                    if self.accept("["):
                        size = self.expr()
                        self.expect("]")''', '''                    if self.accept("["):
                        if self.is_("]"):
                            size = ("num", 0)
                        else:
                            size = self.expr()
                            while self.accept(","):
                                if not self.is_("]"):
                                    self.expr()
                        self.expect("]")''')

# --- Interpreter
rep('''    def __init__(self, src, io, sysvars):
        self.defs = Parser(tokenize(src)).program()
        self.io = io                # io.get_in(n) / io.get_out(n) / io.set_out(n,v)
        self.sv = sysvars           # dict der Systemvariablen
        self.glob = {}
        self.stop = False''', '''    def __init__(self, src, io, sysvars, glob_init=None, lenient=True):
        p = Parser(tokenize(src), lenient)
        self.defs = p.program()
        self.warnings = list(p.warnings)
        self.io = io                # io.get_in(n) / io.get_out(n) / io.set_out(n,v)
        self.sv = sysvars           # dict der Systemvariablen
        self.glob = dict(glob_init or {})
        self.lenient = lenient
        self.stop = False
        self._warned = set()

    def warn(self, msg):
        if msg not in self._warned:
            self._warned.add(msg)
            self.warnings.append(msg)''')
rep('''            if n.startswith("$"):
                return self.sv.get(n[1:].replace(".", "_"), 0)
            d, _ = self._lookup(env, n)
            if d is None:
                raise XrlError(f"Variable {n} nicht deklariert", 0)
            return d[n]''', '''            if n.startswith("$"):
                return self.sv.get(n[1:].replace(".", "_"), 0)
            parts = n.split(".")
            d, _ = self._lookup(env, parts[0])
            if d is None:
                if self.lenient:
                    self.warn(f"Variable {parts[0]} unbekannt -> 0")
                    return 0
                raise XrlError(f"Variable {n} nicht deklariert", 0)
            v = d[parts[0]]
            for f in parts[1:]:
                v = v.get(f, 0) if isinstance(v, dict) else 0
            return v''')
rep('''            if n in FUNCS:
                return FUNCS[n](*args)
            raise XrlError(f"Funktion {n} unbekannt", 0)''', '''            if n in FUNCS:
                return FUNCS[n](*args)
            if n in self.defs:
                gen = self.call(n, args, want_value=True)
                val = None
                try:
                    while True:
                        next(gen)
                except StopIteration as st:
                    val = st.value
                return val if val is not None else 0
            if self.lenient:
                self.warn(f"Funktion {n} nicht verfügbar -> 0")
                return 0
            raise XrlError(f"Funktion {n} unbekannt", 0)''')
rep('''            if n.startswith("$"):
                self.sv[n[1:].replace(".", "_")] = val
                return
            d, _ = self._lookup(env, n)
            if d is None:
                raise XrlError(f"Variable {n} nicht deklariert", 0)
            cur = d[n]''', '''            if n.startswith("$"):
                self.sv[n[1:].replace(".", "_")] = val
                return
            if "." in n:
                parts = n.split(".")
                d, _ = self._lookup(env, parts[0])
                if d is None:
                    if self.lenient:
                        self.warn(f"Variable {parts[0]} unbekannt (Zuweisung ignoriert)")
                        return
                    raise XrlError(f"Variable {n} nicht deklariert", 0)
                obj = d[parts[0]]
                for f in parts[1:-1]:
                    obj = obj.setdefault(f, {})
                obj[parts[-1]] = val
                return
            d, _ = self._lookup(env, n)
            if d is None:
                if self.lenient:
                    self.glob[n] = val          # implizit global anlegen
                    return
                raise XrlError(f"Variable {n} nicht deklariert", 0)
            cur = d[n]''')
rep('''    def run(self, entry=None):
        if not self.defs:
            raise XrlError("Kein DEF im Programm", 0)
        entry = entry or next(iter(self.defs))
        try:
            yield from self.call(entry, [])
        except _Exit:
            pass

    def call(self, name, args):
        if name not in self.defs:
            raise XrlError(f"Unterprogramm {name} nicht gefunden", 0)
        params, body = self.defs[name]
        env = dict(zip(params, args))
        try:
            yield from self.exec_block(body, env)
        except _Return:
            pass''', '''    def run(self, entry=None):
        progs = [k for k in self.defs if not k.startswith("__DAT__")]
        if not progs:
            raise XrlError("Kein DEF im Programm", 0)
        # Datenlisten (DEFDAT) zuerst als globale Variablen anlegen
        for k in self.defs:
            if k.startswith("__DAT__"):
                for s in self.defs[k][1]:
                    if s[0] in ("decl", "assign"):
                        try:
                            for _ in self.exec_stmt(s, self.glob):
                                pass
                        except XrlError as e:
                            self.warn(f"Datenliste: {e}")
        entry = entry or progs[0]
        try:
            yield from self.call(entry, [])
        except _Exit:
            pass

    def call(self, name, args, want_value=False):
        if name not in self.defs:
            if name == "BAS":
                self.bas(args)
                return None
            if self.lenient:
                self.warn(f"Unterprogramm {name} nicht vorhanden – übersprungen")
                return None
            raise XrlError(f"Unterprogramm {name} nicht gefunden", 0)
        params, body = self.defs[name]
        env = dict(zip(params, args))
        try:
            yield from self.exec_block(body, env)
        except _Return as r:
            return r.v
        return None

    def bas(self, args):
        """Kompatibilitaet zu Inline-Formular-Aufrufen BAS(#AKTION, wert)."""
        act = str(args[0]).upper() if args else ""
        val = args[1] if len(args) > 1 else 0
        if act in ("#PTP_PARAMS", "#VEL_PTP"):
            self.sv["VEL_AXIS_PCT"] = max(0.01, min(1.0, float(val) / 100.0))
        elif act in ("#CP_PARAMS", "#VEL_CP"):
            self.sv["VEL_CP"] = max(0.001, float(val))
        elif act == "#INITMOV":
            self.sv["VEL_AXIS_PCT"] = 1.0
            self.sv["VEL_CP"] = 2.0
        elif act in ("#FRAMES", "#TOOL", "#BASE"):
            fd = self.glob.get("FDAT_ACT", {}) if act == "#FRAMES" else {}
            tn = int(fd.get("TOOL_NO", val if act == "#TOOL" else -1)) if isinstance(fd, dict) else -1
            bn = int(fd.get("BASE_NO", val if act == "#BASE" else -1)) if isinstance(fd, dict) else -1
            td, bd = self.glob.get("TOOL_DATA"), self.glob.get("BASE_DATA")
            if tn >= 0 and isinstance(td, list) and tn < len(td) and act in ("#FRAMES", "#TOOL"):
                self.sv["TOOL"] = dict(td[tn]) if tn > 0 else {}
            if bn >= 0 and isinstance(bd, list) and bn < len(bd) and act in ("#FRAMES", "#BASE"):
                self.sv["BASE"] = dict(bd[bn]) if bn > 0 else {}''')
# Aufrufe: Generator von call kann None liefern
rep('''            if e[0] == "var":
                yield from self.call(e[1], [])
            elif e[0] == "callx":
                yield from self.call(e[1], [self.ev(a, env) for a in e[2]])
            return''', '''            if e[0] == "var":
                g = self.call(e[1], [])
            elif e[0] == "callx":
                g = self.call(e[1], [self.ev(a, env) for a in e[2]])
            else:
                g = None
            if g is not None:
                yield from g
            return''')
# REL-Bewegungen: fehlende Komponenten = 0
rep('''        if k == "move":
            tgt = self.target(self.ev(s[3], env), env)''', '''        if k == "move":
            tgt = self.target(self.ev(s[3], env), env, rel=s[2].endswith("_REL"))''')
rep('''    def target(self, v, env):
        if isinstance(v, dict):
            keys = set(v)
            if keys & set(AX_KEYS):
                cur = self.sv.get("AXIS_ACT", [0] * 6)
                return ("axis", [v.get(a, cur[i]) for i, a in enumerate(AX_KEYS)])
            cur = self.sv.get("POS_ACT", [0] * 6)''', '''    def target(self, v, env, rel=False):
        if isinstance(v, dict):
            keys = set(v)
            if keys & set(AX_KEYS):
                cur = [0] * 6 if rel else self.sv.get("AXIS_ACT", [0] * 6)
                return ("axis", [v.get(a, cur[i]) for i, a in enumerate(AX_KEYS)])
            cur = [0] * 6 if rel else self.sv.get("POS_ACT", [0] * 6)''')
open(P, "w", encoding="utf8").write(m)
print("ok")
