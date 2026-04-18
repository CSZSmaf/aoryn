$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectRoot

$appInfo = python -c "import json; from desktop_agent.version import APP_BROWSER_NAME, APP_NAME, APP_VERSION; print(json.dumps({'name': APP_NAME, 'browser_name': APP_BROWSER_NAME, 'version': APP_VERSION}))"
if (-not $appInfo) {
    throw "Could not read application metadata."
}
$app = $appInfo | ConvertFrom-Json

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw "Python was not found in PATH."
}

python -m pip show pyinstaller *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Host "PyInstaller is not installed yet." -ForegroundColor Yellow
    Write-Host "Install it with:" -ForegroundColor Yellow
    Write-Host "  python -m pip install --user -r requirements-build.txt" -ForegroundColor Cyan
    exit 1
}

python -m PyInstaller --noconfirm --clean .\Aoryn.spec
python -m PyInstaller --noconfirm --clean .\AorynBrowser.spec

Write-Host ""
Write-Host "Build complete:" -ForegroundColor Green
Write-Host ("  .\dist\{0}\{0}.exe" -f $app.name) -ForegroundColor Cyan
Write-Host ("  .\dist\{0}.exe" -f $app.browser_name) -ForegroundColor Cyan
Write-Host ("Version: {0}" -f $app.version) -ForegroundColor DarkGray
