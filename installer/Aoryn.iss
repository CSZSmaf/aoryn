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
#ifndef BrowserExeName
  #define BrowserExeName "AorynBrowser.exe"
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
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"

[Files]
Source: "{#ReleaseSourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Registry]
Root: HKCU; Subkey: "Software\Aoryn\DesktopInstaller"; ValueType: string; ValueName: "InstallDir"; ValueData: "{app}"; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Aoryn\DesktopInstaller"; ValueType: string; ValueName: "DisplayVersion"; ValueData: "{#AppVersion}"; Flags: uninsdeletevalue uninsdeletekeyifempty

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{autoprograms}\{#AppName} Browser"; Filename: "{app}\{#BrowserExeName}"
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
  ExistingInstallCount: Integer;
  ExistingInstallVersion: string;
  ExistingInstallDir: string;
  ExistingInstallComparison: Integer;
  ExistingInstallUninstallCommand: string;
  ExistingInstallVersions: array of string;
  ExistingInstallDirs: array of string;
  ExistingInstallUninstallCommands: array of string;
  ExistingInstallSources: array of string;
  ExistingInstallComparisons: array of Integer;

function NormalizeDirName(const DirName: string): string;
begin
  Result := Lowercase(RemoveBackslashUnlessRoot(ExpandConstant(DirName)));
end;

function NormalizeCommandKey(const CommandLine: string): string;
begin
  Result := Lowercase(Trim(CommandLine));
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

function LegacyUninstallRegistryKey(): string;
begin
  Result := 'Software\Microsoft\Windows\CurrentVersion\Uninstall';
end;

function UpgradeUninstallKeepUserDataSwitch(): string;
begin
  Result := '/KEEPUSERDATA';
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

function CompareDetectedVersionText(const VersionText: string): Integer;
begin
  if Trim(VersionText) = '' then
    Result := -1
  else
    Result := CompareVersionText(VersionText, '{#AppVersion}');
end;

function StringContainsText(const Value: string; const Needle: string): Boolean;
begin
  Result := Pos(Uppercase(Needle), Uppercase(Value)) > 0;
end;

procedure ResetExistingInstallState();
begin
  ExistingInstallDetected := False;
  ExistingInstallCount := 0;
  ExistingInstallVersion := '';
  ExistingInstallDir := '';
  ExistingInstallComparison := 0;
  ExistingInstallUninstallCommand := '';
  SetArrayLength(ExistingInstallVersions, 0);
  SetArrayLength(ExistingInstallDirs, 0);
  SetArrayLength(ExistingInstallUninstallCommands, 0);
  SetArrayLength(ExistingInstallSources, 0);
  SetArrayLength(ExistingInstallComparisons, 0);
end;

procedure SyncExistingInstallSummary();
var
  Index: Integer;
begin
  ExistingInstallCount := GetArrayLength(ExistingInstallVersions);
  ExistingInstallDetected := ExistingInstallCount > 0;
  ExistingInstallVersion := '';
  ExistingInstallDir := '';
  ExistingInstallComparison := -1;
  ExistingInstallUninstallCommand := '';

  if not ExistingInstallDetected then
  begin
    ExistingInstallComparison := 0;
    exit;
  end;

  for Index := 0 to ExistingInstallCount - 1 do
  begin
    if (ExistingInstallDir = '') and (Trim(ExistingInstallDirs[Index]) <> '') then
      ExistingInstallDir := ExistingInstallDirs[Index];
    if (ExistingInstallUninstallCommand = '') and (Trim(ExistingInstallUninstallCommands[Index]) <> '') then
      ExistingInstallUninstallCommand := ExistingInstallUninstallCommands[Index];
    if Trim(ExistingInstallVersions[Index]) <> '' then
    begin
      if (ExistingInstallVersion = '') or (ExistingInstallComparisons[Index] > ExistingInstallComparison) then
      begin
        ExistingInstallVersion := ExistingInstallVersions[Index];
        ExistingInstallComparison := ExistingInstallComparisons[Index];
      end;
    end;
  end;
end;

function TryReadLocalUninstallCommand(
  const InstallDirValue: string;
  var UninstallCommandValue: string
): Boolean;
var
  FindRec: TFindRec;
  CandidatePath: string;
begin
  UninstallCommandValue := '';
  if Trim(InstallDirValue) = '' then
  begin
    Result := False;
    exit;
  end;

  if not FindFirst(AddBackslash(InstallDirValue) + 'unins???.exe', FindRec) then
  begin
    Result := False;
    exit;
  end;

  try
    repeat
      CandidatePath := AddBackslash(InstallDirValue) + FindRec.Name;
      if FileExists(CandidatePath) then
      begin
        UninstallCommandValue :=
          '"' + CandidatePath + '" /VERYSILENT /SUPPRESSMSGBOXES /NORESTART ' +
          UpgradeUninstallKeepUserDataSwitch();
        Result := True;
        exit;
      end;
    until not FindNext(FindRec);
  finally
    FindClose(FindRec);
  end;

  Result := False;
end;

procedure AddExistingInstallCandidate(
  const SourceName: string;
  const InstalledVersionValue: string;
  const InstallDirValue: string;
  const UninstallCommandValue: string
);
var
  Index: Integer;
  NewIndex: Integer;
  ExistingDirKey: string;
  ExistingCommandKey: string;
  CandidateDirKey: string;
  CandidateCommandKey: string;
  ResolvedUninstallCommand: string;
begin
  ResolvedUninstallCommand := Trim(UninstallCommandValue);
  if (ResolvedUninstallCommand = '') and (Trim(InstallDirValue) <> '') then
    TryReadLocalUninstallCommand(InstallDirValue, ResolvedUninstallCommand);

  if
    (Trim(InstalledVersionValue) = '') and
    (Trim(InstallDirValue) = '') and
    (ResolvedUninstallCommand = '')
  then
    exit;

  CandidateDirKey := NormalizeDirName(InstallDirValue);
  CandidateCommandKey := NormalizeCommandKey(ResolvedUninstallCommand);

  for Index := 0 to GetArrayLength(ExistingInstallVersions) - 1 do
  begin
    ExistingDirKey := NormalizeDirName(ExistingInstallDirs[Index]);
    ExistingCommandKey := NormalizeCommandKey(ExistingInstallUninstallCommands[Index]);

    if
      ((CandidateDirKey <> '') and (ExistingDirKey <> '') and (CompareText(CandidateDirKey, ExistingDirKey) = 0)) or
      ((CandidateCommandKey <> '') and (ExistingCommandKey <> '') and (CompareText(CandidateCommandKey, ExistingCommandKey) = 0))
    then
    begin
      if (Trim(ExistingInstallVersions[Index]) = '') and (Trim(InstalledVersionValue) <> '') then
        ExistingInstallVersions[Index] := InstalledVersionValue
      else if
        (Trim(InstalledVersionValue) <> '') and
        (CompareDetectedVersionText(InstalledVersionValue) > ExistingInstallComparisons[Index])
      then
        ExistingInstallVersions[Index] := InstalledVersionValue;

      if (Trim(ExistingInstallDirs[Index]) = '') and (Trim(InstallDirValue) <> '') then
        ExistingInstallDirs[Index] := InstallDirValue;
      if (Trim(ExistingInstallUninstallCommands[Index]) = '') and (ResolvedUninstallCommand <> '') then
        ExistingInstallUninstallCommands[Index] := ResolvedUninstallCommand;
      if (Trim(ExistingInstallSources[Index]) = '') and (Trim(SourceName) <> '') then
        ExistingInstallSources[Index] := SourceName;

      ExistingInstallComparisons[Index] := CompareDetectedVersionText(ExistingInstallVersions[Index]);
      SyncExistingInstallSummary();
      exit;
    end;
  end;

  NewIndex := GetArrayLength(ExistingInstallVersions);
  SetArrayLength(ExistingInstallVersions, NewIndex + 1);
  SetArrayLength(ExistingInstallDirs, NewIndex + 1);
  SetArrayLength(ExistingInstallUninstallCommands, NewIndex + 1);
  SetArrayLength(ExistingInstallSources, NewIndex + 1);
  SetArrayLength(ExistingInstallComparisons, NewIndex + 1);
  ExistingInstallVersions[NewIndex] := InstalledVersionValue;
  ExistingInstallDirs[NewIndex] := InstallDirValue;
  ExistingInstallUninstallCommands[NewIndex] := ResolvedUninstallCommand;
  ExistingInstallSources[NewIndex] := SourceName;
  ExistingInstallComparisons[NewIndex] := CompareDetectedVersionText(InstalledVersionValue);
  SyncExistingInstallSummary();
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

function TryReadUninstallCommandFromRoot(
  const RootKey: Integer;
  var UninstallCommandValue: string
): Boolean;
var
  KeyPath: string;
begin
  UninstallCommandValue := '';
  KeyPath := UninstallRegistryKey();

  Result := RegQueryStringValue(RootKey, KeyPath, 'UninstallString', UninstallCommandValue);
  if (not Result) or (Trim(UninstallCommandValue) = '') then
    Result := RegQueryStringValue(RootKey, KeyPath, 'QuietUninstallString', UninstallCommandValue);

  if Result then
    UninstallCommandValue := Trim(UninstallCommandValue);
end;

function TryReadExistingUninstallCommand(var UninstallCommandValue: string): Boolean;
begin
  Result :=
    TryReadUninstallCommandFromRoot(HKCU, UninstallCommandValue) or
    TryReadUninstallCommandFromRoot(HKLM, UninstallCommandValue);
end;

function ExtractCommandExecutable(const CommandLine: string): string;
var
  Parsed: string;
  EndPos: Integer;
begin
  Parsed := Trim(CommandLine);
  if Parsed = '' then
  begin
    Result := '';
    exit;
  end;

  if Copy(Parsed, 1, 1) = '"' then
  begin
    Delete(Parsed, 1, 1);
    EndPos := Pos('"', Parsed);
    if EndPos > 0 then
      Result := Copy(Parsed, 1, EndPos - 1)
    else
      Result := Parsed;
  end
  else
  begin
    EndPos := Pos(' ', Parsed);
    if EndPos > 0 then
      Result := Copy(Parsed, 1, EndPos - 1)
    else
      Result := Parsed;
  end;
end;

function ExtractCommandParameters(const CommandLine: string): string;
var
  Parsed: string;
  EndPos: Integer;
begin
  Parsed := Trim(CommandLine);
  if Parsed = '' then
  begin
    Result := '';
    exit;
  end;

  if Copy(Parsed, 1, 1) = '"' then
  begin
    Delete(Parsed, 1, 1);
    EndPos := Pos('"', Parsed);
    if EndPos > 0 then
      Result := Trim(Copy(Parsed, EndPos + 1, Length(Parsed)))
    else
      Result := '';
  end
  else
  begin
    EndPos := Pos(' ', Parsed);
    if EndPos > 0 then
      Result := Trim(Copy(Parsed, EndPos + 1, Length(Parsed)))
    else
      Result := '';
  end;
end;

function AppendCommandArgument(const ExistingValue: string; const NextValue: string): string;
begin
  if ExistingValue = '' then
    Result := NextValue
  else if NextValue = '' then
    Result := ExistingValue
  else
    Result := ExistingValue + ' ' + NextValue;
end;

function ExistingInstallUninstallParams(const CommandLine: string): string;
var
  UpperParams: string;
begin
  Result := ExtractCommandParameters(CommandLine);
  UpperParams := Uppercase(Result);

  if (Pos('/SILENT', UpperParams) = 0) and (Pos('/VERYSILENT', UpperParams) = 0) then
    Result := AppendCommandArgument(Result, '/SILENT');
  if Pos('/NORESTART', UpperParams) = 0 then
    Result := AppendCommandArgument(Result, '/NORESTART');
  if Pos(Uppercase(UpgradeUninstallKeepUserDataSwitch()), UpperParams) = 0 then
    Result := AppendCommandArgument(Result, UpgradeUninstallKeepUserDataSwitch());
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

function IsLikelyAorynInstallEntry(const RootKey: Integer; const SubkeyName: string): Boolean;
var
  KeyPath: string;
  DisplayNameValue: string;
  AppNameValue: string;
  PublisherValue: string;
  InstallLocationValue: string;
  AppPathValue: string;
  UninstallStringValue: string;
  QuietUninstallValue: string;
  NameMatch: Boolean;
  PublisherMatch: Boolean;
  PathMatch: Boolean;
begin
  KeyPath := LegacyUninstallRegistryKey() + '\' + SubkeyName;
  DisplayNameValue := '';
  AppNameValue := '';
  PublisherValue := '';
  InstallLocationValue := '';
  AppPathValue := '';
  UninstallStringValue := '';
  QuietUninstallValue := '';

  RegQueryStringValue(RootKey, KeyPath, 'DisplayName', DisplayNameValue);
  RegQueryStringValue(RootKey, KeyPath, 'AppName', AppNameValue);
  RegQueryStringValue(RootKey, KeyPath, 'Publisher', PublisherValue);
  RegQueryStringValue(RootKey, KeyPath, 'InstallLocation', InstallLocationValue);
  RegQueryStringValue(RootKey, KeyPath, 'Inno Setup: App Path', AppPathValue);
  RegQueryStringValue(RootKey, KeyPath, 'UninstallString', UninstallStringValue);
  RegQueryStringValue(RootKey, KeyPath, 'QuietUninstallString', QuietUninstallValue);

  NameMatch :=
    (CompareText(Trim(DisplayNameValue), '{#AppName}') = 0) or
    (CompareText(Trim(AppNameValue), '{#AppName}') = 0);
  PublisherMatch := CompareText(Trim(PublisherValue), '{#AppPublisher}') = 0;
  PathMatch :=
    StringContainsText(InstallLocationValue, '{#AppName}') or
    StringContainsText(AppPathValue, '{#AppName}') or
    StringContainsText(UninstallStringValue, '{#AppName}') or
    StringContainsText(QuietUninstallValue, '{#AppName}');

  Result := NameMatch or (PublisherMatch and PathMatch);
end;

function TryReadLegacyInstallFromRootSubkey(
  const RootKey: Integer;
  const SubkeyName: string;
  var InstalledVersionValue: string;
  var InstallDirValue: string;
  var UninstallCommandValue: string
): Boolean;
var
  KeyPath: string;
begin
  InstalledVersionValue := '';
  InstallDirValue := '';
  UninstallCommandValue := '';

  if not IsLikelyAorynInstallEntry(RootKey, SubkeyName) then
  begin
    Result := False;
    exit;
  end;

  KeyPath := LegacyUninstallRegistryKey() + '\' + SubkeyName;
  Result := RegQueryStringValue(RootKey, KeyPath, 'InstallLocation', InstallDirValue);
  if not Result then
    Result := RegQueryStringValue(RootKey, KeyPath, 'Inno Setup: App Path', InstallDirValue);

  if not RegQueryStringValue(RootKey, KeyPath, 'DisplayVersion', InstalledVersionValue) then
    InstalledVersionValue := '';

  if not RegQueryStringValue(RootKey, KeyPath, 'UninstallString', UninstallCommandValue) then
    RegQueryStringValue(RootKey, KeyPath, 'QuietUninstallString', UninstallCommandValue);
  UninstallCommandValue := Trim(UninstallCommandValue);

  Result := Result or (InstalledVersionValue <> '') or (UninstallCommandValue <> '');
end;

procedure DetectLegacyInstallEntriesFromRoot(const RootKey: Integer; const SourceName: string);
var
  SubkeyNames: TArrayOfString;
  Index: Integer;
  InstalledVersionValue: string;
  InstallDirValue: string;
  UninstallCommandValue: string;
begin
  if not RegGetSubkeyNames(RootKey, LegacyUninstallRegistryKey(), SubkeyNames) then
    exit;

  for Index := 0 to GetArrayLength(SubkeyNames) - 1 do
  begin
    if TryReadLegacyInstallFromRootSubkey(
      RootKey,
      SubkeyNames[Index],
      InstalledVersionValue,
      InstallDirValue,
      UninstallCommandValue
    ) then
      AddExistingInstallCandidate(SourceName, InstalledVersionValue, InstallDirValue, UninstallCommandValue);
  end;
end;

procedure DetectExistingInstall();
var
  InstalledVersionValue: string;
  InstallDirValue: string;
  UninstallCommandValue: string;
begin
  ResetExistingInstallState();

  InstalledVersionValue := '';
  InstallDirValue := '';
  UninstallCommandValue := '';
  if TryReadInstallerMetadata(InstalledVersionValue, InstallDirValue) then
  begin
    TryReadExistingUninstallCommand(UninstallCommandValue);
    AddExistingInstallCandidate('installer metadata', InstalledVersionValue, InstallDirValue, UninstallCommandValue);
  end;

  InstalledVersionValue := '';
  InstallDirValue := '';
  UninstallCommandValue := '';
  if TryReadExistingInstallFromRoot(HKCU, InstalledVersionValue, InstallDirValue) then
  begin
    TryReadUninstallCommandFromRoot(HKCU, UninstallCommandValue);
    AddExistingInstallCandidate('current uninstall key (HKCU)', InstalledVersionValue, InstallDirValue, UninstallCommandValue);
  end;

  InstalledVersionValue := '';
  InstallDirValue := '';
  UninstallCommandValue := '';
  if TryReadExistingInstallFromRoot(HKLM, InstalledVersionValue, InstallDirValue) then
  begin
    TryReadUninstallCommandFromRoot(HKLM, UninstallCommandValue);
    AddExistingInstallCandidate('current uninstall key (HKLM)', InstalledVersionValue, InstallDirValue, UninstallCommandValue);
  end;

  InstalledVersionValue := '';
  InstallDirValue := '';
  if TryReadDefaultInstallVersion(InstalledVersionValue, InstallDirValue) then
    AddExistingInstallCandidate('default install dir', InstalledVersionValue, InstallDirValue, '');

  DetectLegacyInstallEntriesFromRoot(HKCU, 'legacy uninstall key (HKCU)');
  DetectLegacyInstallEntriesFromRoot(HKLM, 'legacy uninstall key (HKLM)');
  SyncExistingInstallSummary();
end;

procedure UpdateWelcomePageText();
begin
  if not ExistingInstallDetected then
    exit;

  if ExistingInstallCount = 1 then
  begin
    if ExistingInstallComparison > 0 then
      WizardForm.WelcomeLabel1.Caption := 'Replace {#AppName}'
    else
      WizardForm.WelcomeLabel1.Caption := 'Update {#AppName}';

    WizardForm.WelcomeLabel2.Caption :=
      '{#AppName} ' + InstalledVersionLabel() + ' is already installed.'#13#10 +
      'Setup will clean the existing copy before installing version {#AppVersion} and keep your existing user data.';
  end
  else
  begin
    if ExistingInstallComparison > 0 then
      WizardForm.WelcomeLabel1.Caption := 'Clean & Replace {#AppName}'
    else
      WizardForm.WelcomeLabel1.Caption := 'Clean & Update {#AppName}';

    WizardForm.WelcomeLabel2.Caption :=
      'Setup found ' + IntToStr(ExistingInstallCount) + ' installed {#AppName} copies.'#13#10 +
      'It will uninstall the detected copies before installing version {#AppVersion} and keep your existing user data.';

    if ExistingInstallComparison > 0 then
      WizardForm.WelcomeLabel2.Caption :=
        WizardForm.WelcomeLabel2.Caption + #13#10 +
        'One of the detected copies is newer ({#AppName} ' + InstalledVersionLabel() + ').';
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
      if ExistingInstallCount = 1 then
        ExistingInstallNotice := '{#AppName} ' + InstalledVersionLabel() + ' is already installed'
      else
        ExistingInstallNotice := 'Setup found ' + IntToStr(ExistingInstallCount) + ' installed {#AppName} copies';

      if ExistingInstallDir <> '' then
        ExistingInstallNotice := ExistingInstallNotice + ' in ' + ExistingInstallDir;
      ExistingInstallNotice :=
        ExistingInstallNotice + '.'#13#10 +
        'Setup will clean old copies before installing version {#AppVersion}. Keep this folder or choose another writable folder if you want the refreshed copy somewhere else.'#13#10;
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
      exit;
    end;
  end;

  if Result and (CurPageID = wpReady) and (ExistingInstallComparison > 0) then
  begin
    Result :=
      MsgBox(
        'A newer {#AppName} ' + InstalledVersionLabel() + ' is already installed.'#13#10#13#10 +
        'Do you want Setup to uninstall the detected copy and replace it with version {#AppVersion}?',
        mbConfirmation,
        MB_YESNO
      ) = IDYES;
  end;
end;

function ShouldRemoveUserData: Boolean;
begin
  Result := RemoveUserDataOnUninstall;
end;

function HasKeepUserDataSwitch(): Boolean;
var
  CommandTail: string;
begin
  CommandTail := Uppercase(GetCmdTail());
  Result :=
    (Pos('/KEEPUSERDATA', CommandTail) > 0) or
    (Pos('-KEEPUSERDATA', CommandTail) > 0);
end;

function ExistingInstallEntryDescription(const Index: Integer): string;
begin
  Result := '{#AppName}';
  if Trim(ExistingInstallVersions[Index]) <> '' then
    Result := Result + ' ' + ExistingInstallVersions[Index]
  else
    Result := Result + ' earlier build';

  if Trim(ExistingInstallDirs[Index]) <> '' then
    Result := Result + ' in ' + ExistingInstallDirs[Index];
end;

function BuildExistingInstallManualRemovalMessage(const Index: Integer; const ProblemText: string): string;
var
  DetailText: string;
begin
  DetailText := ExistingInstallEntryDescription(Index);
  if Trim(ExistingInstallSources[Index]) <> '' then
    DetailText := DetailText + ' (' + ExistingInstallSources[Index] + ')';

  Result :=
    ProblemText + #13#10#13#10 +
    'Detected copy: ' + DetailText + #13#10#13#10 +
    'Please uninstall this version manually, then run this installer again.';
end;

function PrepareToInstall(var NeedsRestart: Boolean): string;
var
  Index: Integer;
  UninstallCommand: string;
  UninstallExecutablePath: string;
  UninstallResultCode: Integer;
  UninstallParams: string;
begin
  NeedsRestart := False;
  Result := '';

  if not ExistingInstallDetected then
    exit;

  for Index := 0 to ExistingInstallCount - 1 do
  begin
    UninstallCommand := Trim(ExistingInstallUninstallCommands[Index]);
    if UninstallCommand = '' then
    begin
      Result := BuildExistingInstallManualRemovalMessage(
        Index,
        'Setup found an existing {#AppName} copy, but could not find a trusted uninstaller for it.'
      );
      exit;
    end;

    UninstallExecutablePath := ExtractCommandExecutable(UninstallCommand);
    if (UninstallExecutablePath = '') or (not FileExists(UninstallExecutablePath)) then
    begin
      Result := BuildExistingInstallManualRemovalMessage(
        Index,
        'Setup found an existing {#AppName} copy, but could not open its uninstaller.'
      );
      exit;
    end;

    UninstallParams := ExistingInstallUninstallParams(UninstallCommand);
    if not Exec(
      UninstallExecutablePath,
      UninstallParams,
      ExtractFileDir(UninstallExecutablePath),
      SW_SHOW,
      ewWaitUntilTerminated,
      UninstallResultCode
    ) then
    begin
      Result := BuildExistingInstallManualRemovalMessage(
        Index,
        'Setup could not start the detected {#AppName} uninstaller.'
      );
      exit;
    end;

    if UninstallResultCode <> 0 then
    begin
      Result := BuildExistingInstallManualRemovalMessage(
        Index,
        'The detected {#AppName} uninstall did not complete successfully.'
      );
      exit;
    end;
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if (CurUninstallStep = usUninstall) and (not UninstallPromptShown) then
  begin
    UninstallPromptShown := True;
    if HasKeepUserDataSwitch() then
    begin
      RemoveUserDataOnUninstall := False;
      exit;
    end;

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
