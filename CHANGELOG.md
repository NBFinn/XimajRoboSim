## 1.4.0

- Greifer nimmt ein später in Reichweite kommendes Teil bei weiterhin aktivem Greifbefehl auf. Pro Roboter wird höchstens ein Teil gehalten; Greifabstand wird an der gedrehten Werkstück-Hülle geprüft.
- Werkzeugbereich zeigt Greifbefehl, gehaltenes Teil, Abstand und doppelt verwendete Ausgangszuordnungen.

- Feste, sprechende OPC-UA-NodeIds für Roboter, Achsen, TCP, E/A, Komponenten und Methoden. Vorhandene Browse-Pfade bleiben erhalten; frühere automatisch erzeugte numerische NodeIds müssen im Client neu zugeordnet werden.
- Roboterposition in aktueller BASE und Welt, Achs- und Pose-Arrays sowie eingelernte Punkte mit X/Y/Z, A/B/C, S/T und Gültigkeitsangaben.
- Neue Teach-Punkte speichern den Weltbezug der BASE und E1. Bei älteren Punkten bleibt der Weltbezug ausdrücklich unbekannt; keine erfundenen Koordinaten.
- Knotenübersicht unter Konnektivität: Filter, letzte Werte, Datentyp, Zugriff, Einheit, NodeId kopieren und vollständiger CSV-/JSON-Export.
- Gelöschte Roboter, Punkte und ersetzte Komponenten werden aus dem OPC-UA-Adressraum entfernt. Befehle für entfernte Roboter werden verworfen.
- Server meldet Bereitschaft erst nach Aufbau der Roboterknoten. Portsuche bleibt im gültigen TCP-Bereich; Start-Zeitüberschreitung wird gemeldet.

## 1.3.4

- **Realistische Katalogteile:** Alle Teile haben eigene, detaillierte 3D-Modelle: Förderband mit Alu-Profilen, Getriebemotor und Stützen, Rollenbahn mit runden Tragrollen, Schutzzaun mit Pfosten, Fußplatten und Drahtgitter, Lichtschranke und Farbsensor mit Gehäuse, Linse und Reflektor, Signalleuchte, Zuführtrichter, Auffangbehälter, Euro-Palette, Schaltschrank, Arbeitstisch, Gitterbox, Lagerregal, Roboter-Sockel, Spannvorrichtung, Säule und Karton.
- **Darstellung wählbar:** In den Eigenschaften lässt sich festlegen, wie ein Quader, Zylinder oder Förderer aussieht (z. B. Euro-Palette, Schaltschrank, Rollenbahn). Für Förderer zusätzlich Rahmenfarbe, Gurtfarbe und Anzahl der Stützen.
- Ältere Projekte erhalten die neue Darstellung automatisch anhand der Katalognamen. Kollisionen und Maße bleiben unverändert.

## 1.3.3

- **Neues Logo:** Ximaj RoboSim hat ein eigenes Logo (Sechseck mit Roboterarm). Es erscheint in der Kopfzeile, im Startbild, als Programm-Icon und im Setup; auf dunklen Flächen in heller Ausführung.
- **Rückgängig / Wiederholen** (Strg+Z / Strg+Y, START > Zwischenablage): bis zu 50 Schritte für Szene, Roboter und Programme. Ungespeicherte Änderungen zeigt der Fenstertitel mit *.
- **Automatische Sicherung** alle 2 Minuten. Nach einem Absturz bietet die App beim Start die Wiederherstellung an. Beim Schließen mit ungespeicherten Änderungen: Speichern, Verwerfen oder Abbrechen.

## 1.3.2

- **OPC-UA-Server startet zuverlässig:** Ist der Port belegt (z. B. 4840 durch den KUKA-Dienst „KukaOpcUa_Simulation“), wählt der Server automatisch den nächsten freien Port und nennt den belegenden Dienst; vorher startete er dann gar nicht und Clients landeten beim fremden Server.
- Endpunkte mit PC-Name, localhost und IP-Adressen (Doppelklick kopiert); Option „nur auf diesem PC“; Anzahl der E/A einstellbar (Standard 128).
- Neue Knoten: Simulation (State, Time, SpeedFactor, StartAll/StopAll/ResetAll), Robots/<Name> für **jeden** Roboter mit eigenen Methoden, Components (Sensoren, Förderer mit schreibbarer Geschwindigkeit, Teile-Erzeuger, Farbsensoren, Leuchten). Bisherige Knoten bleiben erhalten.
- **Neu: OPC-UA-Client** wie in iiQWorks: Verbindung zu SPS/Steuerung/Leitsystem, Variablen durchsuchen und mit $IN/$OUT, Override, Geschwindigkeit, Achsen, TCP und Zustand koppeln (lesen/schreiben), im Projekt gespeichert.
- OPC-UA-Statusanzeige in der Simulationsleiste.
- **Design wie ximaj.com:** durchgehend dunkler Navy-Verlauf, halbtransparente Karten mit 16 px Radius, weiße Saira-Überschriften, Knöpfe in Ximaj-Blau; dunkle Ximaj-Halle in der 3D-Ansicht (helle Halle weiter unter ANSICHT, Auswahl wird gemerkt); deutsche Texte in Standarddialogen.
- **Aufgeräumt:** Funktionen ohne echten Nutzen entfernt (Forum, Blog, Akademie, Xpert, Topologie, „Aktualisiere von Instanz“, „Neu“/„Eigenschaften“/„Verknüpfung erstellen“ in MODELLIERUNG, doppelte Wizards und Scripting-Hilfe). „Auf Steuerung übertragen“ heißt jetzt ehrlich „Steuerungspaket exportieren“, „RCS Export“ heißt „Maschinendaten exportieren“.
- Spiegeln funktioniert jetzt auch für Quader und Zylinder und bleibt beim Speichern erhalten.
- „Zuletzt verwendet“ in der DATEI-Ansicht wird jetzt gefüllt.

## 1.3.1

- Menüband ohne Doppelungen: MODELLIERUNG enthält nur Modellierfunktionen, PROGRAMM eine eigene Gruppe „Roboter“ (Jog, World Frame, Austauschen, Punkt einlernen), Projektanalyse unter START.
- Antriebskonfiguration legt eine Projektkopie des Robotermodells an; das mitgelieferte Modell bleibt unverändert, die Änderung wird im Projekt gespeichert.
- Projekt zusammenführen: eindeutige Namen auch für Roboter, Signalverbindungen und Eltern werden mit umbenannt.
- Konfigurationsvorschlag und „Auf Steuerung übertragen“ berücksichtigen die eingelernten Punkte.
- Roboter kopieren/einfügen übernimmt Werkzeug, Programm und Punkte.
- Interagieren hält Förderbänder zuverlässig an.
- Ursprung frei wählbar auch bei Quadern und Zylindern (Umwandlung in formgleiches Netz, bleibt beim Speichern erhalten).
- Eigene Komponenten werden im richtigen Katalogformat gespeichert.
- Optionsfelder im Menüband sichtbar gestaltet.

## 1.3.0

- **Menüband** im Ximaj-Design mit den Reitern DATEI, START, MODELLIERUNG, PROGRAMM, KONFIGURATION, ANSICHT und HILFE, eigene Symbole, Befehlssuche, einklappbar (Strg+F1); DATEI-Ansicht mit zuletzt verwendeten Projekten.
- **3D-Bearbeitung:** Achsenkreuz zum Verschieben, Drehring, Positionsraster (fest oder automatisch), Mehrfachauswahl (Strg+Klick, Umschalt+Rahmen), PnP-Andocken an Förderbänder, Interagieren (Förderer an/aus, Teile anfordern, Signale schalten), Jog am Werkzeugpunkt.
- **Werkzeuge:** Kopieren/Einfügen/Löschen, Gruppieren, Fügen/Ablösen (auch an den Roboterflansch), Andocken, Ausrichten, Messen, Bemaßung linear und Winkel, Ursprung positionieren/verschieben, Spiegeln, Verhalten zuweisen, Komponenten im Katalog speichern, Assistenten (Förderstrecke, Schutzzaun, Palette).
- **Programm:** Robot World Frame verschieben (zur Referenz/zur Welt), Roboter austauschen, Lehr-Overlay, Simulationskonfiguration, Kollisionserkennung bearbeiten, Achslimits farbig anzeigen/anhalten/melden, Traces mit Online-Aufzeichnung, Analyse und Diagramm.
- **Konfiguration:** E/A-Verschaltungseditor, Verschaltungsübersicht, Device Catalog, Topologie, automatisches Routing, Antriebskonfiguration, Konfigurationsvorschlag, Maschinendaten-Export, Übertragen auf Steuerung, Projekt zusammenführen, Langtext-Editor.
- **Projektanalyse** im Hintergrund mit Fenster und optionalem Popup.
- **Hilfe:** Hilfe mit Suche, Tastenkürzel, Python-/OPC-UA-/XRL-Referenz, Akademie, Fehlerbericht, VS-Code-Projekt, geführter Arbeitsablauf.
- **VCMX-Komponentenskripte** (vcCore) werden nach Rückfrage ausgeführt: Farbsensor, Farbanzeige und Zufallsfarben verhalten sich wie im Original.
- **Roboter:** Servomotoren mit Kühlrippen, Kabelstrang, Gewichtsausgleich, Lack-/Metall-Oberflächen; CAD-Geometrie je Glied und Lackfarbe im Roboter-Editor.

## 1.2.6

- Neues Robotermodell: glatte Gussgehäuse statt Quadern (Fuß mit Schrauben, Karussell, Schulterguss, konischer Oberarm, Motorpaket, Handgelenkgabel, Flansch mit Lochbild); Armstärke wächst mit der Traglast.
- Roboterbibliothek mit Kinematiken realer Hersteller (KUKA, ABB, FANUC, Yaskawa, Stäubli) nach öffentlichen Datenblättern, im Katalog nach Hersteller gruppiert. Nur Maße und Achsdaten, keine Hersteller-CAD-Daten.
- Roboter-Editor: eigene 6-Achs-Roboter aus einer Vorlage ableiten, Maße, Achsgrenzen, Geschwindigkeiten und Traglast festlegen; eigene Roboter werden im Projekt mitgespeichert.
- VCMX: Signalverbindungen zwischen Objekten und Roboter-E/A werden übernommen: Förderband-Engine, Creator über CreationSignal (ein Teil je steigender Flanke), Sensoren, Farbsensor mit Farbausgängen, Farbanzeige; Objekt-zu-Objekt-Verbindungen über interne Signale.
- Zufallsfarben für erzeugte Teile, wenn der Creator mehrere Materialien hat.
- Neu im Katalog: Farbsensor, Farbanzeige (Signalleuchte), Zuführung mit Zufallsfarben.
- Reset entfernt erzeugte Teile und stellt Werkstücke, Roboter, E/A und Zeit wieder her.

## 1.2.5

- VCMX Advanced Creator: Ausgabepunkt aus Komponentenabmessungen und Drehung statt Bodenursprung importieren.
- Creator-Intervall, Blockabmessungen und Standardmaterialfarbe uebernehmen.
- Untitled.vcmx: Mehrfacherzeugung und Foerdertransport im Regressionstest geprueft. Die originalen VC-CreationSignal-Verbindungen sind weiterhin nicht nachgebildet.

## 1.2.4

- Startbildschirm bleibt mindestens drei Sekunden sichtbar; die Ladezeit wird mitgerechnet.

# Änderungen

## 1.2.3

- Modellieren-Tab für eigene Quader und Zylinder mit Maßen, Pose und Farbe; Speicherung im Projekt.
- Importdialog wählt das Hauptprogramm aus; globale Konfigurationsdaten umfassen auch FDAT/PDAT/LDAT.
- Laufzeitfehler öffnen automatisch die Meldungen und zeigen die konkrete Ursache in der Statusleiste.
- Private GitHub-Releases werden über vorhandene CLI-Anmeldung oder benutzerbezogen verschlüsselten Zugang abgefragt und geladen.
- Vorherige stabile Setup-Version wird direkt in der App geladen, geprüft und zur Installation vorbereitet.
- Geprüfte Setups bleiben im Benutzer-Cache; Installation verwendet das aktuelle Programmverzeichnis.
- Aufgeschobene Installation lässt sich über einen eigenen Zustand des Installationsbuttons fortsetzen.

## 1.2.2

- Importierte VCMX- und Textprogramme wechseln in den XRL-Modus und werden im Robotermodell gespeichert.
- Die Modulauswahl im Import-Bericht behält Unterprogramme und globale Konfigurationsdaten bei.
- E/A-Bereichsauswahl für alle Signale 1–1024, einschließlich hoher importierter Signalnummern wie Eingang 119.
- WAIT FOR zeigt die wartende Programmzeile und einen Hinweis auf die E/A-Bedingung.
- Seitenbereiche sind bis auf 100 Pixel Breite beziehungsweise 80 Pixel Höhe verkleinerbar; große Inhalte bleiben scrollbar.
- Manuelle Updatesuche öffnet den Ergebnisbereich und zeigt Fortschritt, Fehler und Versionsvergleich.
- Private Release-Quellen werden ausdrücklich erklärt; GitHub-Releases lassen sich direkt im Browser öffnen.
- EXE-Updates bevorzugen Setup-Dateien, auch bei portablen Builds.

## 1.2.1

- Neu gebautes Setup und portables Paket des vorhandenen Quellstands.
- Versionsnummer erhöht, damit Version 1.2.0 das Release als Update erkennt.
- Die gemeldeten VCMX-, Fenstergrößen- und Update-Anzeigeprobleme sind in diesem Release noch nicht korrigiert.

## 1.2.0

**Mehrere Roboter in einer Zelle**
- Beliebig viele Roboter, jeder mit eigenem Programm, Werkzeug, Basis, Punkten und Statements
- „Start“ startet alle Roboter gleichzeitig; Koordination über Signale (z. B. `WAIT FOR $OUT[10]`)
- Kollisionsprüfung auch zwischen den Robotern
- Katalog: „Als weiteren Roboter einsetzen“

**Linearachse (E1)**
- Roboter auf Verfahrschiene mit frei wählbaren Grenzen und Geschwindigkeit, mit Tippbetrieb
- Ziele mit `E1` in PTP, LIN und CIRC; die Achse fährt synchron mit
- Detailgetreue Darstellung: Schiene, Führungen, Zahnstange, Energiekette, Schlitten, Endanschläge
- Import: Roboter auf Linearachsen aus alten Projekten samt Software-Endschaltern

**Statement-Programmierung (ohne Code)**
- Programme aus Bausteinen: PTP/LIN/CIRC (geteacht), Warten, Signale, Impuls, Greifer, Schleifen,
  Wenn/Sonst, Geschwindigkeit, Unterprogramm, Meldung, Kommentar, HALT
- Bearbeiten-Dialog, Teach, Anfahren, Verschieben, Strukturprüfung, Live-Markierung beim Ablauf
- XRL wird automatisch erzeugt

**Prozesse (Menü „Prozesse“)**
- Bahnprozess (Schweißen, Kleben, Dichten): Kontur aus der Bauteilgeometrie mit Höhe, Versatz, Anstell- und
  Stechwinkel, An-/Abfahrt, Prozess-Signal
- Punktprozess (Punktschweißen, Inspektion): entlang der Kontur oder als Raster, mit Verweilzeit und Impuls
- Flächenprozess (Lackieren, Polieren, Entgraten): Mäanderbahnen mit Bahnbreite, Überlappung und
  Abdeckungsanzeige
- Freie Drehung um die Werkzeugachse für beste Erreichbarkeit; Vorschau, Kennzahlen, Zeitschätzung

**Materialfluss**
- Neue Senke (Teile-Abnahme); Durchsatz-Kennzahlen (fertig, erzeugt, im Umlauf, Teile/h)
- E/A-Mapping: Signalnamen, 64 Ein- und Ausgänge, automatische Vorschläge

**CAD und Export**
- CAD-Import: STEP, IGES (zusätzlich zu STL, OBJ, PLY, GLB, 3MF); „CAD-Netz vereinfachen“
- 2D-Hallenlayout aus DXF als Grundriss auf dem Boden
- Video-Export als MP4; 3D-Präsentation als HTML-Datei, die sich im Browser drehen lässt

**Copilot**
- Layout und Simulation per Texteingabe in der Kopfleiste, z. B. „füge ein Förderband 3 m bei x 1500 y -800 hinzu“,
  „neuer Roboter XR-20 bei x 2500“, „Zaun um die Zelle“, „starte Simulation“; läuft lokal

**Realismus**
- Schutzzäune mit Pfosten, Rahmen und Gittergeflecht
- Korrekte Darstellung halbtransparenter Flächen (Sensorfelder, Abdeckung)

## 1.1.0

**Realistische Darstellung**
- Helle Hallenansicht mit Boden und Raster (umschaltbar unter *Ansicht*), Kantenglättung (8× MSAA)
- Hallenlicht mit Glanzlichtern und Fülllicht, weiche Bodenschatten (abschaltbar)
- Förderbänder detailgetreu: Gurt mit Gurtfarbe, Aluminium-Seitenprofile, Umlenktrommeln, Antriebsmotor,
  Füße mit Querstrebe und Stellfüßen, mitlaufende Gurtmarkierung
- Neu: Kurvenförderer (beliebiger Winkel, links/rechts), Teile werden entlang des Bogens transportiert
- Große CAD-Modelle werden deutlich schneller gezeichnet

**Import alter Projekte (.vcmx)**
- Gurt- und Bauteilfarben werden aus der Materialtabelle übernommen
- Kurvenförderer werden als echte Bögen übernommen, inklusive Anzahl der Füße
- `SIGNAL`-Deklarationen (Einzelbits und Bitgruppen) werden unterstützt

**Installation und Updates**
- Neu: Setup-Datei (Installation ohne Admin-Rechte in den Benutzerordner, Startmenü, Desktop-Symbol,
  Doppelklick auf `.xrsim`-Projekte)
- Installierte Versionen aktualisieren sich über das Setup: im Hintergrund, mit SHA-256-Prüfung und Neustart
- Projekte lassen sich per Kommandozeile oder Doppelklick öffnen

## 1.0.0
- Erste Version: Roboter XR-Reihe, XRL-Programmierung, Simulation, Katalog, Analyse, Sicherheit,
  OPC-UA-Server, Python-Skripte, Import alter Projekte, Update-Dienst
