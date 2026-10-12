import zipfile, sys, re
z = zipfile.ZipFile(sys.argv[1])
n = [x for x in z.namelist() if x.endswith(".rsc")][0]
t = z.read(n).decode("utf8", "replace")
ms = list(re.finditer(r'\n(\s*)(Material|rMaterial|MaterialDef)\s+"([^"]+)"\s*\n\s*\{', t))
print("Anzahl:", len(ms), [m.group(3) for m in ms][:40])
m = ms[0]
print(re.sub(r"[ ]+", " ", t[m.start():m.start() + 1200]))
