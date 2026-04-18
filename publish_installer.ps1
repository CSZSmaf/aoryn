param(
    [switch]$SkipBuild,
    [switch]$SkipPagesSync,
    [string]$ProxyUrl
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectRoot

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw "Python was not found in PATH."
}

$hasBoto3 = $false
python -c "import importlib.util, sys; sys.exit(0 if importlib.util.find_spec('boto3') else 1)"
if ($LASTEXITCODE -eq 0) {
    $hasBoto3 = $true
}
if (-not $hasBoto3) {
    throw "boto3 is not installed. Run `python -m pip install --user -r requirements-build.txt` first."
}

if (-not $SkipBuild) {
    powershell -ExecutionPolicy Bypass -File .\build_release.ps1
}

$appInfoJson = python -c "import json; from desktop_agent.version import browser_installer_file_name, installer_file_name; print(json.dumps({'installer_file_name': installer_file_name(), 'browser_installer_file_name': browser_installer_file_name()}))"
if (-not $appInfoJson) {
    throw "Could not read installer metadata."
}

$app = $appInfoJson | ConvertFrom-Json
$installerPath = Join-Path $projectRoot ("release\\{0}" -f $app.installer_file_name)
$browserInstallerPath = Join-Path $projectRoot ("release\\{0}" -f $app.browser_installer_file_name)
if (-not (Test-Path $installerPath)) {
    throw "Installer not found: $installerPath"
}
if (-not (Test-Path $browserInstallerPath)) {
    throw "Browser installer not found: $browserInstallerPath"
}

$desktopPublishArgs = @(
    ".\scripts\publish_installer.py",
    "--installer-path",
    $installerPath
)

if ($ProxyUrl) {
    $desktopPublishArgs += "--proxy"
    $desktopPublishArgs += $ProxyUrl
}

if (-not $SkipPagesSync -and $env:AORYN_CF_API_TOKEN) {
    $desktopPublishArgs += "--sync-pages-download-settings"
}

python @desktopPublishArgs

$browserPublishArgs = @(
    ".\scripts\publish_installer.py",
    "--installer-path",
    $browserInstallerPath,
    "--latest-key",
    "latest/AorynBrowser-Setup-latest.exe",
    "--pages-key-env",
    "AORYN_WINDOWS_BROWSER_INSTALLER_KEY",
    "--pages-url-env",
    "AORYN_WINDOWS_BROWSER_INSTALLER_URL"
)

if (-not $SkipPagesSync -and $env:AORYN_CF_API_TOKEN) {
    $browserPublishArgs += "--sync-pages-download-settings"
    $browserPublishArgs += "--retry-pages-deployment"
}

if ($ProxyUrl) {
    $browserPublishArgs += "--proxy"
    $browserPublishArgs += $ProxyUrl
}

python @browserPublishArgs
