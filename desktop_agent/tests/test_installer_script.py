from pathlib import Path


def test_inno_setup_script_keeps_custom_install_and_user_data_policy():
    script = Path("installer") / "Aoryn.iss"
    source = script.read_text(encoding="utf-8")

    assert r"DefaultDirName={localappdata}\Programs\{#AppName}" in source
    assert "UsePreviousAppDir=yes" in source
    assert "DisableDirPage=no" in source
    assert "This installer stays in current-user mode." in source
    assert r"%APPDATA%\Aoryn" in source
    assert r"%LOCALAPPDATA%\Aoryn" in source
    assert "[UninstallDelete]" in source
    assert r'Name: "{userappdata}\Aoryn"; Check: ShouldRemoveUserData' in source
    assert r'Name: "{localappdata}\Aoryn"; Check: ShouldRemoveUserData' in source
    assert "function ShouldRemoveUserData: Boolean;" in source
    assert "Do you also want to remove Aoryn user data?" in source
    assert "ScaleY(52)" not in source
    assert "DirDataNoticeLabel.AutoSize := True;" in source


def test_inno_setup_script_detects_existing_install_for_updates():
    script = Path("installer") / "Aoryn.iss"
    source = script.read_text(encoding="utf-8")

    assert r'Subkey: "Software\Aoryn\DesktopInstaller"' in source
    assert 'ValueName: "InstallDir"' in source
    assert 'ValueName: "DisplayVersion"' in source
    assert "function InstallerMetadataRegistryKey(): string;" in source
    assert "function TryReadInstallerMetadata(" in source
    assert r"Software\Microsoft\Windows\CurrentVersion\Uninstall\{#AppId}_is1" in source
    assert "function DefaultInstallExePath(): string;" in source
    assert "function TryReadDefaultInstallVersion(" in source
    assert "GetVersionNumbersString(ExePath, InstalledVersionValue)" in source
    assert "if TryReadInstallerMetadata(ExistingInstallVersion, ExistingInstallDir) or" in source
    assert "function TryReadExistingInstallFromRoot(" in source
    assert "DisplayVersion" in source
    assert "Inno Setup: App Path" in source
    assert "procedure DetectExistingInstall();" in source
    assert "WizardForm.WelcomeLabel1.Caption := 'Update {#AppName}'" in source
    assert "Setup will update it to version {#AppVersion}" in source
    assert "Keep this folder to update the existing installation in place." in source
    assert "will create a separate copy instead of updating the existing installation" in source
