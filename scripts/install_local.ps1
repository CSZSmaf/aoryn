<#
.SYNOPSIS
    Install a PyInstaller-built Aoryn bundle locally for the current user.

.DESCRIPTION
    Mirrors installer/Aoryn.iss: copies the built folder to
    %LOCALAPPDATA%\Programs\Aoryn and creates Start Menu + Desktop shortcuts.
    Per-user, no administrator rights required.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\install_local.ps1
    powershell -ExecutionPolicy Bypass -File scripts\install_local.ps1 -Source dist\Aoryn
#>
param(
    [string]$Source = "dist\Aoryn",
    [string]$AppName = "Aoryn",
    [string]$ExeName = "Aoryn.exe",
    [switch]$NoDesktopShortcut,
    [switch]$Launch
)

$ErrorActionPreference = "Stop"

# Resolve the source folder relative to the repository root.
$repoRoot = Split-Path -Parent $PSScriptRoot
if (-not [System.IO.Path]::IsPathRooted($Source)) {
    $Source = Join-Path $repoRoot $Source
}
$sourceExe = Join-Path $Source $ExeName
if (-not (Test-Path $sourceExe)) {
    throw "Build output not found: $sourceExe. Run `python -m PyInstaller Aoryn.spec --noconfirm` first."
}

$installDir = Join-Path $env:LOCALAPPDATA "Programs\$AppName"
$installedExe = Join-Path $installDir $ExeName

Write-Host "Installing $AppName -> $installDir"

# Stop any running instance so files are not locked.
Get-Process -Name ([System.IO.Path]::GetFileNameWithoutExtension($ExeName)) -ErrorAction SilentlyContinue |
    ForEach-Object {
        Write-Host "  stopping running $ExeName (pid $($_.Id))"
        try { $_.CloseMainWindow() | Out-Null } catch {}
        Start-Sleep -Milliseconds 400
        try { $_ | Stop-Process -Force -ErrorAction Stop } catch {}
    }

# Clean and recreate the install directory.
if (Test-Path $installDir) {
    Remove-Item -Recurse -Force $installDir -ErrorAction SilentlyContinue
}
New-Item -ItemType Directory -Force -Path $installDir | Out-Null

Write-Host "  copying files..."
Copy-Item -Path (Join-Path $Source "*") -Destination $installDir -Recurse -Force

if (-not (Test-Path $installedExe)) {
    throw "Copy failed: $installedExe is missing."
}

# Create shortcuts (Start Menu + Desktop) via WScript.Shell.
$shell = New-Object -ComObject WScript.Shell

$startMenuDir = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs"
$startMenuLnk = Join-Path $startMenuDir "$AppName.lnk"
$sc = $shell.CreateShortcut($startMenuLnk)
$sc.TargetPath = $installedExe
$sc.WorkingDirectory = $installDir
$sc.IconLocation = "$installedExe,0"
$sc.Description = "$AppName Desktop App"
$sc.Save()
Write-Host "  Start Menu shortcut: $startMenuLnk"

if (-not $NoDesktopShortcut) {
    $desktopDir = [Environment]::GetFolderPath("Desktop")
    $desktopLnk = Join-Path $desktopDir "$AppName.lnk"
    $sc2 = $shell.CreateShortcut($desktopLnk)
    $sc2.TargetPath = $installedExe
    $sc2.WorkingDirectory = $installDir
    $sc2.IconLocation = "$installedExe,0"
    $sc2.Description = "$AppName Desktop App"
    $sc2.Save()
    Write-Host "  Desktop shortcut: $desktopLnk"
}

Write-Host ""
Write-Host "Installed $AppName to: $installedExe" -ForegroundColor Green

if ($Launch) {
    Write-Host "Launching $AppName..."
    Start-Process -FilePath $installedExe -WorkingDirectory $installDir
}
