# Updates über GitHub – was hochgeladen werden muss

> **Kurzweg ab 1.1.0:** `build.ps1` baut EXE, Setup, ZIP und Prüfsummen, und `publish.ps1` lädt alles
> als GitHub-Release hoch (einmalig vorher `gh auth login`). Pro Release gehören vier Dateien dazu:
> `XimajRoboSim-Setup-x.y.z.exe` und `.exe.sha256` für installierte Versionen (Update über das Setup)
> sowie `XimajRoboSim-x.y.z.zip` und `.zip.sha256` für portable Versionen und 1.0.0.

Die App fragt beim Start (und über *Hilfe → Nach Updates suchen*) diese Adresse ab:

```
https://api.github.com/repos/NBFinn/XimajRoboSim/releases/latest
```

Sie vergleicht den **Tag** des neuesten Releases (z. B. `v1.0.1`) mit ihrer eigenen Version aus
`ximaj_robosim/version.py`. Ist der Tag höher, bietet sie das Update an.

## Voraussetzung (einmalig)

- Das Repository **NBFinn/XimajRoboSim muss öffentlich sein**. Bei einem privaten Repo antwortet
  GitHub ohne Anmeldung mit „404“, und die App meldet „Noch kein Release gefunden“.
  Den Quellcode kannst du privat halten, wenn du für die Releases ein eigenes öffentliches Repo
  nutzt. Dann `UPDATE_REPO` in `ximaj_robosim/version.py` entsprechend ändern.

## Erstes Release (Version 1.0.0) – jetzt hochladen

1. GitHub → Repo **NBFinn/XimajRoboSim** → **Releases** → **Draft a new release**
2. **Tag:** `v1.0.0` (neu anlegen) · **Titel:** `Ximaj RoboSim 1.0.0`
3. **Beschreibung:** Änderungsnotizen. Die App zeigt diesen Text im Update-Dialog an.
4. **Assets** per Drag & Drop aus `release\v1.0.0\` anhängen, und zwar **genau diese zwei Dateien**:
   - `XimajRoboSim-1.0.0.zip`
   - `XimajRoboSim-1.0.0.zip.sha256`
5. **Publish release** (nicht „Pre-release“, sonst zählt es nicht als „latest“).

`latest.json` im selben Ordner ist nur eine Info für dich und muss nicht hochgeladen werden.

## Jedes weitere Update (z. B. 1.0.1)

1. In `ximaj_robosim/version.py` die Version erhöhen: `VERSION = "1.0.1"`
2. Bauen:
   ```
   powershell -ExecutionPolicy Bypass -File build.ps1
   ```
3. Neues GitHub-Release mit Tag **`v1.0.1`** anlegen und die zwei Dateien aus `release\v1.0.1\`
   anhängen (`.zip` und `.zip.sha256`), dann veröffentlichen.

Fertig: Alle installierten Versionen erkennen beim nächsten Start „Update 1.0.1 verfügbar“.

## Was die App beim Update macht

1. Sie lädt das ZIP und die `.sha256` (nur über HTTPS).
2. Sie prüft die SHA-256-Prüfsumme. Stimmt sie nicht, wird das Update verworfen.
3. Sie fragt den Benutzer: „Jetzt neu starten und installieren?“
4. Sie sichert die alte Version nach `_backup\<alte Version>\` und spielt die neue ein.
   Projekte und Einstellungen (in `%APPDATA%\XimajRoboSim`) bleiben unberührt.
5. Zurück zur alten Version: *Hilfe → Auf vorherige Version zurücksetzen*.

## Wichtige Regeln

- Die Tags müssen dem Schema `vX.Y.Z` folgen und immer steigen.
- Das ZIP muss den kompletten Inhalt von `dist\XimajRoboSim\` enthalten (macht `build.ps1` automatisch).
- Lade immer **beide** Dateien hoch. Ohne `.sha256` lehnt die App das Update aus Sicherheitsgründen ab.
