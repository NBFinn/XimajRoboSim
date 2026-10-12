; Ximaj RoboSim - Installer (Inno Setup 6). Wird von build.ps1 mit /DAppVer=x.y.z aufgerufen.
#ifndef AppVer
  #define AppVer "0.0.0"
#endif

[Setup]
AppId={{6E0B7C1A-58A4-4F7B-9C2E-5A1D3F9B7E21}
AppName=Ximaj RoboSim
AppVersion={#AppVer}
AppVerName=Ximaj RoboSim {#AppVer}
AppPublisher=Ximaj IT-Solutions
AppPublisherURL=https://ximaj.com
AppSupportURL=https://github.com/NBFinn/XimajRoboSim/releases
VersionInfoCompany=Ximaj IT-Solutions
VersionInfoDescription=Ximaj RoboSim Setup
VersionInfoVersion={#AppVer}
DefaultDirName={localappdata}\Programs\Ximaj RoboSim
DefaultGroupName=Ximaj RoboSim
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=release\v{#AppVer}
OutputBaseFilename=XimajRoboSim-Setup-{#AppVer}
SetupIconFile=ximaj_robosim\assets\ximaj_robosim.ico
WizardImageFile=ximaj_robosim\assets\wizard_large_1x.bmp,ximaj_robosim\assets\wizard_large_2x.bmp
WizardSmallImageFile=ximaj_robosim\assets\wizard_small_1x.bmp,ximaj_robosim\assets\wizard_small_2x.bmp
WizardImageStretch=no
UninstallDisplayIcon={app}\XimajRoboSim.exe
UninstallDisplayName=Ximaj RoboSim
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
CloseApplications=force
RestartApplications=no
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
ChangesAssociations=yes

[Languages]
Name: "german"; MessagesFile: "compiler:Languages\German.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "assoc"; Description: "Ximaj-Projekte (.xrsim) mit Ximaj RoboSim öffnen"; GroupDescription: "Dateizuordnung"

[InstallDelete]
; alte Bibliotheken entfernen, damit keine Reste einer Vorversion bleiben
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "dist\XimajRoboSim\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Ximaj RoboSim"; Filename: "{app}\XimajRoboSim.exe"
Name: "{autodesktop}\Ximaj RoboSim"; Filename: "{app}\XimajRoboSim.exe"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Classes\.xrsim"; ValueType: string; ValueName: ""; ValueData: "XimajRoboSim.Projekt"; Flags: uninsdeletevalue; Tasks: assoc
Root: HKCU; Subkey: "Software\Classes\XimajRoboSim.Projekt"; ValueType: string; ValueName: ""; ValueData: "Ximaj RoboSim Projekt"; Flags: uninsdeletekey; Tasks: assoc
Root: HKCU; Subkey: "Software\Classes\XimajRoboSim.Projekt\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\XimajRoboSim.exe,0"; Tasks: assoc
Root: HKCU; Subkey: "Software\Classes\XimajRoboSim.Projekt\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\XimajRoboSim.exe"" ""%1"""; Tasks: assoc

[Run]
; normale Installation: Haken "starten" am Ende
Filename: "{app}\XimajRoboSim.exe"; Description: "{cm:LaunchProgram,Ximaj RoboSim}"; Flags: nowait postinstall skipifsilent
; stilles Update aus der App: danach automatisch neu starten
Filename: "{app}\XimajRoboSim.exe"; Flags: nowait; Check: WizardSilent
