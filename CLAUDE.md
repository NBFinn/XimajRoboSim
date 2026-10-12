# Ximaj RoboSim – Hinweise für Claude

Desktop-Programm (Windows) zum Planen, Programmieren und Simulieren von Roboterzellen. Python + PyQt6 + PyOpenGL, ausgeliefert als PyInstaller-EXE mit Inno-Setup-Installer. GitHub-Repo: `NBFinn/XimajRoboSim`.

## Sprache und Stil
- Alle Texte für Nutzer (UI, CHANGELOG, Commit-Messages, README) auf **Deutsch**, einfache Sprache, keine Marketingfloskeln.
- Commit-Messages kurz und beschreibend auf Deutsch (z. B. „Rückgängig/Wiederholen und automatische Sicherung“).

## Rechtliches – wichtig
Eigenständige Software: **keinen Code, keine CAD-Modelle, Bibliotheken oder Marken** von Roboterherstellern (KUKA, ABB, FANUC …) oder anderen Simulationsprogrammen (Visual Components, iiQWorks …) übernehmen. Robotermodelle (XR-Reihe), Katalogteile, XRL, Design und Icons sind Eigenarbeit. Beim `.vcmx`-Import nur Positionen/Maße/Parameter/Programme übernehmen, fremde Netzgeometrie als Platzhalter.

## Aufbau
- `ximaj_robosim/` – Quellcode, Einstieg `main.py`. Module werden **flach** importiert (`from sim import Simulation`), nicht als Paket; Tests setzen dafür `sys.path` auf `ximaj_robosim/`.
  - `sim.py` Simulation/Szene · `kinematics.py` Kinematik · `xrl.py` / `statements.py` Programmiersprache XRL und Bausteine
  - `viewer.py` 3D-Ansicht · `ribbon.py` / `ui_ribbon.py` Menüband · `theme.py` Ximaj-Design (dunkel, Navy, Ximaj-Blau)
  - `opcua_srv.py` / `opcua_client.py` OPC UA · `update.py` Update über GitHub-Releases · `history.py` Undo/Redo + Autosave
  - `vcmx_import.py`, `cad.py`, `rsc_parser.py` Importe · `version.py` enthält `VERSION` und `UPDATE_REPO`
- `tests/` – `test_*.py` sind echte Tests (unittest), `ui_*.py`, `inspect_*.py`, `*debug*.py` sind Hilfs-/Screenshot-Skripte.
- `tools/` – Build-Helfer (`version_info.py`, `make_icon.py`).
- `build/`, `dist/`, `release/` und die `*.png`-Screenshots im Wurzelordner sind generiert (gitignored) – nicht bearbeiten.

## Befehle
```
pip install -r requirements.txt
python ximaj_robosim\main.py                              # aus dem Quellcode starten
python -m pytest tests -q                                 # alle Tests (oder einzeln: python tests\test_cells.py)
powershell -ExecutionPolicy Bypass -File build.ps1        # EXE + ZIP + Setup + latest.json in release\v<Version>
powershell -ExecutionPolicy Bypass -File publish.ps1      # GitHub-Release (braucht gh auth login)
dist\XimajRoboSim\XimajRoboSim.exe --selftest             # Selbsttest der gebauten EXE
```

## Release-Ablauf
1. `VERSION` in `ximaj_robosim/version.py` erhöhen.
2. Abschnitt `## <Version>` oben in `CHANGELOG.md` anlegen – `publish.ps1` nimmt daraus die Release-Notes.
3. `build.ps1`, dann `publish.ps1` (Details: `GITHUB_UPDATE_ANLEITUNG.md`).
Veröffentlichen/Pushen nur nach ausdrücklicher Freigabe.

## Fallstricke
- Neue Abhängigkeiten auch in `build.ps1` eintragen (`--collect-*` / `--hidden-import`), sonst fehlen sie in der EXE.
- Projektdateien (`.xrsim`) müssen abwärtskompatibel bleiben; neue Felder mit Standardwerten laden.
- OPC-UA-Standardport 4840 ist oft durch den KUKA-Dienst belegt – der Server weicht automatisch aus, nicht „reparieren“.
