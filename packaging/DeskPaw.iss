#define AppName "DeskPaw"
#define AppVersion GetVersionNumbersString(AddBackslash(SourcePath) + "..\dist\DeskPaw.exe")

[Setup]
AppId=GreenHuo.DeskPaw
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=GreenHuo
DefaultDirName={autopf}\DeskPaw
DefaultGroupName=DeskPaw
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist
OutputBaseFilename=DeskPaw-Setup-x64
SetupIconFile=..\deskpaw\assets\deskpaw.ico
UninstallDisplayIcon={app}\DeskPaw.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加任务："; Flags: unchecked

[Files]
Source: "..\dist\DeskPaw.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\DeskPaw"; Filename: "{app}\DeskPaw.exe"; WorkingDir: "{app}"
Name: "{autodesktop}\DeskPaw"; Filename: "{app}\DeskPaw.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\DeskPaw.exe"; Description: "运行 DeskPaw"; Flags: nowait postinstall skipifsilent
