"""Ende-zu-Ende-Test des Update-Dienstes mit simuliertem GitHub-Release (ohne Netz)."""
import hashlib, io, json, os, shutil, sys, tempfile, zipfile, importlib

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "ximaj_robosim")
tmp = tempfile.mkdtemp(prefix="xrs_upd_")
app = os.path.join(tmp, "app")
shutil.copytree(SRC, app, ignore=shutil.ignore_patterns("__pycache__", "_backup", "_update_*"))
sys.path.insert(0, app)
import update  # aus der Kopie
from version import VERSION as CUR
_p = [int(x) for x in CUR.split(".")]
NEW = f"{_p[0]}.{_p[1]}.{_p[2] + 1}"
assert update.APP_DIR == app, update.APP_DIR

# --- "neue Version" 1.0.1 als Release-ZIP bauen
newdir = os.path.join(tmp, "new")
shutil.copytree(app, newdir)
open(os.path.join(newdir, "version.py"), "w").write(f'VERSION = "{NEW}"\nUPDATE_REPO = "NBFinn/XimajRoboSim"\n')
open(os.path.join(newdir, "NEU.txt"), "w").write("neu")
zbuf = io.BytesIO()
with zipfile.ZipFile(zbuf, "w") as z:
    for r, d, fs in os.walk(newdir):
        for f in fs:
            full = os.path.join(r, f)
            z.write(full, os.path.join("ximaj_robosim", os.path.relpath(full, newdir)))
zdata = zbuf.getvalue()
sha = hashlib.sha256(zdata).hexdigest()
release = {"tag_name": "v" + NEW, "body": "Testrelease", "html_url": "x",
           "assets": [{"name": "XimajRoboSim-" + NEW + ".zip", "browser_download_url": "https://t/zip", "size": len(zdata)},
                      {"name": "XimajRoboSim-" + NEW + ".zip.sha256", "browser_download_url": "https://t/sha", "size": 80}]}


class R(io.BytesIO):
    def __init__(self, b):
        super().__init__(b)
        self.headers = {"Content-Length": str(len(b))}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass


def fake_get(url, timeout=15):
    if url == update.API:
        return R(json.dumps(release).encode())
    if url.endswith("/zip"):
        return R(zdata)
    if url.endswith("/sha"):
        return R(f"{sha}  XimajRoboSim-{NEW}.zip\n".encode())
    raise RuntimeError(url)


update._get = fake_get
info = update.check()
print("1) check:", {k: info[k] for k in ("current", "latest", "available")})
assert info["available"] and info["latest"] == NEW
update.download(info, lambda f: None)
print("2) download+SHA ok, staging:", os.path.isdir(update.STAGING), "pending:", os.path.exists(update.PENDING))
v = update.apply_pending()
print("3) apply_pending ->", v)
print("   neue Datei vorhanden:", os.path.exists(os.path.join(app, "NEU.txt")))
print("   version.py:", open(os.path.join(app, "version.py")).read().strip().splitlines()[0])
print("   Backup:", os.listdir(update.BACKUP))
# Manipulierter Download muss abgelehnt werden
zdata_good = zdata
zdata = zdata_good[:-10] + b"0123456789"
open(os.path.join(app, "version.py"), "w").write(f'VERSION = "{CUR}"\nUPDATE_REPO = "NBFinn/XimajRoboSim"\n')
importlib.reload(sys.modules["version"]); importlib.reload(update); update._get = fake_get
try:
    update.download(update.check(), None)
    print("4) FEHLER: manipulierte Datei akzeptiert!")
except RuntimeError as e:
    print("4) manipulierte Datei abgelehnt:", e)
ok = update.rollback()
print("5) rollback:", ok, "| NEU_IN_101 weg:", not os.path.exists(os.path.join(app, "NEU.txt")))
shutil.rmtree(tmp, ignore_errors=True)
