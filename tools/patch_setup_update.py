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


patch("update.py", [
    ('''    zips = [a for a in rel.get("assets", []) if a["name"].lower().endswith(".zip")]
    if not zips:
        info["error"] = "Release enthaelt kein ZIP-Asset"
        return info
    a = zips[0]
    sha = next((x for x in rel.get("assets", []) if x["name"] == a["name"] + ".sha256"), None)
    info.update(available=True, url=a["browser_download_url"], name=a["name"], size=a.get("size", 0),
                sha_url=sha["browser_download_url"] if sha else None)
    return info''', '''    assets = rel.get("assets", [])
    setups = [a for a in assets if a["name"].lower().endswith(".exe") and "setup" in a["name"].lower()]
    zips = [a for a in assets if a["name"].lower().endswith(".zip")]
    # Installierte EXE -> Setup bevorzugen; Quellcode/portable -> ZIP
    if FROZEN and setups and is_installed():
        a, kind = setups[0], "setup"
    elif zips:
        a, kind = zips[0], "zip"
    elif setups:
        a, kind = setups[0], "setup"
    else:
        info["error"] = "Release enthaelt weder Setup noch ZIP"
        return info
    sha = next((x for x in assets if x["name"] == a["name"] + ".sha256"), None)
    info.update(available=True, url=a["browser_download_url"], name=a["name"], size=a.get("size", 0),
                sha_url=sha["browser_download_url"] if sha else None, kind=kind)
    return info


def is_installed():
    """True, wenn die EXE ueber das Setup installiert wurde (Deinstallationsdatei vorhanden)."""
    return FROZEN and any(n.lower().startswith("unins") and n.lower().endswith(".exe") for n in os.listdir(APP_DIR))'''),
    ('''    with _get(info["sha_url"]) as r:
        expected = r.read().decode("utf8").split()[0].lower()
    tmp = os.path.join(APP_DIR, "_update_download.zip")''', '''    with _get(info["sha_url"]) as r:
        expected = r.read().decode("utf8").split()[0].lower()
    if info.get("kind") == "setup":
        import tempfile
        tmp = os.path.join(tempfile.gettempdir(), info["name"])
    else:
        tmp = os.path.join(APP_DIR, "_update_download.zip")'''),
    ('''    if h.hexdigest() != expected:
        os.remove(tmp)
        raise RuntimeError("Pruefsumme stimmt nicht - Download verworfen")
    shutil.rmtree(STAGING, ignore_errors=True)''', '''    if h.hexdigest() != expected:
        os.remove(tmp)
        raise RuntimeError("Pruefsumme stimmt nicht - Download verworfen")
    if info.get("kind") == "setup":
        with open(PENDING, "w", encoding="utf8") as f:
            json.dump({"version": info["latest"], "from": VERSION, "time": time.time(), "setup": tmp}, f)
        return True
    shutil.rmtree(STAGING, ignore_errors=True)'''),
    ('''    if FROZEN or not (os.path.exists(PENDING) and os.path.isdir(STAGING)):
        return None     # EXE: Einspielen uebernimmt restart_and_apply() mit Hilfsskript''', '''    if FROZEN:
        # Setup-Update ist durchgelaufen, wenn die EXE jetzt die neue Version hat
        if os.path.exists(PENDING):
            try:
                meta = json.load(open(PENDING, encoding="utf8"))
                if _ver(meta.get("version", "")) <= _ver(VERSION):
                    os.remove(PENDING)
                    s = meta.get("setup")
                    if s and os.path.exists(s):
                        os.remove(s)
                    return meta.get("version")
            except Exception:
                pass
        return None     # EXE: Einspielen uebernimmt restart_and_apply()
    if not (os.path.exists(PENDING) and os.path.isdir(STAGING)):
        return None'''),
    ('''    if not FROZEN:
        subprocess.Popen([sys.executable] + sys.argv)
        return
    meta = json.load(open(PENDING, encoding="utf8"))''', '''    if not FROZEN:
        subprocess.Popen([sys.executable] + sys.argv)
        return
    meta = json.load(open(PENDING, encoding="utf8"))
    if meta.get("setup"):
        # Installer still ausfuehren; er schliesst die App, installiert und startet sie neu
        subprocess.Popen([meta["setup"], "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS",
                          f"/LOG={os.path.join(APP_DIR, '_update_setup.log')}"], close_fds=True)
        return'''),
])
patch("version.py", [('VERSION = "1.0.0"', 'VERSION = "1.1.0"')])
patch("main.py", [
    ('''        if self.settings.get("auto_update", True):''', '''        if len(sys.argv) > 1 and sys.argv[1].lower().endswith(".xrsim") and os.path.exists(sys.argv[1]):
            QTimer.singleShot(300, lambda: self.open_project(sys.argv[1]))
        if self.settings.get("auto_update", True):'''),
    ('''    def open_project(self):
        p, _ = QFileDialog.getOpenFileName(self, "Projekt öffnen", "", "Ximaj Projekt (*.xrsim)")''', '''    def open_project(self, path=None):
        p = path if isinstance(path, str) else QFileDialog.getOpenFileName(self, "Projekt öffnen", "", "Ximaj Projekt (*.xrsim)")[0]'''),
    ('''            if upd.rollback():''', '''            if upd.is_installed():
                QMessageBox.information(self, "Zurücksetzen", "Installierte Version: bitte das Setup der gewünschten "
                                        "älteren Version von der GitHub-Release-Seite ausführen.")
                return
            if upd.rollback():'''),
])
print("ok")
