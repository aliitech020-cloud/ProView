; Inno Setup script - builds ProView-Setup.exe from the PyInstaller output in dist\ProView
#ifndef AppVersion
  #define AppVersion "1.1.0"
#endif

[Setup]
AppId={{7E3F2A51-6B1C-4D8E-9A2F-3C5B7D9E1F20}
AppName=ProView
AppVersion={#AppVersion}
AppVerName=ProView {#AppVersion}
AppPublisher=ProView
DefaultDirName={autopf}\ProView
DefaultGroupName=ProView
DisableProgramGroupPage=yes
OutputDir=installer_out
OutputBaseFilename=ProView-Setup-{#AppVersion}
SetupIconFile=assets\proview.ico
UninstallDisplayIcon={app}\ProView.exe
UninstallDisplayName=ProView
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ChangesAssociations=yes

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "assocstl"; Description: "Add ProView to ""Open with"" for .stl files"; GroupDescription: "File types:"
Name: "assocply"; Description: "Add ProView to ""Open with"" for .ply files"; GroupDescription: "File types:"

[Files]
Source: "dist\ProView\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\ProView"; Filename: "{app}\ProView.exe"
Name: "{group}\Uninstall ProView"; Filename: "{uninstallexe}"
Name: "{autodesktop}\ProView"; Filename: "{app}\ProView.exe"; Tasks: desktopicon

[Registry]
Root: HKA; Subkey: "Software\Classes\ProView.Mesh"; ValueType: string; ValueName: ""; ValueData: "3D model"; Flags: uninsdeletekey; Tasks: assocstl assocply
Root: HKA; Subkey: "Software\Classes\ProView.Mesh\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\ProView.exe,0"; Tasks: assocstl assocply
Root: HKA; Subkey: "Software\Classes\ProView.Mesh\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\ProView.exe"" ""%1"""; Tasks: assocstl assocply
Root: HKA; Subkey: "Software\Classes\.stl\OpenWithProgids"; ValueType: string; ValueName: "ProView.Mesh"; ValueData: ""; Flags: uninsdeletevalue; Tasks: assocstl
Root: HKA; Subkey: "Software\Classes\.ply\OpenWithProgids"; ValueType: string; ValueName: "ProView.Mesh"; ValueData: ""; Flags: uninsdeletevalue; Tasks: assocply

[Run]
Filename: "{app}\ProView.exe"; Description: "{cm:LaunchProgram,ProView}"; Flags: nowait postinstall skipifsilent
