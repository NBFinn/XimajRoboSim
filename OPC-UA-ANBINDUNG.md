# RoboSim 1.4.0: Roboterpunkte über OPC UA einlesen

RoboSim stellt einen echten OPC-UA-Server bereit. Dein eigener OPC-UA-Server benötigt einen **Client/Adapter**, der diese Werte liest oder abonniert und bei Bedarf im eigenen Adressraum veröffentlicht. Zwei Server verbinden sich nicht allein durch das Eintragen ihrer Adressen.

1. RoboSim starten und dein `.xrsim`-Projekt öffnen.
2. Unter **Konnektivität** den RoboSim-OPC-UA-Server starten.
3. Den tatsächlich angezeigten Endpunkt kopieren, z. B. `opc.tcp://localhost:4841/ximaj/robosim`. Port 4840 kann durch deinen anderen Server belegt sein; der Ausweichport wird angezeigt.
4. **Roboterpunkte / OPC-UA-Knoten** öffnen. Nach Robotername, `Points`, `Axes` oder `TcpWorld` filtern, NodeId kopieren oder alle Knoten exportieren.
5. In deinem Server-Adapter diesen Endpunkt und die benötigten NodeIds zum Lesen/Abonnieren eintragen.

Namespace-URI: `urn:ximaj:robosim`. Bei der aktuellen Serverkonfiguration ist der Namespace-Index üblicherweise 2. **Lies die NamespaceArray des verbundenen Servers und löse die URI auf**, statt die Nummer grundsätzlich fest einzubauen. Der Export enthält die tatsächlich gültige NodeId und zusätzlich URI und Identifier.

| Beispiel-Identifier (String-Teil der NodeId) | Wert / Bedeutung |
|---|---|
| `XimajRoboSim/Robots/Roboter%201/Axes/A1` | Achse A1 in Grad |
| `XimajRoboSim/Robots/Roboter%201/Axes/JointPosition` | Double-Array A1–A6 in Grad |
| `XimajRoboSim/Robots/Roboter%201/Tcp/Pose` | Double-Array X,Y,Z,A,B,C in aktueller BASE |
| `XimajRoboSim/Robots/Roboter%201/TcpWorld/Pose` | Double-Array X,Y,Z,A,B,C im Weltkoordinatensystem |
| `XimajRoboSim/Robots/Roboter%201/BaseWorld` | Aktuelle BASE relativ zur Welt |
| `XimajRoboSim/Robots/Roboter%201/Points/P1/X` | Eingelernter X-Wert in mm |
| `XimajRoboSim/Robots/Roboter%201/Points/P1/Pose` | Eingelernte Pose X,Y,Z,A,B,C |
| `XimajRoboSim/Robots/Roboter%201/Points/P1/WorldPose` | Pose zur Welt beim Einlernen, nur bei `WorldKnown=true` verwenden |
| `XimajRoboSim/Robots/Roboter%201/Points/P1/Valid` | Ob die sechs eingelernten Koordinaten gültig sind |
| `XimajRoboSim/Robots/Roboter%201/Points/P1/E1` | Linearachse beim Einlernen, nur bei `E1Known=true` verwenden |
| `XimajRoboSim/Robot/TcpWorld/X` | Welt-X des aktuell ausgewählten Roboters |
| `XimajRoboSim/Robots/Roboter%201/Gripper/Command` | Tatsächlicher Greifbefehl auf dem konfigurierten Roboterausgang |
| `XimajRoboSim/Robots/Roboter%201/Gripper/Holding` | Ob ein Werkstück gehalten wird |
| `XimajRoboSim/Robots/Roboter%201/Gripper/MappingConflict` | Weitere Komponenten, die denselben Ausgang verwenden |

Eine vollständige Adresse lautet beispielsweise `ns=2;s=XimajRoboSim/Robots/Roboter%201/Axes/A1`. Roboternamen stammen aus deinem Projekt. Leerzeichen, `/` und `%` in Namen werden im Identifier pro Pfadsegment kodiert. Browse-Namen bleiben lesbar. Bei Umbenennung entsteht eine neue Adresse. Gleichnamige Teach-Punkte ab dem zweiten erhalten `/Duplicate/2`, `/Duplicate/3` usw.; bei solchen Duplikaten ist die Reihenfolge maßgeblich. Eindeutige Punktnamen sind daher empfehlenswert.

X/Y/Z und E1 sind Millimeter, A/B/C sind Grad: A um Z, B um Y, C um X (ZYX). Aktuelle TCP-Werte werden aus der Kinematik berechnet, auch wenn die Simulation angehalten ist. `Pose` und `JointPosition` liefern jeweils zusammengehörige Werte in einem einzelnen Array. Mehrere separate Knoten bilden keine gemeinsame atomare Momentaufnahme. Achsen und Roboterpunkte sind schreibgeschützt; die bisherigen E/A, Override, Bandgeschwindigkeit und Methoden bleiben verfügbar.

Ältere Teach-/Importpunkte enthalten nur eine Pose in BASE, ohne den damaligen Weltbezug. `WorldKnown=false` und NaN in `WorldPose` machen das ausdrücklich sichtbar. In JSON-/CSV-Exporten werden solche unbekannten Zahlen als `null` ausgegeben. Neue Teach-Punkte erfassen den Weltbezug beim Einlernen. Alte Punkte kannst du bei bewusst gewählter BASE neu einlernen.

NodeIds bleiben bei Neustart mit gleichen Namen gleich, unabhängig von der Reihenfolge, in der andere Komponenten hinzukommen. Frühere numerische NodeIds aus Version 1.3.x werden durch String-NodeIds ersetzt: vorhandene Zuordnungen anhand der Browse-Pfade neu auswählen.

Der Server verwendet weiterhin unverschlüsseltes OPC UA ohne Anmeldung. Für lokale Simulation **Nur auf diesem PC erreichbar** aktivieren. Eine Verbindung zu einem fremden/produktiven Server, Zertifikatssicherheit oder eine echte Robotersteuerung ist damit nicht automatisch eingerichtet.

## Kleiner Lesetest aus Python

`pip install asyncua`, dann `python examples/read_robot_points.py --endpoint <angezeigte-URL> --robot "Roboter 1"`.
Das Beispiel löst den Namespace über die URI auf und liest nur. Es schaltet keine Ausgänge und startet keine Roboter.
