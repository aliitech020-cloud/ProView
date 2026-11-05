; Inno Setup script - builds ProVixel-Setup.exe from the PyInstaller output in dist\ProVixel
#ifndef AppVersion
  #define AppVersion "1.2.0"
#endif

[Setup]
AppId={{7E3F2A51-6B1C-4D8E-9A2F-3C5B7D9E1F20}
AppName=ProVixel
AppVersion={#AppVersion}
AppVerName=ProVixel {#AppVersion}
AppPublisher=ProVixel
DefaultDirName={autopf}\ProVixel
DefaultGroupName=ProVixel
DisableProgramGroupPage=yes
OutputDir=installer_out
OutputBaseFilename=ProVixel-Setup-{#AppVersion}
SetupIconFile=assets\provixel.ico
UninstallDisplayIcon={app}\ProVixel.exe
UninstallDisplayName=ProVixel
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
Name: "assocstl"; Description: "Add ProVixel to ""Open with"" for .stl files"; GroupDescription: "File types:"
Name: "assocply"; Description: "Add ProVixel to ""Open with"" for .ply files"; GroupDescription: "File types:"

[Files]
Source: "dist\ProVixel\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\ProVixel"; Filename: "{app}\ProVixel.exe"
Name: "{group}\Uninstall ProVixel"; Filename: "{uninstallexe}"
Name: "{autodesktop}\ProVixel"; Filename: "{app}\ProVixel.exe"; Tasks: desktopicon

[Registry]
Root: HKA; Subkey: "Software\Classes\ProVixel.Mesh"; ValueType: string; ValueName: ""; ValueData: "3D model"; Flags: uninsdeletekey; Tasks: assocstl assocply
Root: HKA; Subkey: "Software\Classes\ProVixel.Mesh\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\ProVixel.exe,0"; Tasks: assocstl assocply
Root: HKA; Subkey: "Software\Classes\ProVixel.Mesh\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\ProVixel.exe"" ""%1"""; Tasks: assocstl assocply
Root: HKA; Subkey: "Software\Classes\.stl\OpenWithProgids"; ValueType: string; ValueName: "ProVixel.Mesh"; ValueData: ""; Flags: uninsdeletevalue; Tasks: assocstl
Root: HKA; Subkey: "Software\Classes\.ply\OpenWithProgids"; ValueType: string; ValueName: "ProVixel.Mesh"; ValueData: ""; Flags: uninsdeletevalue; Tasks: assocply

[Run]
Filename: "{app}\ProVixel.exe"; Description: "{cm:LaunchProgram,ProVixel}"; Flags: nowait postinstall skipifsilent
