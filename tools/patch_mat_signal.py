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


patch("vcmx_import.py", [
    ('''    for m in re.finditer(r'\\n\\s*Material\\s+"([^"]+)"\\s*\\n\\s*\\{([\\s\\S]{0,600}?)\\n\\s*\\}\\s*\\n', text):
        body = m.group(2)''', '''    for m in re.finditer(r'\\n\\s*Material\\s+"([^"]+)"\\s*\\n\\s*\\{', text):
        body = text[m.end():m.end() + 700]'''),
])

patch("xrl.py", [
    ('''    "SPTP", "SLIN", "SCIRC",''', '''    "SIGNAL",
    "SPTP", "SLIN", "SCIRC",'''),
    ('''            if v == "GLOBAL":
                self.nxt()
                return self.stmt()''', '''            if v == "GLOBAL":
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
                return ("signal", ln, nm, a, b)'''),
    ('''        if k == "decl":''', '''        if k == "signal":
            def ref(e):
                if e[0] == "idx" and e[1][0] == "var" and e[1][1] in ("$IN", "$OUT"):
                    return e[1][1], int(self.ev(e[2], env))
                return None
            a, b = ref(s[3]), ref(s[4]) if s[4] is not None else None
            if a:
                self.glob[s[2]] = SignalRef(self.io, a[0], a[1], b[1] if b else a[1])
            return
        if k == "decl":'''),
    # Lesen
    ('''            v = d[parts[0]]
            for f in parts[1:]:''', '''            v = d[parts[0]]
            if isinstance(v, SignalRef):
                return v.read()
            for f in parts[1:]:'''),
    # Schreiben
    ('''            cur = d[n]
            if isinstance(cur, dict) and isinstance(val, dict):''', '''            cur = d[n]
            if isinstance(cur, SignalRef):
                cur.write(val)
                return
            if isinstance(cur, dict) and isinstance(val, dict):'''),
    ('''class _Break(Exception):
    pass''', '''class _Break(Exception):
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
                self.io.set_out(n, bool(int(v) >> i & 1))'''),
])
print("ok")
