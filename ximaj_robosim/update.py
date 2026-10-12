"""Update-Dienst der Ximaj RoboSim.

Quelle: GitHub-Releases von version.UPDATE_REPO (neuestes Release).
Ablauf: pruefen -> (Nutzer bestaetigt) -> Asset laden -> SHA-256 pruefen -> in Staging entpacken
        -> beim naechsten Start durch apply_pending() einspielen (Backup der alten Version).
Release-Konvention (im Repo veroeffentlichen):
  * Tag  vX.Y.Z
  * Asset  XimajRoboSim-X.Y.Z.zip   (Inhalt: der Ordner ximaj_robosim/ bzw. dessen Dateien)
  * Asset  XimajRoboSim-X.Y.Z.zip.sha256   (Pruefsumme, erste Spalte = Hex-SHA256)
Nutzerdaten (Projekte, Einstellungen) liegen ausserhalb des Programmordners und bleiben unberuehrt.
"""
import hashlib
import json
import os
import re
import shutil
import sys
import time
import urllib.error
import urllib.request
import zipfile

from version import VERSION, UPDATE_REPO
import release_access

FROZEN = getattr(sys, "frozen", False)
APP_DIR = os.path.dirname(sys.executable) if FROZEN else os.path.dirname(os.path.abspath(__file__))
EXE_NAME = os.path.basename(sys.executable) if FROZEN else None
STAGING = os.path.join(APP_DIR, "_update_staging")
BACKUP = os.path.join(APP_DIR, "_backup")
PENDING = os.path.join(APP_DIR, "_update_pending.json")
API = f"https://api.github.com/repos/{UPDATE_REPO}/releases/latest"
UA = "XimajRoboSim-Updater"
KEEP = {"_update_staging", "_backup", "_update_pending.json", "__pycache__", "settings.json"}


def _ver(s):
    return tuple(int(x) for x in re.findall(r"\d+", s)[:3]) or (0,)


def _get(url, timeout=15):
    return release_access.get(url, UPDATE_REPO, UA, timeout)


def check():
    """-> dict(available, current, latest, notes, url, sha_url, name) oder dict(error=...)"""
    try:
        with _get(API) as r:
            rel = json.loads(r.read().decode("utf8"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return {"error": f"GitHub meldet 404 für {UPDATE_REPO}. Das Repository ist privat, nicht vorhanden oder enthält noch kein öffentliches Release. "
                    "Für private Releases wird die vorhandene GitHub-CLI-Anmeldung verwendet. Falls diese fehlt oder keinen Zugriff hat, "
                    "unter Update / Info einen GitHub-Zugang mit Leserechten für dieses Repository hinterlegen.", "current": VERSION}
        return {"error": f"Update-Server meldet Fehler {e.code}", "current": VERSION}
    except Exception as e:
        return {"error": f"Update-Server nicht erreichbar: {e}", "current": VERSION}
    tag = rel.get("tag_name", "")
    info = {"current": VERSION, "latest": tag.lstrip("vV"), "notes": rel.get("body", ""),
            "available": False, "page": rel.get("html_url", "")}
    if _ver(tag) <= _ver(VERSION):
        return info
    assets = rel.get("assets", [])
    setups = [a for a in assets if a["name"].lower().endswith(".exe") and "setup" in a["name"].lower()]
    zips = [a for a in assets if a["name"].lower().endswith(".zip")]
    # EXE -> Setup bevorzugen; Quellmodus -> ZIP
    if FROZEN and setups:
        a, kind = setups[0], "setup"
    elif zips:
        a, kind = zips[0], "zip"
    elif setups:
        a, kind = setups[0], "setup"
    else:
        info["error"] = "Release enthaelt weder Setup noch ZIP"
        return info
    sha = next((x for x in assets if x["name"] == a["name"] + ".sha256"), None)
    info.update(available=True, url=a.get("url") or a["browser_download_url"], name=a["name"], size=a.get("size", 0),
                sha_url=(sha.get("url") or sha["browser_download_url"]) if sha else None, kind=kind)
    return info


def is_installed():
    """True, wenn die EXE ueber das Setup installiert wurde (Deinstallationsdatei vorhanden)."""
    return FROZEN and any(n.lower().startswith("unins") and n.lower().endswith(".exe") for n in os.listdir(APP_DIR))


def download(info, progress=None):
    """Laedt, verifiziert und entpackt nach STAGING. Wirft Exception bei Fehler."""
    if not info.get("sha_url"):
        raise RuntimeError("Release hat keine .sha256-Datei - Update aus Sicherheitsgruenden abgelehnt")
    with _get(info["sha_url"]) as r:
        expected = r.read().decode("utf8").split()[0].lower()
    if info.get("kind") == "setup":
        cache = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "XimajRoboSim", "updates")
        os.makedirs(cache, exist_ok=True)
        if os.path.basename(info["name"]) != info["name"] or not re.fullmatch(r"[A-Za-z0-9_.-]+", info["name"]):
            raise RuntimeError("Ungültiger Paketname")
        tmp = os.path.join(cache, info["name"])
    else:
        tmp = os.path.join(APP_DIR, "_update_download.zip")
    target = tmp
    tmp = target + ".part"
    h = hashlib.sha256()
    with _get(info["url"], 60) as r, open(tmp, "wb") as f:
        total = int(r.headers.get("Content-Length") or info.get("size") or 0)
        got = 0
        while True:
            b = r.read(65536)
            if not b:
                break
            f.write(b)
            h.update(b)
            got += len(b)
            if progress and total:
                progress(got / total)
    if h.hexdigest() != expected:
        os.remove(tmp)
        raise RuntimeError("Pruefsumme stimmt nicht - Download verworfen")
    os.replace(tmp, target)
    tmp = target
    if info.get("kind") == "setup":
        with open(PENDING, "w", encoding="utf8") as f:
            json.dump({"version": info["latest"], "from": VERSION, "time": time.time(), "setup": tmp}, f)
        return True
    shutil.rmtree(STAGING, ignore_errors=True)
    os.makedirs(STAGING)
    with zipfile.ZipFile(tmp) as z:
        root = os.path.realpath(STAGING)
        for m in z.infolist():
            dest = os.path.realpath(os.path.join(STAGING, m.filename))
            if not dest.startswith(root + os.sep) and dest != root:
                raise RuntimeError("Unsicherer Pfad im ZIP - abgebrochen")
        z.extractall(STAGING)
    os.remove(tmp)
    # evtl. Unterordner ximaj_robosim/ abflachen
    entries = os.listdir(STAGING)
    if len(entries) == 1 and os.path.isdir(os.path.join(STAGING, entries[0])):
        sub = os.path.join(STAGING, entries[0])
        for n in os.listdir(sub):
            shutil.move(os.path.join(sub, n), os.path.join(STAGING, n))
        os.rmdir(sub)
    marker = EXE_NAME if FROZEN else "main.py"
    if not os.path.exists(os.path.join(STAGING, marker)):
        shutil.rmtree(STAGING, ignore_errors=True)
        raise RuntimeError("Update-Paket unvollstaendig (Startdatei fehlt)")
    with open(PENDING, "w", encoding="utf8") as f:
        json.dump({"version": info["latest"], "from": VERSION, "time": time.time()}, f)
    return True


def apply_pending():
    """Beim Start VOR allen anderen Imports aufrufen. -> Versionsstring wenn ein Update eingespielt wurde."""
    if FROZEN:
        # Setup-Update ist durchgelaufen, wenn die EXE jetzt die neue Version hat
        if os.path.exists(PENDING):
            try:
                meta = json.load(open(PENDING, encoding="utf8"))
                if _ver(meta.get("version", "")) <= _ver(VERSION):
                    os.remove(PENDING)
                    s = meta.get("setup")
                    # Geprüfte Setups im Benutzer-Cache für spätere Rückkehr behalten.
                    pass
                    return meta.get("version")
            except Exception:
                pass
        return None     # EXE: Einspielen uebernimmt restart_and_apply()
    if not (os.path.exists(PENDING) and os.path.isdir(STAGING)):
        return None
    try:
        meta = json.load(open(PENDING, encoding="utf8"))
        bdir = os.path.join(BACKUP, meta.get("from", "alt"))
        shutil.rmtree(bdir, ignore_errors=True)
        os.makedirs(bdir)
        for n in os.listdir(APP_DIR):
            if n in KEEP:
                continue
            shutil.move(os.path.join(APP_DIR, n), os.path.join(bdir, n))
        for n in os.listdir(STAGING):
            shutil.move(os.path.join(STAGING, n), os.path.join(APP_DIR, n))
        shutil.rmtree(STAGING, ignore_errors=True)
        os.remove(PENDING)
        return meta.get("version")
    except Exception as e:
        print("Update fehlgeschlagen:", e, file=sys.stderr)
        rollback()
        return None


def rollback():
    """Stellt die zuletzt gesicherte Version wieder her."""
    if not os.path.isdir(BACKUP):
        return False
    vers = sorted(os.listdir(BACKUP), key=_ver)
    if not vers:
        return False
    src = os.path.join(BACKUP, vers[-1])
    for n in os.listdir(APP_DIR):
        if n in KEEP:
            continue
        p = os.path.join(APP_DIR, n)
        shutil.rmtree(p, ignore_errors=True) if os.path.isdir(p) else os.remove(p)
    for n in os.listdir(src):
        shutil.move(os.path.join(src, n), os.path.join(APP_DIR, n))
    shutil.rmtree(src, ignore_errors=True)
    return True


def build_release_zip(out_dir):
    """Hilfsfunktion fuer dich als Herausgeber: erzeugt ZIP + .sha256 fuer ein GitHub-Release."""
    name = f"XimajRoboSim-{VERSION}.zip"
    zp = os.path.join(out_dir, name)
    with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as z:
        for r, d, files in os.walk(APP_DIR):
            d[:] = [x for x in d if x not in KEEP]
            for f in files:
                if f in KEEP or f.endswith(".pyc"):
                    continue
                full = os.path.join(r, f)
                z.write(full, os.path.join("ximaj_robosim", os.path.relpath(full, APP_DIR)))
    h = hashlib.sha256(open(zp, "rb").read()).hexdigest()
    open(zp + ".sha256", "w").write(f"{h}  {name}\n")
    return zp


def restart_and_apply():
    """Nach 'Jetzt neu starten': Quellmodus -> neu starten (apply_pending greift), EXE -> Hilfsskript."""
    import subprocess
    if not FROZEN:
        subprocess.Popen([sys.executable] + sys.argv)
        return
    with open(PENDING, encoding="utf8") as pending:
        meta = json.load(pending)
    if meta.get("setup"):
        # Installer still ausfuehren; er schliesst die App, installiert und startet sie neu
        subprocess.Popen([meta["setup"], "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS",
                          f"/DIR={APP_DIR}", f"/LOG={os.path.join(APP_DIR, '_update_setup.log')}"],
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), close_fds=True)
        return
    bdir = os.path.join(BACKUP, meta.get("from", "alt"))
    bat = os.path.join(APP_DIR, "_apply_update.bat")
    with open(bat, "w", encoding="utf8") as f:
        f.write(f'''@echo off
:wait
tasklist /fi "imagename eq {EXE_NAME}" | find /i "{EXE_NAME}" >nul && (timeout /t 1 /nobreak >nul & goto wait)
robocopy "{APP_DIR}" "{bdir}" /E /XD _backup _update_staging /XF _apply_update.bat _update_pending.json >nul
robocopy "{STAGING}" "{APP_DIR}" /E /IS /IT >nul
rmdir /s /q "{STAGING}"
del "{PENDING}"
start "" "{os.path.join(APP_DIR, EXE_NAME)}"
(goto) 2>nul & del "%~f0"
''')
    subprocess.Popen(["cmd", "/c", bat], creationflags=0x08000000, close_fds=True)


def prepare_rollback(progress=None):
    """Die jüngste ältere stabile Setup-Version prüfen und zur Installation vormerken."""
    with _get(f"https://api.github.com/repos/{UPDATE_REPO}/releases?per_page=100") as response:
        releases = json.loads(response.read().decode("utf8"))
    older = sorted((r for r in releases if not r.get("draft") and not r.get("prerelease")
                    and _ver(r.get("tag_name", "")) < _ver(VERSION)),
                   key=lambda r: _ver(r.get("tag_name", "")), reverse=True)
    for release in older:
        try:
            info = release_access.release_info(release, VERSION)
        except RuntimeError:
            continue
        if info["kind"] != "setup":
            continue
        download(info, progress)
        return info["latest"]
    raise RuntimeError("Keine ältere stabile Version mit Setup und Prüfsumme verfügbar.")
