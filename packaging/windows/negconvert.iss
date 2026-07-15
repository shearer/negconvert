; Inno Setup script for NegConvert. Run after PyInstaller has produced
; dist\NegConvert\ (onedir build) at the repo root - see
; .github/workflows/build.yml. Pass the version with /DAppVersion=x.y.z;
; defaults to 0.0.0-dev for local/manual runs.
#ifndef AppVersion
  #define AppVersion "0.0.0-dev"
#endif

[Setup]
AppId={{6F2B6B7E-6C7B-4B7E-9C7A-0E0F1B6E1B41}
AppName=NegConvert
AppVersion={#AppVersion}
AppPublisher=NegConvert
DefaultDirName={autopf}\NegConvert
DefaultGroupName=NegConvert
UninstallDisplayIcon={app}\NegConvert.exe
OutputDir=..\..\dist-installers
OutputBaseFilename=NegConvert-{#AppVersion}-windows
Compression=lzma2
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern
DisableProgramGroupPage=yes

[Files]
Source: "..\..\dist\NegConvert\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs

[Icons]
Name: "{group}\NegConvert"; Filename: "{app}\NegConvert.exe"
Name: "{autodesktop}\NegConvert"; Filename: "{app}\NegConvert.exe"; Tasks: desktopicon

[Tasks]
Name: desktopicon; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"

[Run]
Filename: "{app}\NegConvert.exe"; Description: "Launch NegConvert"; Flags: nowait postinstall skipifsilent
