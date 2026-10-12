# Ximaj RoboSim - Release auf GitHub veroeffentlichen (vorher: build.ps1, gh auth login)
# Aufruf:  powershell -ExecutionPolicy Bypass -File publish.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$gh = "C:\Program Files\GitHub CLI\gh.exe"
$repo = "NBFinn/XimajRoboSim"
$version = (python -c "import sys; sys.path.insert(0,'ximaj_robosim'); from version import VERSION; print(VERSION)").Trim()
$rel = "release\v$version"
$files = @("$rel\XimajRoboSim-Setup-$version.exe", "$rel\XimajRoboSim-Setup-$version.exe.sha256",
           "$rel\XimajRoboSim-$version.zip", "$rel\XimajRoboSim-$version.zip.sha256")
foreach ($f in $files) { if (-not (Test-Path $f)) { throw "Fehlt: $f  (zuerst build.ps1 ausfuehren)" } }

& $gh auth status | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Nicht bei GitHub angemeldet: gh auth login" }

$info = & $gh repo view $repo --json isEmpty,visibility | ConvertFrom-Json
if ($info.isEmpty) { throw "Repository $repo ist leer - GitHub erlaubt Releases erst nach dem ersten Commit." }
if ($info.visibility -ne "PUBLIC") { Write-Warning "Repository ist $($info.visibility): Die App benoetigt fuer private Releases eine GitHub-CLI-Anmeldung oder einen Zugang unter Update / Info." }

# Versionshinweise aus CHANGELOG.md (Abschnitt dieser Version)
$log = Get-Content CHANGELOG.md -Raw
$m = [regex]::Match($log, "(?s)## $([regex]::Escape($version))\s*(.*?)(?=\r?\n## |\z)")
$notes = if ($m.Success) { $m.Groups[1].Value.Trim() } else { "Ximaj RoboSim $version" }
$nf = "$rel\notes.md"
$notes | Set-Content $nf -Encoding utf8

# Pruefen, ob das Release schon existiert (Fehlermeldung "release not found" ist hier normal)
$ErrorActionPreference = "Continue"
$null = cmd /c "`"$gh`" release view v$version -R $repo >nul 2>nul"
$exists = ($LASTEXITCODE -eq 0)
$ErrorActionPreference = "Stop"
if ($exists) {
  & $gh release upload "v$version" @files -R $repo --clobber
} else {
  & $gh release create "v$version" @files -R $repo --title "Ximaj RoboSim $version" --notes-file $nf --latest
}
if ($LASTEXITCODE -ne 0) { throw "Upload fehlgeschlagen" }
Write-Host "Veroeffentlicht: https://github.com/$repo/releases/tag/v$version"
