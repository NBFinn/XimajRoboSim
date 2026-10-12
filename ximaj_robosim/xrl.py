"""XRL - Ximaj Robot Language: die eigene Roboter-Programmiersprache der Ximaj IT Solutions.

Eigenstaendiger Interpreter (Tokenizer, Parser, Generator-Ausfuehrung). Unterstuetzt:
DEF/END, DECL INT/REAL/BOOL/POS/AXIS, ; Kommentare, Zuweisungen, IF/ELSE, FOR, WHILE,
REPEAT/UNTIL, LOOP, SWITCH/CASE, EXIT, HALT, WAIT SEC / WAIT FOR, PULSE,
PTP/LIN/CIRC (+_REL), Aggregate {X 1,Y 2,Z 3,A 0,B 0,C 0}, {A1 .., A6 ..},
Systemvariablen $VEL_CP, $ACC_CP, $OUT[n], $IN[n], $TOOL, $BASE, $APO_CDIS, $VEL_AXIS[n], $ACC_AXIS[n].
Der Interpreter ist ein Generator: er liefert Ereignisse an die Simulation.
"""
import math
import re

KEYWORDS = {
    "DEF", "END", "DECL", "GLOBAL", "INT", "REAL", "BOOL", "POS", "E6POS", "FRAME", "AXIS", "E6AXIS",
    "IF", "THEN", "ELSE", "ENDIF", "FOR", "TO", "STEP", "ENDFOR", "WHILE", "ENDWHILE", "REPEAT", "UNTIL",
    "LOOP", "ENDLOOP", "SWITCH", "CASE", "DEFAULT", "ENDSWITCH", "EXIT", "HALT", "WAIT", "SEC", "FOR",
    "PTP", "LIN", "CIRC", "PTP_REL", "LIN_REL", "PULSE", "TRUE", "FALSE", "AND", "OR", "NOT", "EXOR", "MOD",
    "RETURN", "CONTINUE", "INI", "TRIGGER", "WHEN", "DISTANCE", "DELAY", "DO", "ANOUT", "MSG",
    "DEFDAT", "ENDDAT", "DEFFCT", "ENDFCT",
    "SIGNAL",
    "SPTP", "SLIN", "SCIRC", "SPTP_REL", "SLIN_REL", "SCIRC_REL", "CIRC_REL", "EXT", "EXTFCT", "INTERRUPT", "WITH",
}

TOKEN_RE = re.compile(r"""
    (?P<ws>[ \t\r]+)|(?P<nl>\n)|(?P<comment>[;&][^\n]*)|
    (?P<num>\d+\.\d*(?:[eE][+-]?\d+)?|\.\d+(?:[eE][+-]?\d+)?|\d+(?:[eE][+-]?\d+)?)|
    (?P<enum>\#[A-Za-z_][A-Za-z_0-9]*)|(?P<hexb>'[HhBb][0-9A-Fa-f]+')|
    (?P<id>\$?[A-Za-z_][A-Za-z_0-9]*(?:\.[A-Za-z_][A-Za-z_0-9]*)*)|(?P<str>"[^"\n]*")|
    (?P<op><>|<=|>=|==|[-+*/<>=\[\]\(\),:{}.])
""", re.X)


class XrlError(Exception):
    def __init__(self, msg, line=0):
        super().__init__(f"Zeile {line}: {msg}")
        self.line = line


class Tok:
    __slots__ = ("k", "v", "line")

    def __init__(self, k, v, line):
        self.k, self.v, self.line = k, v, line


def tokenize(src):
    toks, line, pos = [], 1, 0
    while pos < len(src):
        m = TOKEN_RE.match(src, pos)
        if not m:
            raise XrlError(f"Unerwartetes Zeichen {src[pos]!r}", line)
        pos = m.end()
        k = m.lastgroup
        if k == "ws" or k == "comment":
            continue
        if k == "nl":
            toks.append(Tok("nl", "\n", line))
            line += 1
            continue
        v = m.group(k)
        if k == "num":
            toks.append(Tok("num", float(v) if any(c in v for c in ".eE") else int(v), line))
        elif k == "id":
            u = v.upper()
            toks.append(Tok("kw" if u in KEYWORDS else "id", u, line))
        elif k == "str":
            toks.append(Tok("str", v[1:-1], line))
        elif k == "enum":
            toks.append(Tok("str", v.upper(), line))
        elif k == "hexb":
            toks.append(Tok("num", int(v[2:-1], 16 if v[1] in "Hh" else 2), line))
        else:
            toks.append(Tok("op", v, line))
    toks.append(Tok("nl", "\n", line))
    toks.append(Tok("eof", "", line))
    return toks


# ---------------------------------------------------------------- Parser
class Parser:
    def __init__(self, toks, lenient=True):
        self.t, self.i = toks, 0
        self.lenient = lenient
        self.warnings = []

    def skipline(self):
        while self.peek().k not in ("nl", "eof"):
            self.i += 1
        self.skipnl()

    def peek(self):
        return self.t[self.i]

    def nxt(self):
        t = self.t[self.i]
        self.i += 1
        return t

    def is_(self, v):
        t = self.peek()
        return t.k in ("kw", "op") and t.v == v

    def accept(self, v):
        if self.is_(v):
            return self.nxt()
        return None

    def expect(self, v):
        if not self.is_(v):
            raise XrlError(f"'{v}' erwartet, gefunden '{self.peek().v}'", self.peek().line)
        return self.nxt()

    def skipnl(self):
        while self.peek().k == "nl":
            self.i += 1

    def eol(self):
        if self.peek().k not in ("nl", "eof"):
            raise XrlError(f"Zeilenende erwartet, gefunden '{self.peek().v}'", self.peek().line)
        self.skipnl()

    def program(self):
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
        return defs

    def block(self, enders):
        out = []
        self.skipnl()
        while not (self.peek().k == "kw" and self.peek().v in enders) and self.peek().k != "eof":
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
        return out

    def stmt(self):
        t = self.peek()
        ln = t.line
        if t.k == "kw":
            v = t.v
            if v == "DECL" or v in ("INT", "REAL", "BOOL", "POS", "E6POS", "FRAME", "AXIS", "E6AXIS"):
                self.nxt()
                if v == "DECL":
                    while self.peek().v in ("GLOBAL", "CONST"):
                        self.nxt()
                    ty = self.nxt().v
                else:
                    ty = v
                names = []
                while True:
                    n = self.nxt().v
                    size = None
                    if self.accept("["):
                        if self.is_("]"):
                            size = ("num", 0)
                        else:
                            size = self.expr()
                            while self.accept(","):
                                if not self.is_("]"):
                                    self.expr()
                        self.expect("]")
                    init = None
                    if self.accept("="):
                        init = self.expr()
                    names.append((n, size, init))
                    if not self.accept(","):
                        break
                self.eol()
                return ("decl", ln, ty, names)
            if v == "INI":
                self.nxt()
                self.eol()
                return None
            if v == "GLOBAL":
                self.nxt()
                return self.stmt()
            if v == "SIGNAL":
                self.nxt()
                nm = self.nxt().v
                a = self.expr()
                b = None
                if self.accept("TO"):
                    b = self.expr()
                self.skipline()
                return ("signal", ln, nm, a, b)
            if v in ("EXT", "EXTFCT", "INTERRUPT"):
                self.skipline()            # Deklarationen/Interrupts: in der Simulation ohne Wirkung
                return None
            if v in ("PTP", "LIN", "PTP_REL", "LIN_REL", "SPTP", "SLIN", "SPTP_REL", "SLIN_REL"):
                self.nxt()
                tgt = self.expr()
                withs = self.with_clause()
                self.rest_of_motion()
                kind = v[1:] if v.startswith("S") else v
                return ("move", ln, kind, tgt, withs)
            if v in ("CIRC", "SCIRC", "CIRC_REL", "SCIRC_REL"):
                self.nxt()
                aux = self.expr()
                self.expect(",")
                tgt = self.expr()
                withs = self.with_clause()
                self.rest_of_motion()
                return ("circ", ln, aux, tgt, withs)
            if v == "CIRC__ALT":
                self.nxt()
                aux = self.expr()
                self.expect(",")
                tgt = self.expr()
                if self.accept(","):
                    self.expect("CA")
                    self.expr()
                self.opt_approx()
                self.eol()
                return ("circ", ln, aux, tgt)
            if v == "WAIT":
                self.nxt()
                if self.accept("SEC"):
                    e = self.expr()
                    self.eol()
                    return ("waitsec", ln, e)
                self.expect("FOR")
                e = self.expr()
                self.eol()
                return ("waitfor", ln, e)
            if v == "PULSE":
                self.nxt()
                self.expect("(")
                tgt = self.expr()
                self.expect(",")
                val = self.expr()
                self.expect(",")
                dur = self.expr()
                self.expect(")")
                self.eol()
                return ("pulse", ln, tgt, val, dur)
            if v == "IF":
                self.nxt()
                c = self.expr()
                self.expect("THEN")
                self.eol()
                a = self.block({"ELSE", "ENDIF"})
                b = []
                if self.accept("ELSE"):
                    self.eol()
                    b = self.block({"ENDIF"})
                self.expect("ENDIF")
                self.eol()
                return ("if", ln, c, a, b)
            if v == "FOR":
                self.nxt()
                var = self.nxt().v
                self.expect("=")
                a = self.expr()
                self.expect("TO")
                b = self.expr()
                st = None
                if self.accept("STEP"):
                    st = self.expr()
                self.eol()
                body = self.block({"ENDFOR"})
                self.expect("ENDFOR")
                self.eol()
                return ("for", ln, var, a, b, st, body)
            if v == "WHILE":
                self.nxt()
                c = self.expr()
                self.eol()
                body = self.block({"ENDWHILE"})
                self.expect("ENDWHILE")
                self.eol()
                return ("while", ln, c, body)
            if v == "REPEAT":
                self.nxt()
                self.eol()
                body = self.block({"UNTIL"})
                self.expect("UNTIL")
                c = self.expr()
                self.eol()
                return ("repeat", ln, c, body)
            if v == "LOOP":
                self.nxt()
                self.eol()
                body = self.block({"ENDLOOP"})
                self.expect("ENDLOOP")
                self.eol()
                return ("loop", ln, body)
            if v == "SWITCH":
                self.nxt()
                e = self.expr()
                self.eol()
                cases, default = [], []
                self.skipnl()
                while self.is_("CASE"):
                    self.nxt()
                    vals = [self.expr()]
                    while self.accept(","):
                        vals.append(self.expr())
                    self.eol()
                    cases.append((vals, self.block({"CASE", "DEFAULT", "ENDSWITCH"})))
                if self.accept("DEFAULT"):
                    self.eol()
                    default = self.block({"ENDSWITCH"})
                self.expect("ENDSWITCH")
                self.eol()
                return ("switch", ln, e, cases, default)
            if v in ("EXIT", "HALT", "RETURN", "CONTINUE"):
                self.nxt()
                if v == "RETURN" and self.peek().k not in ("nl", "eof"):
                    e = self.expr()
                    self.eol()
                    return ("return", ln, e)
                self.eol()
                return (v.lower(), ln)
            if v == "MSG":
                self.nxt()
                e = self.expr()
                self.eol()
                return ("msg", ln, e)
            raise XrlError(f"Unerwartetes Schluesselwort {v}", ln)
        if t.k == "id":
            e = self.expr()
            if self.accept("="):
                r = self.expr()
                self.eol()
                return ("assign", ln, e, r)
            self.eol()
            return ("call", ln, e)
        raise XrlError(f"Unerwartet '{t.v}'", ln)

    def with_clause(self):
        """WITH $TOOL = STOOL2(F), $VEL_AXIS[1] = SVEL_JOINT(100) ... -> [(ziel, ausdruck)]"""
        out = []
        if not self.accept("WITH"):
            return out
        try:
            while True:
                t = self.expr()
                self.expect("=")
                v = self.expr()
                out.append((t, v))
                if not self.accept(","):
                    break
        except XrlError:
            pass
        return out

    def rest_of_motion(self):
        """Ueberschleifen (C_PTP/C_DIS/C_SPL), WITH-Zusaetze, CA ... bis Zeilenende ueberspringen"""
        while self.peek().k not in ("nl", "eof"):
            self.nxt()
        self.skipnl()

    def opt_approx(self):
        # C_PTP / C_DIS / C_VEL / C_ORI werden akzeptiert (Ueberschleifen) und gespeichert
        while self.peek().k == "id" and self.peek().v in ("C_PTP", "C_DIS", "C_VEL", "C_ORI"):
            self.nxt()

    # Ausdruecke
    def expr(self):
        return self.e_or()

    def e_or(self):
        a = self.e_and()
        while self.peek().k == "kw" and self.peek().v in ("OR", "EXOR"):
            op = self.nxt().v
            a = ("bin", op, a, self.e_and())
        return a

    def e_and(self):
        a = self.e_not()
        while self.is_("AND"):
            self.nxt()
            a = ("bin", "AND", a, self.e_not())
        return a

    def e_not(self):
        if self.accept("NOT"):
            return ("not", self.e_not())
        return self.e_cmp()

    def e_cmp(self):
        a = self.e_add()
        while self.peek().k == "op" and self.peek().v in ("==", "<>", "<", ">", "<=", ">="):
            op = self.nxt().v
            a = ("bin", op, a, self.e_add())
        return a

    def e_add(self):
        a = self.e_mul()
        while self.peek().k == "op" and self.peek().v in ("+", "-"):
            op = self.nxt().v
            a = ("bin", op, a, self.e_mul())
        return a

    def e_mul(self):
        a = self.e_geo()
        while (self.peek().k == "op" and self.peek().v in ("*", "/")) or self.is_("MOD"):
            op = self.nxt().v
            a = ("bin", op, a, self.e_geo())
        return a

    def e_geo(self):
        a = self.e_un()
        while self.is_(":"):
            self.nxt()
            a = ("bin", ":", a, self.e_un())
        return a

    def e_un(self):
        if self.peek().k == "op" and self.peek().v in ("-", "+"):
            op = self.nxt().v
            e = self.e_un()
            return ("neg", e) if op == "-" else e
        return self.e_post()

    def e_post(self):
        a = self.atom()
        while True:
            if self.is_("["):
                self.nxt()
                i = self.expr()
                while self.accept(","):          # mehrdimensional: weitere Indizes ignorieren
                    if not self.is_("]"):
                        self.expr()
                self.expect("]")
                a = ("idx", a, i)
            elif self.is_("."):
                self.nxt()
                a = ("field", a, self.nxt().v)
            elif self.is_("(") and a[0] == "var":
                self.nxt()
                args = []
                while not self.is_(")"):
                    args.append(self.expr())
                    self.accept(",")
                self.expect(")")
                a = ("callx", a[1], args)
            elif self.is_(".") if False else (self.peek().k == "num" and False):
                break
            else:
                break
        return a

    def atom(self):
        t = self.nxt()
        if t.k == "num":
            return ("num", t.v)
        if t.k == "str":
            return ("str", t.v)
        if t.k == "kw" and t.v in ("TRUE", "FALSE"):
            return ("num", t.v == "TRUE")
        if t.k == "id":
            return ("var", t.v)
        if t.k == "op" and t.v == "(":
            e = self.expr()
            self.expect(")")
            return e
        if t.k == "op" and t.v == "{":
            # Aggregat; optionaler Typ "E6POS:" vorweg
            if self.peek().k in ("id", "kw") and self.t[self.i + 1].v == ":" :
                self.nxt()
                self.nxt()
            items = {}
            while not self.is_("}"):
                key = self.nxt().v
                if self.is_("["):
                    while not self.is_("]") and self.peek().k not in ("nl", "eof"):
                        self.nxt()
                    self.accept("]")
                items[key] = self.expr()
                self.accept(",")
            self.expect("}")
            return ("agg", items)
        raise XrlError(f"Unerwarteter Ausdruck '{t.v}'", t.line)


# ---------------------------------------------------------------- Ausfuehrung
class _Exit(Exception):
    pass


class _Return(Exception):
    def __init__(self, v=None):
        self.v = v


class _Continue(Exception):
    pass


FUNCS = {
    "SIN": lambda x: math.sin(math.radians(x)), "COS": lambda x: math.cos(math.radians(x)),
    "TAN": lambda x: math.tan(math.radians(x)), "ASIN": lambda x: math.degrees(math.asin(x)),
    "ACOS": lambda x: math.degrees(math.acos(x)), "ATAN2": lambda y, x: math.degrees(math.atan2(y, x)),
    "SQRT": math.sqrt, "ABS": abs, "MIN": min, "MAX": max, "INT": int, "FLOOR": math.floor,
}
POS_KEYS = ("X", "Y", "Z", "A", "B", "C")
AX_KEYS = ("A1", "A2", "A3", "A4", "A5", "A6")


class Interp:
    """Fuehrt ein ORL-Programm als Generator aus.

    Ereignisse (tuple): ('line', n) | ('ptp'|'lin', ziel, rel) | ('circ', hilf, ziel) |
    ('wait', sek) | ('waitfor', fn) | ('pulse', nr, wert, sek) | ('msg', text) | ('halt',)
    ziel = ('pos', [x,y,z,a,b,c], S, T) oder ('axis', [a1..a6])
    """

    def __init__(self, src, io, sysvars, glob_init=None, lenient=True):
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
            self.warnings.append(msg)

    # -- Variablen
    def _lookup(self, env, name):
        if name in env:
            return env, name
        if name in self.glob:
            return self.glob, name
        return None, name

    def ev(self, e, env):
        k = e[0]
        if k == "num":
            return e[1]
        if k == "str":
            return e[1]
        if k == "var":
            n = e[1]
            if n == "$IN" or n == "$OUT":
                return n
            if n.startswith("$"):
                return self.sv.get(n[1:].replace(".", "_"), 0)
            parts = n.split(".")
            d, _ = self._lookup(env, parts[0])
            if d is None:
                if self.lenient:
                    self.warn(f"Variable {parts[0]} unbekannt -> 0")
                    return 0
                raise XrlError(f"Variable {n} nicht deklariert", 0)
            v = d[parts[0]]
            if isinstance(v, SignalRef):
                return v.read()
            for f in parts[1:]:
                v = v.get(f, 0) if isinstance(v, dict) else 0
            return v
        if k == "neg":
            return -self.ev(e[1], env)
        if k == "not":
            return not self.ev(e[1], env)
        if k == "idx":
            base = self.ev(e[1], env)
            i = int(self.ev(e[2], env))
            if base == "$IN":
                return self.io.get_in(i)
            if base == "$OUT":
                return self.io.get_out(i)
            if isinstance(base, str):
                nm = e[1][1]
                return self.sv.get(nm[1:].replace(".", "_") + f"[{i}]", 0)
            return base[i]
        if k == "agg":
            return {kk: self.ev(v, env) for kk, v in e[1].items()}
        if k == "field":
            base = self.ev(e[1], env)
            for f in e[2].split("."):
                base = base.get(f, 0) if isinstance(base, dict) else 0
            return base
        if k == "callx":
            n, args = e[1], [self.ev(a, env) for a in e[2]]
            if n in FUNCS:
                return FUNCS[n](*args)
            ok, val = self.builtin(n, args)
            if ok:
                return val
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
            raise XrlError(f"Funktion {n} unbekannt", 0)
        if k == "bin":
            op = e[1]
            if op == "AND":
                return bool(self.ev(e[2], env)) and bool(self.ev(e[3], env))
            if op == "OR":
                return bool(self.ev(e[2], env)) or bool(self.ev(e[3], env))
            a, b = self.ev(e[2], env), self.ev(e[3], env)
            if op == ":":
                return _geo(a, b)
            if op == "EXOR":
                return bool(a) != bool(b)
            if op == "+":
                return a + b
            if op == "-":
                return a - b
            if op == "*":
                return a * b
            if op == "/":
                if isinstance(a, int) and isinstance(b, int):
                    return int(a / b)
                return a / b
            if op == "MOD":
                return a % b
            if op == "==":
                return a == b
            if op == "<>":
                return a != b
            if op == "<":
                return a < b
            if op == ">":
                return a > b
            if op == "<=":
                return a <= b
            if op == ">=":
                return a >= b
        raise XrlError(f"Ausdruck {k} nicht auswertbar", 0)

    def assign(self, tgt, val, env):
        if tgt[0] == "var":
            n = tgt[1]
            if n.startswith("$"):
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
            cur = d[n]
            if isinstance(cur, SignalRef):
                cur.write(val)
                return
            if isinstance(cur, dict) and isinstance(val, dict):
                cur.update(val)
            else:
                d[n] = val
            return
        if tgt[0] == "field":
            obj = self.ev(tgt[1], env)
            parts = tgt[2].split(".")
            if isinstance(obj, dict):
                for f in parts[:-1]:
                    obj = obj.setdefault(f, {})
                obj[parts[-1]] = val
            return
        if tgt[0] == "idx":
            base = tgt[1]
            i = int(self.ev(tgt[2], env))
            if base[0] == "var" and base[1] == "$OUT":
                self.io.set_out(i, bool(val))
                return
            if base[0] == "var" and base[1].startswith("$"):
                self.sv[base[1][1:].replace(".", "_") + f"[{i}]"] = val
                return
            arr = self.ev(base, env)
            if isinstance(arr, dict) and not isinstance(i, int):
                arr[i] = val
            else:
                arr[i] = val
            return
        raise XrlError("Ungueltige Zuweisung", 0)

    # -- Ausfuehrung
    def run(self, entry=None):
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

    def apply_with(self, withs, env):
        """Nur die fuer die Simulation relevanten Zusaetze: Werkzeug, Basis, Geschwindigkeit."""
        for t, v in withs:
            name = t[1] if t[0] == "var" else (t[1][1] if t[0] == "idx" and t[1][0] == "var" else "")
            if name not in ("$TOOL", "$BASE", "$VEL_AXIS", "$VEL", "$VEL.CP"):
                continue
            try:
                val = self.ev(v, env)
            except XrlError:
                continue
            if name == "$TOOL" and isinstance(val, dict):
                self.sv["TOOL"] = dict(val)
            elif name == "$BASE" and isinstance(val, dict):
                self.sv["BASE"] = dict(val)
            elif name == "$VEL_AXIS" and isinstance(val, (int, float)) and val > 0:
                self.sv["VEL_AXIS_PCT"] = max(0.01, min(1.0, float(val) / 100.0))
            elif name in ("$VEL", "$VEL.CP") and isinstance(val, (int, float)) and val > 0:
                self.sv["VEL_CP"] = float(val)

    def builtin(self, n, args):
        """Kompatible Hilfsfunktionen fuer Bewegungszusaetze. -> (gefunden, wert)"""
        td, bd = self.glob.get("TOOL_DATA"), self.glob.get("BASE_DATA")
        if n == "STOOL2" and args and isinstance(args[0], dict):
            i = int(args[0].get("TOOL_NO", 0))
            return True, (td[i] if isinstance(td, list) and 0 <= i < len(td) else {})
        if n == "SBASE" and args:
            i = int(args[0]) if not isinstance(args[0], dict) else int(args[0].get("BASE_NO", 0))
            return True, (bd[i] if isinstance(bd, list) and 0 <= i < len(bd) else {})
        if n in ("SVEL_JOINT", "SVEL_CP", "SACC_JOINT", "SACC_CP") and args:
            return True, args[0] if isinstance(args[0], (int, float)) else 0
        return False, None

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
                self.sv["BASE"] = dict(bd[bn]) if bn > 0 else {}

    def exec_block(self, body, env):
        for s in body:
            if self.stop:
                raise _Exit()
            yield from self.exec_stmt(s, env)

    def exec_stmt(self, s, env):
        k, ln = s[0], s[1]
        yield ("line", ln)
        try:
            yield from self._exec(s, env, k, ln)
        except XrlError as e:
            if e.line == 0:
                raise XrlError(str(e).split(": ", 1)[1], ln)
            raise
        except (ZeroDivisionError, TypeError, KeyError, IndexError, ValueError) as e:
            raise XrlError(f"{type(e).__name__}: {e}", ln)

    def _exec(self, s, env, k, ln):
        if k == "signal":
            def ref(e):
                if e[0] == "idx" and e[1][0] == "var" and e[1][1] in ("$IN", "$OUT"):
                    return e[1][1], int(self.ev(e[2], env))
                return None
            a, b = ref(s[3]), ref(s[4]) if s[4] is not None else None
            if a:
                self.glob[s[2]] = SignalRef(self.io, a[0], a[1], b[1] if b else a[1])
            return
        if k == "decl":
            for n, size, init in s[3]:
                ty = s[2]
                if size is not None:
                    cnt = int(self.ev(size, env))
                    env[n] = [_default(ty) for _ in range(cnt + 1)]
                else:
                    env[n] = self.ev(init, env) if init else _default(ty)
            return
        if k == "assign":
            self.assign(s[2], self.ev(s[3], env), env)
            return
        if k == "call":
            e = s[2]
            if e[0] == "var":
                g = self.call(e[1], [])
            elif e[0] == "callx":
                g = self.call(e[1], [self.ev(a, env) for a in e[2]])
            else:
                g = None
            if g is not None:
                yield from g
            return
        if k in ("move", "circ") and len(s) > 4 and s[-1]:
            self.apply_with(s[-1], env)
        if k == "move":
            tgt = self.target(self.ev(s[3], env), env, rel=s[2].endswith("_REL"))
            yield (s[2].lower().replace("_rel", ""), tgt, s[2].endswith("_REL"))
            return
        if k == "circ":
            yield ("circ", self.target(self.ev(s[2], env), env), self.target(self.ev(s[3], env), env))
            return
        if k == "waitsec":
            yield ("wait", float(self.ev(s[2], env)))
            return
        if k == "waitfor":
            e = s[2]
            yield ("waitfor", lambda e=e, env=env: bool(self.ev(e, env)))
            return
        if k == "pulse":
            tgt = s[2]
            yield ("pulse", int(self.ev(tgt[2], env)), bool(self.ev(s[3], env)), float(self.ev(s[4], env)))
            return
        if k == "msg":
            yield ("msg", str(self.ev(s[2], env)))
            return
        if k == "if":
            yield from self.exec_block(s[3] if self.ev(s[2], env) else s[4], env)
            return
        if k == "for":
            var = s[2]
            a, b = self.ev(s[3], env), self.ev(s[4], env)
            st = self.ev(s[5], env) if s[5] else 1
            if st == 0:
                raise XrlError("STEP 0", ln)
            env.setdefault(var, 0)
            env[var] = a
            while (env[var] <= b) if st > 0 else (env[var] >= b):
                try:
                    yield from self.exec_block(s[6], env)
                except _Continue:
                    pass
                except _Break:
                    break
                env[var] += st
            return
        if k == "while":
            while self.ev(s[2], env):
                yield ("tick",)
                try:
                    yield from self.exec_block(s[3], env)
                except _Continue:
                    pass
            return
        if k == "repeat":
            while True:
                yield ("tick",)
                try:
                    yield from self.exec_block(s[3], env)
                except _Continue:
                    pass
                if self.ev(s[2], env):
                    break
            return
        if k == "loop":
            while True:
                yield ("tick",)
                try:
                    yield from self.exec_block(s[2], env)
                except _Continue:
                    pass
                except _Break:
                    break
            return
        if k == "switch":
            v = self.ev(s[2], env)
            for vals, body in s[3]:
                if any(self.ev(x, env) == v for x in vals):
                    yield from self.exec_block(body, env)
                    return
            yield from self.exec_block(s[4], env)
            return
        if k == "exit":
            raise _Break()
        if k == "continue":
            raise _Continue()
        if k == "halt":
            yield ("halt",)
            return
        if k == "return":
            raise _Return(self.ev(s[2], env) if len(s) > 2 else None)
        raise XrlError(f"Anweisung {k} nicht implementiert", ln)

    def target(self, v, env, rel=False):
        if isinstance(v, dict):
            keys = set(v)
            e1 = v.get("E1")
            if keys & set(AX_KEYS):
                cur = [0] * 6 if rel else self.sv.get("AXIS_ACT", [0] * 6)
                return ("axis", [v.get(a, cur[i]) for i, a in enumerate(AX_KEYS)], e1)
            cur = [0] * 6 if rel else self.sv.get("POS_ACT", [0] * 6)
            return ("pos", [v.get(a, cur[i]) for i, a in enumerate(POS_KEYS)], v.get("S"), v.get("T"), e1)
        raise XrlError(f"Ziel ist kein Positions-/Achsaggregat (Wert: {str(v)[:40]})", 0)


class _Break(Exception):
    pass


class SignalRef:
    """SIGNAL name $IN[a] TO $IN[b]: Einzelbit (BOOL) oder Bitgruppe (INT)"""

    def __init__(self, io, kind, a, b):
        self.io, self.kind, self.a, self.b = io, kind, a, b

    def _get(self, n):
        return self.io.get_in(n) if self.kind == "$IN" else self.io.get_out(n)

    def read(self):
        if self.a == self.b:
            return bool(self._get(self.a))
        return sum((1 << i) for i, n in enumerate(range(self.a, self.b + 1)) if self._get(n))

    def write(self, v):
        if self.kind != "$OUT":
            return
        if self.a == self.b:
            self.io.set_out(self.a, bool(v))
        else:
            for i, n in enumerate(range(self.a, self.b + 1)):
                self.io.set_out(n, bool(int(v) >> i & 1))


def _default(ty):
    if ty == "INT":
        return 0
    if ty == "REAL":
        return 0.0
    if ty == "BOOL":
        return False
    if ty in ("AXIS", "E6AXIS"):
        return {a: 0.0 for a in AX_KEYS}
    return {a: 0.0 for a in POS_KEYS}


def _geo(a, b):
    from kinematics import pose_to_mat, mat_to_pose
    ma = pose_to_mat(*[a.get(k, 0) for k in POS_KEYS])
    mb = pose_to_mat(*[b.get(k, 0) for k in POS_KEYS])
    p = mat_to_pose(ma @ mb)
    return dict(zip(POS_KEYS, [float(x) for x in p]))


# _Exit fuer EXIT in Schleifen wird als _Break behandelt; Exit aus dem Programm via stop-Flag
