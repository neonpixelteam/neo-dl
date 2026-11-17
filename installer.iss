; Inno Setup 6 script — build the installer with: ISCC installer.iss
; Output: Output\NEO-DL-Setup.exe
[Setup]
AppName=NEO-DL
AppVersion=1.0.0
AppPublisher=NEO
DefaultDirName={autopf}\NEO-DL
DefaultGroupName=NEO-DL
OutputDir=Output
OutputBaseFilename=NEO-DL-Setup
Compression=lzma2
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
UninstallDisplayIcon={app}\NEO-DL.exe
WizardStyle=modern

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: unchecked

[Files]
Source: "dist\NEO-DL.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\NEO-DL"; Filename: "{app}\NEO-DL.exe"
Name: "{group}\Uninstall NEO-DL"; Filename: "{uninstallexe}"
Name: "{autodesktop}\NEO-DL"; Filename: "{app}\NEO-DL.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\NEO-DL.exe"; Description: "Launch NEO-DL"; Flags: nowait postinstall skipifsilent
