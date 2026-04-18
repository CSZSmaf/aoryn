$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectRoot

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw "Python was not found in PATH."
}

$appInfoJson = python -c "import json; from desktop_agent.version import APP_BROWSER_DISPLAY_NAME, APP_BROWSER_NAME, APP_NAME, APP_PUBLISHER, APP_VERSION, browser_executable_name, browser_installer_file_name, browser_portable_zip_file_name, browser_release_dir_name, checksums_file_name, installer_file_name, portable_zip_file_name, release_dir_name, release_manifest_file_name, review_zip_file_name, source_zip_file_name; print(json.dumps({'name': APP_NAME, 'browser_name': APP_BROWSER_NAME, 'browser_display_name': APP_BROWSER_DISPLAY_NAME, 'publisher': APP_PUBLISHER, 'version': APP_VERSION, 'release_dir_name': release_dir_name(), 'browser_release_dir_name': browser_release_dir_name(), 'browser_executable_name': browser_executable_name(), 'installer_file_name': installer_file_name(), 'browser_installer_file_name': browser_installer_file_name(), 'portable_zip_file_name': portable_zip_file_name(), 'browser_portable_zip_file_name': browser_portable_zip_file_name(), 'review_zip_file_name': review_zip_file_name(), 'source_zip_file_name': source_zip_file_name(), 'release_manifest_file_name': release_manifest_file_name(), 'checksums_file_name': checksums_file_name()}))"
if (-not $appInfoJson) {
    throw "Could not read version metadata from desktop_agent.version."
}

$app = $appInfoJson | ConvertFrom-Json
$releaseRoot = Join-Path $projectRoot "release"
$releaseDir = Join-Path $releaseRoot $app.release_dir_name
$browserReleaseDir = Join-Path $releaseRoot $app.browser_release_dir_name
$installerScript = Join-Path $projectRoot "installer\\Aoryn.iss"
$browserInstallerScript = Join-Path $projectRoot "installer\\AorynBrowser.iss"
$distDir = Join-Path $projectRoot ("dist\\{0}" -f $app.name)
$browserExePath = Join-Path $projectRoot ("dist\\{0}" -f $app.browser_executable_name)
$installerPath = Join-Path $releaseRoot $app.installer_file_name
$browserInstallerPath = Join-Path $releaseRoot $app.browser_installer_file_name
$portableZipPath = Join-Path $releaseRoot $app.portable_zip_file_name
$browserPortableZipPath = Join-Path $releaseRoot $app.browser_portable_zip_file_name
$reviewZipPath = Join-Path $releaseRoot $app.review_zip_file_name
$sourceZipPath = Join-Path $releaseRoot $app.source_zip_file_name
$manifestPath = Join-Path $releaseRoot $app.release_manifest_file_name
$checksumsPath = Join-Path $releaseRoot $app.checksums_file_name

if (-not (Test-Path $installerScript)) {
    throw "Inno Setup script not found: $installerScript"
}
if (-not (Test-Path $browserInstallerScript)) {
    throw "Browser Inno Setup script not found: $browserInstallerScript"
}

$iscc = Get-Command iscc.exe -ErrorAction SilentlyContinue
if (-not $iscc) {
    $commonIsccPaths = @(
        (Join-Path $env:LOCALAPPDATA "Programs\\Inno Setup 6\\ISCC.exe"),
        "C:\\Program Files (x86)\\Inno Setup 6\\ISCC.exe",
        "C:\\Program Files\\Inno Setup 6\\ISCC.exe"
    )
    $resolvedIscc = $commonIsccPaths | Where-Object { Test-Path $_ } | Select-Object -First 1
    if ($resolvedIscc) {
        $iscc = @{ Source = $resolvedIscc }
    }
}
if (-not $iscc) {
    throw "Inno Setup compiler (iscc.exe) is not installed. Install Inno Setup first, then rerun build_release.ps1."
}

Get-ChildItem -Path $releaseRoot -ErrorAction SilentlyContinue | Out-Null
Remove-Item $releaseDir -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item $browserReleaseDir -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item $installerPath -Force -ErrorAction SilentlyContinue
Remove-Item $browserInstallerPath -Force -ErrorAction SilentlyContinue
Remove-Item $portableZipPath -Force -ErrorAction SilentlyContinue
Remove-Item $browserPortableZipPath -Force -ErrorAction SilentlyContinue
Remove-Item $reviewZipPath -Force -ErrorAction SilentlyContinue
Remove-Item $sourceZipPath -Force -ErrorAction SilentlyContinue
Remove-Item $manifestPath -Force -ErrorAction SilentlyContinue
Remove-Item $checksumsPath -Force -ErrorAction SilentlyContinue

powershell -ExecutionPolicy Bypass -File .\build_windows_exe.ps1

if (-not (Test-Path $distDir)) {
    throw "Expected PyInstaller output was not found: $distDir"
}
if (-not (Test-Path $browserExePath)) {
    throw "Expected browser executable output was not found: $browserExePath"
}

New-Item -ItemType Directory -Path $releaseRoot -Force | Out-Null
Copy-Item -Path $distDir -Destination $releaseDir -Recurse -Force
New-Item -ItemType Directory -Path $browserReleaseDir -Force | Out-Null
Copy-Item -Path $browserExePath -Destination (Join-Path $browserReleaseDir $app.browser_executable_name) -Force

& $iscc.Source `
  "/DAppName=$($app.name)" `
  "/DAppPublisher=$($app.publisher)" `
  "/DAppVersion=$($app.version)" `
  "/DAppExeName=$($app.name).exe" `
  "/DReleaseSourceDir=$releaseDir" `
  "/DReleaseOutputDir=$releaseRoot" `
  $installerScript

& $iscc.Source `
  "/DProductName=$($app.browser_display_name)" `
  "/DAppPublisher=$($app.publisher)" `
  "/DAppVersion=$($app.version)" `
  "/DAppExeName=$($app.browser_executable_name)" `
  "/DInstallDirName=$($app.browser_display_name)" `
  "/DOutputBaseName=$([System.IO.Path]::GetFileNameWithoutExtension($app.browser_installer_file_name))" `
  "/DReleaseSourceDir=$browserReleaseDir" `
  "/DReleaseOutputDir=$releaseRoot" `
  $browserInstallerScript

$bundleInfoJson = python .\scripts\create_release_bundle.py `
  --project-root $projectRoot `
  --release-root $releaseRoot `
  --release-dir $releaseDir `
  --browser-release-dir $browserReleaseDir `
  --installer-path $installerPath `
  --browser-installer-path $browserInstallerPath
if (-not $bundleInfoJson) {
    throw "Could not build release bundle artifacts."
}

$bundle = $bundleInfoJson | ConvertFrom-Json

Write-Host ""
Write-Host "Release complete:" -ForegroundColor Green
Write-Host "  $releaseDir" -ForegroundColor Cyan
Write-Host "  $browserReleaseDir" -ForegroundColor Cyan
Write-Host ("  {0}" -f $installerPath) -ForegroundColor Cyan
Write-Host ("  {0}" -f $browserInstallerPath) -ForegroundColor Cyan
Write-Host ("  {0}" -f $bundle.portable_zip) -ForegroundColor Cyan
Write-Host ("  {0}" -f $bundle.browser_portable_zip) -ForegroundColor Cyan
Write-Host ("  {0}" -f $bundle.source_zip) -ForegroundColor Cyan
Write-Host ("  {0}" -f $bundle.review_zip) -ForegroundColor Cyan
Write-Host ("  {0}" -f $bundle.manifest) -ForegroundColor Cyan
Write-Host ("  {0}" -f $bundle.checksums) -ForegroundColor Cyan
