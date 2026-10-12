# Ximaj RoboSim

**Roboterzellen planen, programmieren und simulieren – eine Eigenentwicklung der Ximaj IT Solutions.**

Ximaj RoboSim ist eine eigenständige Software. Sie enthält keinen Code, keine CAD-Modelle, keine
Bibliotheken und keine Marken von Roboterherstellern oder anderen Simulationsprogrammen. Alle Robotermodelle (XR-Reihe),
Katalogteile, die Programmiersprache XRL, das Design und das Icon sind eigene Arbeiten.

## Neu seit 1.2

**1.4.0: feste OPC-UA-NodeIds, Live-TCP in BASE/Welt und eingelernte Roboterpunkte.** Knotenübersicht mit Export unter Konnektivität. Anleitung: [OPC-UA-ANBINDUNG.md](OPC-UA-ANBINDUNG.md).
Der Greifer prüft einen weiterhin aktiven Greifbefehl auch beim späteren Eintreffen eines Teils. Sein Status und doppelt verwendete Ausgänge erscheinen im Werkzeugbereich.

Mehrere Roboter pro Zelle · Linearachse E1 · Statement-Programmierung (Bausteine statt Code) ·
Bahn-, Punkt- und Flächenprozesse aus der Bauteilgeometrie · Senke und Durchsatzanalyse · E/A-Mapping ·
STEP/IGES- und DXF-Import · CAD-Vereinfachung · MP4- und HTML-3D-Export · Copilot (Texteingabe) ·
Selbsttest der EXE: `XimajRoboSim.exe --selftest`. Details in [CHANGELOG.md](CHANGELOG.md).

## Funktionen (Version 1.0)

| Bereich | Funktionen |
|---|---|
| Zellenaufbau | 3D-Ansicht, Katalog mit Robotern, Werkzeugen, Fördertechnik, Zellenbau, Werkstücken und Beispielzellen; eigene Katalogteile (JSON); CAD-Import STL/OBJ/PLY/GLB/3MF; Objekte per Klick wählen und bearbeiten |
| Roboter | 9 Modelle XR-5 … XR-40 (0,5–3,2 m, 3–500 kg), analytische Kinematik mit bis zu 8 Lösungen, Status/Turn, Achsgrenzen, Roboterfuß und BASE frei wählbar |
| Programmierung | XRL-Editor mit Syntaxhervorhebung, Interpreter (PTP/LIN/CIRC, REL, SPTP/SLIN/SCIRC, WITH, Schleifen, SWITCH, Unterprogramme, Funktionen, DEFDAT, WAIT, PULSE), Einzelschritt, Override, Zeitraffer |
| Teach | Achs- und kartesisches Verfahren (BASE/TOOL), Punkte einlernen, anfahren, als PTP/LIN einfügen |
| Simulation | Greifen/Ablegen, Förderbänder, Lichtschranken, Teile-Erzeuger, Schwerkraft, E/A-Signale |
| Analyse | Kollisionsprüfung (Hindernisse, Boden, Selbstkollision), Erreichbarkeitswolke, Szenen-Erreichbarkeit, Swept Volume (Anzeige und CSV), Taktzeit pro Zyklus, Energie- und Leistungsschätzung, Singularitätsanzeige |
| Sicherheit | Verbotszonen und Arbeitsräume, STOP 0 mit Anhalteweg |
| Altprojekte | Import von `.vcmx`/`.vcm`: Layout, Förderer, Sensoren, Roboter mit Originalmaßen und Achsgrenzen, Programme `.src`/`.dat`, Punkte, Werkzeuge und Basen |
| Konnektivität | OPC-UA-Server (Achsen, TCP, Zustand, E/A lesen und schreiben, Start/Stop/Pause/Reset/Programm laden), Python-3-Skriptkonsole |
| Export | Projekt (.xrsim), Programme (.xrl/.src), Konfiguration, 3D-Szene (GLB/OBJ/STL), Screenshot, Animation (GIF + PNG-Folge) |
| Updates | Automatische Prüfung über GitHub-Releases, SHA-256-Prüfung, Sicherung und Zurücksetzen |

## Starten

- **EXE:** `dist\XimajRoboSim\XimajRoboSim.exe`
- **Aus dem Quellcode:** `pip install -r requirements.txt`, dann `python ximaj_robosim\main.py`

## Bauen und veröffentlichen

```
powershell -ExecutionPolicy Bypass -File build.ps1
```

Danach die Schritte in [GITHUB_UPDATE_ANLEITUNG.md](GITHUB_UPDATE_ANLEITUNG.md) ausführen.

## Tests

```
python tests\test_cells.py        # Beispielzellen laufen komplett
python tests\test_update.py       # Update-Dienst Ende-zu-Ende (simuliertes Release)
python tests\test_opcua.py        # OPC-UA-Server mit echtem Client
python tests\test_import.py       # Import alter Projekte (Pfad in der Datei anpassen)
```

## Hinweise zum Import alter Projekte

Importiere nur eigene Projektdateien, für die du die Rechte hast. Netzgeometrien aus fremden Bibliotheken
werden bewusst nicht übernommen, sondern als Platzhalter-Körper dargestellt. Übernommen werden Positionen,
Maße, Parameter, Programme und Steuerungsdaten.
