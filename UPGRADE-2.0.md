# Ximaj RoboSim 2.0.0 – Bedienung und Entscheidungen

Das Upgrade erweitert die bestehende Anwendung. Ximaj-Farben, 3D-Zelle und Ladebildschirm bleiben erhalten.

## Zuerst eine funktionierende Zelle

Unter **Programm → Prüfen / Debuggen → Produktionscockpit** kannst du die Zelle prüfen. Die Prüfung sucht
unter anderem doppelte Namen, fehlende Verbindungsendpunkte, Syntaxfehler und unplausible Greiferausgänge.
Fehler verhindern den Start über die Oberfläche; Warnungen müssen bewertet werden. Die Prüfung führt
keine Roboterprogramme aus und ersetzt keinen vollständigen Zyklustest oder eine Kollisionsprüfung.

Die Signalübersicht zeigt die tatsächlich anliegenden booleschen Werte der gespeicherten Verbindungen.
Der Filter sucht in Diagnose und Signalen. Ein JSON-Bericht enthält das Projekt und die Diagnose;
er kann deshalb persönliche Pfade und Programme enthalten. Es erfolgt keine automatische Übertragung.

## Programm schrittweise verstehen

Im XRL-Editor setzt ein Klick neben die Zeilennummer oder **F9** einen Haltepunkt. Er hält die ganze
Zelle **vor** der betreffenden Anweisung an. **F5** setzt fort; **F10** führt schrittweise weiter.
Der Debugger zeigt lokale Variablen, Systemwerte und den Aufrufstapel des ausgewählten Roboters.
Werte lassen sich dort nicht verändern. Ein Beispiel liegt in `examples/Debugger-WAIT.xrl`.

Haltepunkte werden als Zeilennummern mit dem Projekt gespeichert. Nach Textänderungen müssen sie geprüft
werden; sie verschieben sich noch nicht automatisch mit eingefügten Zeilen. Während eines laufenden
oder pausierten Programms ist der Programmtext schreibgeschützt. Für Änderungen zuerst stoppen.

## Pause, Start und große Zellen

Die globale Pause friert Förderer, Teile, Zellenzeit und alle laufenden Roboter ein. Fortsetzen erhält
die Bedingung von WAIT FOR und die Restzeit von WAIT SEC/PULSE. Ein zusätzlicher Start während eines
laufenden Programms startet es nicht erneut. Ein einzelner Roboter kann über OPC UA separat pausiert
werden; dann läuft die restliche Zelle weiter. Der Einzelschritt bezieht sich auf den ausgewählten Roboter.

Das Cockpit zeigt CPU-Schrittdauer, Anzahl der Teilschritte und noch offenen Zeitrückstand. Hoher Zeitraffer
erreicht auf langsamer Hardware möglicherweise nicht die eingestellte Geschwindigkeit. Offene Schritte
bleiben im Rückstand; Pause und Reset verwerfen diesen Rückstand ausdrücklich. Das Zeitbudget kann einen
einzelnen teuren Physikschritt nicht unterbrechen. Das Profil „Große Zellen“ zeichnet seltener (30 statt
60 Timeraufrufe/s); dies ist keine zugesicherte Bildrate und ändert die gewünschte Simulationsgeschwindigkeit nicht.

## OPC-UA-Verbindungen prüfen

Server und feste NodeIds aus 1.4 bleiben erhalten; siehe `OPC-UA-ANBINDUNG.md`. Externe Clients kannst du
unter **Konnektivität → OPC-UA-Clients** anlegen. Verbinden und Durchsuchen laufen im Hintergrund.
Passwörter gelten nur für die aktuelle Sitzung und werden weiterhin nicht in Projekten gespeichert.

Standardmäßig verbindet sich der Client nach einem Abbruch erneut (Wartezeit 0,25 bis höchstens 30 s).
Danach sind Schreibzugriffe gesperrt. Prüfe im Dialog **Live-Diagnose** Server, Zuordnung und letzte Werte;
klicke dann bewusst **Schreiben freigeben**. Lesen läuft weiter. Während der Verbindungstrennung gelten
letzte Werte als veraltet. Eine fehlerhafte Schreibzuordnung sperrt weitere Schreibzugriffe ebenfalls.
Für eine neu angelegte Verbindung gelten die ausdrücklich konfigurierten Schreibzuordnungen beim ersten
Verbinden. Nach manuellem Trennen muss Schreiben wieder freigegeben werden.

Zusätzliche Schreibziele (Simulation → Server): `JOINTS:<Roboter>` und `POSE:<Roboter>:BASE|WORLD` liefern
sechs Zahlen. Der Serverknoten muss ein passendes schreibbares Array sein. Achs-/TCP-Ziele benötigen einen
vorhandenen Roboternamen. `nsu=urn:ximaj:robosim;s=XimajRoboSim/IO/Out/O9` wird über den Namespace-URI
aufgelöst; alternativ bleiben `ns=...;s=...`-Adressen möglich. Signalnummern sind 1 bis 4096.

Wiederverbinden wiederholt keine Roboterprogramme oder Befehle. Die Kopplung überträgt Variablen;
nach Schreibfreigabe wird der aktuelle Zustand übertragen. Es ist keine transaktionale SPS-Steuerung.
Der vorhandene Server verwendet NoSecurity; verschlüsselte/authentifizierte industrielle Anbindung wurde
mit diesem Upgrade nicht ergänzt. Die Loopback-Tests benötigen keine echten Maschinen.

## Sicher speichern und schneller bedienen

Ein manueller Speichervorgang schreibt zuerst eine vollständige temporäre Datei. Erst danach ersetzt er
die Projektdatei; die vorherige Version steht als `zelle.xrsim.bak` daneben. Kopiere diese bei Bedarf
unter einen neuen `.xrsim`-Namen. Autosave und Undo bleiben erhalten. Defekte Dateien werden beim Öffnen
gemeldet, bevor sie die aktuelle Zelle ersetzen. Ungesicherte Änderungen werden weiterhin abgefragt.

**Strg+K** öffnet eine Befehlspalette. Suche, wähle einen konkreten Befehl und bestätige ihn mit Eingabe.
Die Suche allein führt nichts aus. Der Szenenfilter blendet Objekte aus der Liste aus, ohne deren
Indices zu verändern. Unter 1100 Pixeln Breite wählst du Menübandbereiche über eine Auswahlliste.
Werkzeugseiten und breite Tabellen lassen sich unabhängig scrollen.

## Grenzen und Prüfung

Das eigene Robotermodell und die Kontakt-/Schwerkraftmodelle bleiben Näherungen. CAD, Herstellerprogramme,
Sicherheitsabstände und VC-Komponentenskripte müssen am konkreten Projekt bewertet werden. VC-Skripte sind
keine Sandbox und dürfen nur aus vertrauenswürdigen Dateien aktiviert werden. Unbekannte Anweisungen
werden weiterhin als Importhinweise angezeigt. Bei älteren Teach-Punkten wird kein Weltbezug erfunden.

Die Prüfung dieses Builds steht im ausgelieferten Prüfbericht. Offscreen-Layoutbilder verwenden einen
gekennzeichneten 3D-Platzhalter; daraus folgt keine Prüfung der GPU-Darstellung oder deiner kompletten
Farbsortierzelle. Source und Windows-Installer werden getrennt geliefert.
