# Ximaj RoboSim - EXE bauen und GitHub-Release-Paket erzeugen
# Aufruf:  powershell -ExecutionPolicy Bypass -File build.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$version = (python tools\version_info.py).Trim()
Write-Host "== Baue Ximaj RoboSim $version =="
python tools\make_icon.py | Out-Null

python -m PyInstaller --noconfirm --clean --windowed `
  --name XimajRoboSim `
  --icon ximaj_robosim\assets\ximaj_robosim.ico `
  --version-file build\version_info.txt `
  --add-data "ximaj_robosim\assets;assets" `
  --paths ximaj_robosim `
  --collect-submodules asyncua `
  --collect-data asyncua `
  --collect-submodules OpenGL `
  --hidden-import trimesh `
  --collect-data trimesh `
  --collect-all cascadio `
  --collect-all imageio_ffmpeg `
  --collect-submodules ezdxf `
  --collect-data ezdxf `
  --hidden-import fast_simplification `
  --distpath dist --workpath build\pyi `
  ximaj_robosim\main.py
if ($LASTEXITCODE -ne 0) { throw "PyInstaller fehlgeschlagen" }

# Release-Paket fuer GitHub: ZIP + SHA256 + latest.json
$rel = "release\v$version"
New-Item -ItemType Directory -Force $rel | Out-Null
$zip = "$rel\XimajRoboSim-$version.zip"
if (Test-Path $zip) { Remove-Item $zip }
Compress-Archive -Path "dist\XimajRoboSim\*" -DestinationPath $zip
$hash = (Get-FileHash $zip -Algorithm SHA256).Hash.ToLower()
"$hash  XimajRoboSim-$version.zip" | Set-Content "$zip.sha256" -Encoding ascii -NoNewline
# Setup (Inno Setup 6)
$iscc = @("$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe", "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
          "$env:ProgramFiles\Inno Setup 6\ISCC.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
$setupHash = $null
if ($iscc) {
  & $iscc /Q "/DAppVer=$version" installer.iss
  if ($LASTEXITCODE -ne 0) { throw "Inno Setup fehlgeschlagen" }
  $setup = "$rel\XimajRoboSim-Setup-$version.exe"
  $setupHash = (Get-FileHash $setup -Algorithm SHA256).Hash.ToLower()
  "$setupHash  XimajRoboSim-Setup-$version.exe" | Set-Content "$setup.sha256" -Encoding ascii -NoNewline
} else {
  Write-Host "Inno Setup nicht gefunden - Setup wird uebersprungen"
}
@{ version = $version; zip = "XimajRoboSim-$version.zip"; sha256 = $hash; setup = "XimajRoboSim-Setup-$version.exe"; setup_sha256 = $setupHash } |
  ConvertTo-Json | Set-Content "$rel\latest.json" -Encoding utf8

Write-Host ""
Write-Host "Fertig:"
Write-Host "  EXE:      dist\XimajRoboSim\XimajRoboSim.exe"
Write-Host "  Release:  $rel  (Setup + ZIP jeweils mit .sha256 als Release-Assets, Tag v$version)"
