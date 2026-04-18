#ifndef ProductName
  #define ProductName "Aoryn Browser"
#endif
#ifndef AppVersion
  #define AppVersion "0.1.0"
#endif
#ifndef AppPublisher
  #define AppPublisher "Aoryn"
#endif
#ifndef AppExeName
  #define AppExeName "AorynBrowser.exe"
#endif
#ifndef ReleaseSourceDir
  #define ReleaseSourceDir "..\\dist"
#endif
#ifndef ReleaseOutputDir
  #define ReleaseOutputDir "..\\release"
#endif
#ifndef OutputBaseName
  #define OutputBaseName "AorynBrowser-Setup-0.1.0"
#endif
#ifndef InstallDirName
  #define InstallDirName "Aoryn Browser"
#endif
#ifndef AppId
  #define AppId "{{6B0C3A40-A6D2-4C54-9E3D-6F16AB95D4F0}"
#endif

[Setup]
AppId={#AppId}
AppName={#ProductName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL=https://aoryn.org
DefaultDirName={localappdata}\Programs\{#InstallDirName}
DefaultGroupName={#ProductName}
DisableProgramGroupPage=yes
DisableDirPage=no
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
UsePreviousAppDir=yes
UsePreviousTasks=yes
WizardStyle=modern
Compression=lzma
SolidCompression=yes
SetupIconFile=..\desktop_agent\dashboard_assets\icons\aoryn-app.ico
UninstallDisplayIcon={app}\{#AppExeName}
OutputDir={#ReleaseOutputDir}
OutputBaseFilename={#OutputBaseName}
VersionInfoProductName={#ProductName}
VersionInfoProductVersion={#AppVersion}
VersionInfoDescription={#ProductName}
VersionInfoCompany={#AppPublisher}
VersionInfoCopyright={#AppPublisher}
CloseApplications=yes
CloseApplicationsFilter={#AppExeName}
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"

[Files]
Source: "{#ReleaseSourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Registry]
Root: HKCU; Subkey: "Software\Aoryn\BrowserInstaller"; ValueType: string; ValueName: "InstallDir"; ValueData: "{app}"; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Aoryn\BrowserInstaller"; ValueType: string; ValueName: "DisplayVersion"; ValueData: "{#AppVersion}"; Flags: uninsdeletevalue uninsdeletekeyifempty

[Icons]
Name: "{autoprograms}\{#ProductName}"; Filename: "{app}\{#AppExeName}"
Name: "{autodesktop}\{#ProductName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Launch {#ProductName}"; Flags: nowait postinstall skipifsilent
