#ifndef AppName
  #define AppName "Aoryn"
#endif
#ifndef AppVersion
  #define AppVersion "0.1.0"
#endif
#ifndef AppPublisher
  #define AppPublisher "Aoryn"
#endif
#ifndef AppExeName
  #define AppExeName "Aoryn.exe"
#endif
#ifndef ReleaseSourceDir
  #define ReleaseSourceDir "..\\dist\\Aoryn"
#endif
#ifndef ReleaseOutputDir
  #define ReleaseOutputDir "..\\release"
#endif
#ifndef AppId
  #define AppId "{{D5D2105A-6DA8-4A9A-A0B2-9A1E4A6B5B8F}"
#endif

[Setup]
AppId={#AppId}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL=https://aoryn.local
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
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
OutputBaseFilename={#AppName}-Setup-{#AppVersion}
VersionInfoProductName={#AppName}
VersionInfoProductVersion={#AppVersion}
VersionInfoDescription={#AppName} Desktop App
VersionInfoCompany={#AppPublisher}
VersionInfoCopyright={#AppPublisher}
CloseApplications=yes
CloseApplicationsFilter={#AppExeName}
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
Source: "{#ReleaseSourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Registry]
Root: HKCU; Subkey: "Software\Aoryn\DesktopInstaller"; ValueType: string; ValueName: "InstallDir"; ValueData: "{app}"; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Aoryn\DesktopInstaller"; ValueType: string; ValueName: "DisplayVersion"; ValueData: "{#AppVersion}"; Flags: uninsdeletevalue uninsdeletekeyifempty

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{userappdata}\Aoryn"; Check: ShouldRemoveUserData
Type: filesandordirs; Name: "{localappdata}\Aoryn"; Check: ShouldRemoveUserData

[Code]
var
  DirDataNoticeLabel: TNewStaticText;
  RemoveUserDataOnUninstall: Boolean;
  UninstallPromptShown: Boolean;
  ExistingInstallDetected: Boolean;
  ExistingInstallVersion: string;
  ExistingInstallDir: string;
  ExistingInstallComparison: Integer;

function NormalizeDirName(const DirName: string): string;
begin
  Result := Lowercase(RemoveBackslashUnlessRoot(ExpandConstant(DirName)));
end;

function InstalledVersionLabel(): string;
begin
  if ExistingInstallVersion <> '' then
    Result := ExistingInstallVersion
  else
    Result := 'an earlier build';
end;

function InstallerMetadataRegistryKey(): string;
begin
  Result := 'Software\Aoryn\DesktopInstaller';
end;

function UninstallRegistryKey(): string;
begin
  Result := 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{#AppId}_is1';
end;

function DefaultInstallDir(): string;
begin
  Result := ExpandConstant('{localappdata}\Programs\{#AppName}');
end;

function DefaultInstallExePath(): string;
begin
  Result := AddBackslash(DefaultInstallDir()) + '{#AppExeName}';
end;

function ShiftVersionPart(var VersionText: string): Integer;
var
  DotPos: Integer;
  Token: string;
begin
  DotPos := Pos('.', VersionText);
  if DotPos > 0 then
  begin
    Token := Copy(VersionText, 1, DotPos - 1);
    Delete(VersionText, 1, DotPos);
  end
  else
  begin
    Token := VersionText;
    VersionText := '';
  end;

  Result := StrToIntDef(Token, 0);
end;

function CompareVersionText(const LeftVersion: string; const RightVersion: string): Integer;
var
  LeftRemaining: string;
  RightRemaining: string;
  LeftPart: Integer;
  RightPart: Integer;
  Index: Integer;
begin
  LeftRemaining := LeftVersion;
  RightRemaining := RightVersion;

  for Index := 0 to 7 do
  begin
    LeftPart := ShiftVersionPart(LeftRemaining);
    RightPart := ShiftVersionPart(RightRemaining);

    if LeftPart < RightPart then
    begin
      Result := -1;
      exit;
    end;

    if LeftPart > RightPart then
    begin
      Result := 1;
      exit;
    end;

    if (LeftRemaining = '') and (RightRemaining = '') then
      break;
  end;

  Result := 0;
end;

function TryReadInstallerMetadata(
  var InstalledVersionValue: string;
  var InstallDirValue: string
): Boolean;
var
  KeyPath: string;
begin
  InstalledVersionValue := '';
  InstallDirValue := '';
  KeyPath := InstallerMetadataRegistryKey();

  Result := RegQueryStringValue(HKCU, KeyPath, 'InstallDir', InstallDirValue);
  if not RegQueryStringValue(HKCU, KeyPath, 'DisplayVersion', InstalledVersionValue) then
    InstalledVersionValue := '';

  Result := Result or (InstalledVersionValue <> '');
end;

function TryReadExistingInstallFromRoot(
  const RootKey: Integer;
  var InstalledVersionValue: string;
  var InstallDirValue: string
): Boolean;
var
  KeyPath: string;
begin
  InstalledVersionValue := '';
  InstallDirValue := '';
  KeyPath := UninstallRegistryKey();

  Result := RegQueryStringValue(RootKey, KeyPath, 'Inno Setup: App Path', InstallDirValue);
  if not Result then
    Result := RegQueryStringValue(RootKey, KeyPath, 'InstallLocation', InstallDirValue);

  if not RegQueryStringValue(RootKey, KeyPath, 'DisplayVersion', InstalledVersionValue) then
    InstalledVersionValue := '';

  Result := Result or (InstalledVersionValue <> '');
end;

function TryReadDefaultInstallVersion(
  var InstalledVersionValue: string;
  var InstallDirValue: string
): Boolean;
var
  ExePath: string;
begin
  InstalledVersionValue := '';
  InstallDirValue := '';
  ExePath := DefaultInstallExePath();

  if not FileExists(ExePath) then
  begin
    Result := False;
    exit;
  end;

  InstallDirValue := DefaultInstallDir();
  Result := GetVersionNumbersString(ExePath, InstalledVersionValue);
  if not Result then
  begin
    InstalledVersionValue := '';
    Result := True;
  end;
end;

procedure DetectExistingInstall();
begin
  ExistingInstallDetected := False;
  ExistingInstallVersion := '';
  ExistingInstallDir := '';
  ExistingInstallComparison := 0;

  if TryReadInstallerMetadata(ExistingInstallVersion, ExistingInstallDir) or
     TryReadExistingInstallFromRoot(HKCU, ExistingInstallVersion, ExistingInstallDir) or
     TryReadExistingInstallFromRoot(HKLM, ExistingInstallVersion, ExistingInstallDir) or
     TryReadDefaultInstallVersion(ExistingInstallVersion, ExistingInstallDir) then
  begin
    ExistingInstallDetected := True;
    if ExistingInstallVersion <> '' then
      ExistingInstallComparison := CompareVersionText(ExistingInstallVersion, '{#AppVersion}')
    else
      ExistingInstallComparison := -1;
  end;
end;

procedure UpdateWelcomePageText();
begin
  if not ExistingInstallDetected then
    exit;

  if ExistingInstallComparison < 0 then
  begin
    WizardForm.WelcomeLabel1.Caption := 'Update {#AppName}';
    WizardForm.WelcomeLabel2.Caption :=
      '{#AppName} ' + InstalledVersionLabel() + ' is already installed.'#13#10 +
      'Setup will update it to version {#AppVersion} and keep your existing user data.';
  end
  else if ExistingInstallComparison = 0 then
  begin
    WizardForm.WelcomeLabel1.Caption := 'Refresh {#AppName}';
    WizardForm.WelcomeLabel2.Caption :=
      '{#AppName} {#AppVersion} is already installed.'#13#10 +
      'Setup will repair the current installation in place and keep your existing user data.';
  end
  else
  begin
    WizardForm.WelcomeLabel1.Caption := 'Replace {#AppName}';
    WizardForm.WelcomeLabel2.Caption :=
      'A newer {#AppName} ' + InstalledVersionLabel() + ' is already installed.'#13#10 +
      'Continuing will replace it with version {#AppVersion} in the selected folder.';
  end;
end;

function LooksProtectedDir(const DirName: string): Boolean;
var
  Normalized: string;
  ProgramFilesDir: string;
  ProgramFilesX86Dir: string;
  WindowsDir: string;
begin
  Normalized := Lowercase(ExpandConstant(DirName));
  ProgramFilesDir := Lowercase(ExpandConstant('{pf}'));
  ProgramFilesX86Dir := Lowercase(ExpandConstant('{pf32}'));
  WindowsDir := Lowercase(ExpandConstant('{win}'));
  Result :=
    ((Pos(ProgramFilesDir, Normalized) = 1) and (ProgramFilesDir <> '')) or
    ((Pos(ProgramFilesX86Dir, Normalized) = 1) and (ProgramFilesX86Dir <> '')) or
    ((Pos(WindowsDir, Normalized) = 1) and (WindowsDir <> ''));
end;

function IsWritableInstallDir(const DirName: string): Boolean;
var
  ProbeFile: string;
begin
  Result := False;
  if DirName = '' then
    exit;

  if not DirExists(DirName) then
    if not ForceDirectories(DirName) then
      exit;

  ProbeFile := AddBackslash(DirName) + 'aoryn-write-test.tmp';
  try
    Result := SaveStringToFile(ProbeFile, 'ok', False);
    if Result and FileExists(ProbeFile) then
      DeleteFile(ProbeFile);
  except
    Result := False;
  end;
end;

procedure ClearDirPageProtectionHint();
var
  ExistingInstallNotice: string;
begin
  if Assigned(DirDataNoticeLabel) then
  begin
    ExistingInstallNotice := '';
    if ExistingInstallDetected then
    begin
      ExistingInstallNotice := '{#AppName} ' + InstalledVersionLabel() + ' is already installed';
      if ExistingInstallDir <> '' then
        ExistingInstallNotice := ExistingInstallNotice + ' in ' + ExistingInstallDir;
      ExistingInstallNotice :=
        ExistingInstallNotice + '.'#13#10 +
        'Keep this folder to update the existing installation in place. Choose a different folder only if you intentionally want a separate copy.'#13#10;
    end;

    DirDataNoticeLabel.Caption :=
      ExistingInstallNotice +
      'This installer stays in current-user mode. Keep the default folder or choose another writable folder such as D:\Apps\Aoryn.'#13#10 +
      'Config stays in %APPDATA%\Aoryn. Runs, logs, screenshots, and cache stay in %LOCALAPPDATA%\Aoryn.';
  end;
end;

procedure InitializeWizard();
begin
  DetectExistingInstall();
  DirDataNoticeLabel := TNewStaticText.Create(WizardForm.SelectDirPage);
  DirDataNoticeLabel.Parent := WizardForm.DirEdit.Parent;
  DirDataNoticeLabel.Left := WizardForm.DirEdit.Left;
  DirDataNoticeLabel.Top := WizardForm.DirEdit.Top + WizardForm.DirEdit.Height + ScaleY(14);
  DirDataNoticeLabel.Width :=
    (WizardForm.DirBrowseButton.Left + WizardForm.DirBrowseButton.Width) - WizardForm.DirEdit.Left;
  DirDataNoticeLabel.AutoSize := True;
  DirDataNoticeLabel.WordWrap := True;
  if ExistingInstallDetected and (ExistingInstallDir <> '') then
    WizardForm.DirEdit.Text := ExistingInstallDir;
  ClearDirPageProtectionHint();
  UpdateWelcomePageText();
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if CurPageID = wpSelectDir then
  begin
    ClearDirPageProtectionHint();
    if LooksProtectedDir(WizardDirValue) then
    begin
      MsgBox(
        'Please choose a writable folder in your user space. This installer stays in current-user mode and will not elevate to Program Files.',
        mbError,
        MB_OK
      );
      Result := False;
      exit;
    end;

    if not IsWritableInstallDir(WizardDirValue) then
    begin
      MsgBox(
        'The selected folder is not writable for the current user. Please choose another install location.',
        mbError,
        MB_OK
      );
      Result := False;
    end;
  end;

  if Result and (CurPageID = wpReady) and ExistingInstallDetected and (ExistingInstallDir <> '') then
  begin
    if CompareText(NormalizeDirName(WizardDirValue), NormalizeDirName(ExistingInstallDir)) <> 0 then
    begin
      Result :=
        MsgBox(
          '{#AppName} ' + InstalledVersionLabel() + ' is already installed in:'#13#10 +
          ExistingInstallDir + #13#10#13#10 +
          'Installing to a different folder will create a separate copy instead of updating the existing installation.'#13#10 +
          'Do you want to continue with a separate copy?',
          mbConfirmation,
          MB_YESNO
        ) = IDYES;
    end;
  end;
end;

function ShouldRemoveUserData: Boolean;
begin
  Result := RemoveUserDataOnUninstall;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if (CurUninstallStep = usUninstall) and (not UninstallPromptShown) then
  begin
    UninstallPromptShown := True;
    RemoveUserDataOnUninstall :=
      MsgBox(
        'Do you also want to remove Aoryn user data?'#13#10#13#10 +
        'Yes: delete %APPDATA%\Aoryn and %LOCALAPPDATA%\Aoryn.'#13#10 +
        'No: keep your configuration, logs, cache, and run history for a future reinstall.',
        mbConfirmation,
        MB_YESNO
      ) = IDYES;
  end;
end;
