$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectRoot

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw "Python was not found in PATH."
}

$appInfoJson = python -c "import json; from desktop_agent.version import APP_NAME, APP_PUBLISHER, APP_VERSION, checksums_file_name, installer_file_name, portable_zip_file_name, release_dir_name, release_manifest_file_name, review_zip_file_name, source_zip_file_name; print(json.dumps({'name': APP_NAME, 'publisher': APP_PUBLISHER, 'version': APP_VERSION, 'release_dir_name': release_dir_name(), 'installer_file_name': installer_file_name(), 'portable_zip_file_name': portable_zip_file_name(), 'review_zip_file_name': review_zip_file_name(), 'source_zip_file_name': source_zip_file_name(), 'release_manifest_file_name': release_manifest_file_name(), 'checksums_file_name': checksums_file_name()}))"
if (-not $appInfoJson) {
    throw "Could not read version metadata from desktop_agent.version."
}

$app = $appInfoJson | ConvertFrom-Json
$releaseRoot = Join-Path $projectRoot "release"
$releaseDir = Join-Path $releaseRoot $app.release_dir_name
$installerScript = Join-Path $projectRoot "installer\\Aoryn.iss"
$distDir = Join-Path $projectRoot ("dist\\{0}" -f $app.name)
$installerPath = Join-Path $releaseRoot $app.installer_file_name
$portableZipPath = Join-Path $releaseRoot $app.portable_zip_file_name
$reviewZipPath = Join-Path $releaseRoot $app.review_zip_file_name
$sourceZipPath = Join-Path $releaseRoot $app.source_zip_file_name
$manifestPath = Join-Path $releaseRoot $app.release_manifest_file_name
$checksumsPath = Join-Path $releaseRoot $app.checksums_file_name

if (-not (Test-Path $installerScript)) {
    throw "Inno Setup script not found: $installerScript"
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
Remove-Item $installerPath -Force -ErrorAction SilentlyContinue
Remove-Item $portableZipPath -Force -ErrorAction SilentlyContinue
Remove-Item $reviewZipPath -Force -ErrorAction SilentlyContinue
Remove-Item $sourceZipPath -Force -ErrorAction SilentlyContinue
Remove-Item $manifestPath -Force -ErrorAction SilentlyContinue
Remove-Item $checksumsPath -Force -ErrorAction SilentlyContinue

powershell -ExecutionPolicy Bypass -File .\build_windows_exe.ps1

if (-not (Test-Path $distDir)) {
    throw "Expected PyInstaller output was not found: $distDir"
}

New-Item -ItemType Directory -Path $releaseRoot -Force | Out-Null
Copy-Item -Path $distDir -Destination $releaseDir -Recurse -Force

& $iscc.Source `
  "/DAppName=$($app.name)" `
  "/DAppPublisher=$($app.publisher)" `
  "/DAppVersion=$($app.version)" `
  "/DAppExeName=$($app.name).exe" `
  "/DReleaseSourceDir=$releaseDir" `
  "/DReleaseOutputDir=$releaseRoot" `
  $installerScript

$bundleInfoJson = python .\scripts\create_release_bundle.py `
  --project-root $projectRoot `
  --release-root $releaseRoot `
  --release-dir $releaseDir `
  --installer-path $installerPath
if (-not $bundleInfoJson) {
    throw "Could not build release bundle artifacts."
}

$bundle = $bundleInfoJson | ConvertFrom-Json

Write-Host ""
Write-Host "Release complete:" -ForegroundColor Green
Write-Host "  $releaseDir" -ForegroundColor Cyan
Write-Host ("  {0}" -f $installerPath) -ForegroundColor Cyan
Write-Host ("  {0}" -f $bundle.portable_zip) -ForegroundColor Cyan
Write-Host ("  {0}" -f $bundle.source_zip) -ForegroundColor Cyan
Write-Host ("  {0}" -f $bundle.review_zip) -ForegroundColor Cyan
Write-Host ("  {0}" -f $bundle.manifest) -ForegroundColor Cyan
Write-Host ("  {0}" -f $bundle.checksums) -ForegroundColor Cyan
