import sys, os, zipfile, re, collections
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'ximaj_robosim'))
from rsc_parser import parse

z = zipfile.ZipFile(sys.argv[1])
rsc = [n for n in z.namelist() if n.endswith(".rsc")][0]
txt = z.read(rsc).decode("utf8", "replace")
root = parse(txt)
for n in root.walk():
    if n.k == "Node" and n.arg() == "rSimResource" and n.name() and "Conveyor" in n.name():
        keys = collections.Counter()
        for c in n.walk():
            if "aterial" in c.k or "olor" in c.k:
                keys[(c.k, " ".join(c.a)[:40])] += 1
        print(n.name(), keys.most_common(8))
# globale Materialtabelle: Zeilen mit Material-Definitionen
for m in re.finditer(r'\n\s*(Material|rMaterial|MaterialDef)\s+"([^"]+)"\s*\n\s*\{([\s\S]{0,400}?)\}', txt):
    print("DEF", m.group(2), re.sub(r"\s+", " ", m.group(3))[:200])
    break
print([m.start() for m in re.finditer("transp_red", txt)][:5])
i = txt.find("transp_red")
print(txt[i - 400:i + 300])
