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
    assert "function UpgradeUninstallKeepUserDataSwitch(): string;" in source
    assert "function HasKeepUserDataSwitch(): Boolean;" in source
    assert "Pos('/KEEPUSERDATA', CommandTail) > 0" in source
    assert "if HasKeepUserDataSwitch() then" in source
    assert "Do you also want to remove Aoryn user data?" in source
    assert "ScaleY(52)" not in source
    assert "DirDataNoticeLabel.AutoSize := True;" in source


def test_inno_setup_script_detects_existing_install_for_strict_upgrades():
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
    assert "function TryReadUninstallCommandFromRoot(" in source
    assert "'UninstallString'" in source
    assert "DisplayVersion" in source
    assert "Inno Setup: App Path" in source
    assert "procedure DetectExistingInstall();" in source
    assert "WizardForm.WelcomeLabel1.Caption := 'Update {#AppName}'" in source
    assert "Setup will uninstall version " in source
    assert "function PrepareToInstall(var NeedsRestart: Boolean): string;" in source
    assert "Exec(" in source
    assert "Please uninstall the existing version manually, then run this installer again." in source
    assert "This setup upgrades the existing installation and does not create a second copy." in source
    assert "To move {#AppName} to a different folder, uninstall it first and then run Setup again." in source
    assert "Do you want Setup to uninstall it and replace it with version {#AppVersion}?" in source
    assert "will create a separate copy instead of updating the existing installation" not in source
