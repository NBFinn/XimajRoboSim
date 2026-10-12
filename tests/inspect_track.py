import sys, os, zipfile, re
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'ximaj_robosim'))
from rsc_parser import parse, location
import vcmx_import as vi
p = r"C:\Users\FinnStetter\OneDrive - Ximaj IT-Solutions GmbH\Dokumente\KUKA\iiQWorks.Sim 1.3\My Models\{}.vcmx".format(sys.argv[1])
z = zipfile.ZipFile(p)
rsc = [n for n in z.namelist() if n.endswith(".rsc")][0]
root = parse(z.read(rsc).decode("utf8", "replace"))
for n in root.walk():
    if n.k == "Node" and n.arg() == "rSimResource" and n.name() and n.name().startswith("KL"):
        v = vi._vars(n)
        loc = location(n)
        print(n.name(), (loc[12], loc[13], loc[14]) if loc else None)
        print({k: str(x)[:30] for k, x in v.items()})
        for c in n.walk():
            if c.k == "Node" and c.arg() == "rSimLink":
                l = location(c)
                print("  Link", c.name(), (l[12], l[13], l[14]) if l else None)
            if c.k == "Node" and c.arg() == "rSimResource" and c is not n:
                l = location(c)
                print("  Unterkomponente", c.name(), (l[12], l[13], l[14]) if l else None)
        for c in n.walk():
            if c.k == "Feature" and c.arg() == "rTransformFeature":
                ex = [" ".join(e.a) for e in c.walk() if e.k == "Expression"]
                if ex and any(x.strip('"') for x in ex):
                    print("  TF", ex[:2])
        break
# Programme: E1 in Punkten?
for nm in z.namelist():
    if nm.lower().endswith(".dat") and "/program/" in nm.lower():
        t = z.read(nm).decode("latin1")
        m = re.findall(r"E1\s+(-?[\d.]+)", t)
        if m:
            print(nm, "E1-Werte:", m[:8])
