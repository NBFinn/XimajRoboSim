"""Parser fuer das textbasierte .rsc-Baumformat (Layouts/Komponenten in .vcmx-Archiven).

Nur zum Einlesen eigener Projektdaten (Interoperabilitaet). Ergebnis: Baum aus RNode(k, a, c).
"""
import re

_TOK = re.compile(r'"(?:[^"\\]|\\.)*"|\S+')


class RNode:
    __slots__ = ("k", "a", "c")

    def __init__(self, k, a, c=None):
        self.k, self.a, self.c = k, a, c or []

    # Hilfen
    def find(self, k):
        for n in self.c:
            if n.k == k:
                return n
        return None

    def findall(self, k):
        return [n for n in self.c if n.k == k]

    def walk(self):
        yield self
        for n in self.c:
            yield from n.walk()

    def arg(self, i=0, default=None):
        if i < len(self.a):
            v = self.a[i]
            return v[1:-1] if v.startswith('"') and v.endswith('"') else v
        return default

    def name(self):
        n = self.find("Name")
        return n.arg() if n else None

    def __repr__(self):
        return f"RNode({self.k} {' '.join(self.a)[:40]} [{len(self.c)}])"


def parse(text):
    text = text.replace("\\\r\n", "").replace("\\\n", "")
    lines = text.splitlines()
    root = RNode("ROOT", [])
    stack = [root]
    last = None
    for ln in lines:
        s = ln.strip()
        if not s:
            continue
        if s == "{":
            if last is None:
                last = RNode("ANON", [])
                stack[-1].c.append(last)
            stack.append(last)
            last = None
            continue
        if s == "}":
            if len(stack) > 1:
                stack.pop()
            last = None
            continue
        toks = _TOK.findall(s)
        n = RNode(toks[0], toks[1:])
        stack[-1].c.append(n)
        last = n
    return root


def variables(node):
    """Variablen eines VariableSpace/NodeVariableSpace -> dict name->wert(str)"""
    out = {}
    for vs in ("VariableSpace", "NodeVariableSpace"):
        sp = node.find(vs)
        if not sp:
            continue
        for v in sp.findall("Variable"):
            nm = v.find("Name")
            val = v.find("Value")
            if nm is not None:
                out[nm.arg()] = (val.a if val is not None else [])
    return out


def unq(tokens):
    if not tokens:
        return ""
    s = " ".join(tokens)
    return s[1:-1] if s.startswith('"') and s.endswith('"') else s


def location(node):
    l = node.find("Location")
    if not l or len(l.a) < 16:
        return None
    try:
        return [float(x) for x in l.a[:16]]
    except ValueError:
        return None
