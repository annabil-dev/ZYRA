[Setup]
AppName=ZYRA AI
AppVersion=1.0.55
AppPublisher=ZYRATechnology
DefaultDirName={autopf}\ZYRA AI
DefaultGroupName=ZYRA AI
OutputBaseFilename=ZYRA_AI_Setup_v1.0.64
Compression=lzma2/ultra64
SolidCompression=yes
SetupIconFile=app\ui\icon.ico
UninstallDisplayIcon={app}\ZYRA AI.exe
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64
OutputDir=dist
CloseApplications=force

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional icons:"

[Files]
Source: "dist\ZYRA AI\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\ZYRA AI"; Filename: "{app}\ZYRA AI.exe"
Name: "{autodesktop}\ZYRA AI"; Filename: "{app}\ZYRA AI.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\ZYRA AI.exe"; Description: "Launch ZYRA AI"; Flags: nowait postinstall skipifsilent
