import sys, os, zipfile, re, collections
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'ximaj_robosim'))
from rsc_parser import parse
import vcmx_import as vi

z = zipfile.ZipFile(sys.argv[1])
rsc = [n for n in z.namelist() if n.endswith(".rsc")][0]
txt = z.read(rsc).decode("utf8", "replace")
root = parse(txt)
# Materialdefinitionen
mats = collections.OrderedDict()
for n in root.walk():
    if n.k in ("Material", "rMaterial") and n.c:
        nm = n.find("Name")
        col = [c for c in n.walk() if c.k in ("Diffuse", "DiffuseColor", "Color", "Ambient")]
        if nm:
            mats[nm.arg()] = [(c.k, " ".join(c.a)) for c in col][:3]
print("Materialien:", list(mats.items())[:25])
for n in root.walk():
    if n.k == "Node" and n.arg() == "rSimResource" and n.name() and "Conveyor" in n.name():
        ms = collections.Counter()
        for c in n.walk():
            if c.k == "Variable":
                nm = c.find("Name")
                if nm is not None and nm.arg() == "Material":
                    ms[vi._var_value(c)] += 1
        print(n.name(), dict(ms))
i = txt.find("Material \"")
print(txt[i:i + 600] if i >= 0 else "kein Material-Block")
