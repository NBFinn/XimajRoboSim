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
    ('''        if n.lower().endswith("$config.dat"):
            t = z.read(n).decode("latin1", "replace")
            for ln in t.splitlines():
                if _re.match(r"\\s*DECL\\s+(?:GLOBAL\\s+)?(E6AXIS|E6POS|AXIS|POS|FRAME|INT|REAL|BOOL)\\s+\\w+\\s*=", ln, _re.I):
                    out.append(ln.strip())''',
     '''        if n.lower().endswith(("$config.dat", "/_config.dat")):
            t = z.read(n).decode("latin1", "replace")
            for ln in t.splitlines():
                if _re.match(r"\\s*(?:DECL\\s+)?(?:GLOBAL\\s+)?(E6AXIS|E6POS|AXIS|POS|FRAME|INT|REAL|BOOL)\\s+\\w+\\s*=", ln, _re.I):
                    s = ln.strip()
                    out.append(s if s.upper().startswith("DECL") else "DECL " + s)'''),
])
patch("xrl.py", [
    ('''    (?P<enum>\\#[A-Za-z_][A-Za-z_0-9]*)|''', '''    (?P<enum>\\#[A-Za-z_][A-Za-z_0-9]*)|(?P<hexb>'[HhBb][0-9A-Fa-f]+')|'''),
    ('''        elif k == "enum":
            toks.append(Tok("str", v.upper(), line))''', '''        elif k == "enum":
            toks.append(Tok("str", v.upper(), line))
        elif k == "hexb":
            toks.append(Tok("num", int(v[2:-1], 16 if v[1] in "Hh" else 2), line))'''),
])
print("ok")
