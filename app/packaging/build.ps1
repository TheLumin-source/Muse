# Build Muse for distribution.
#
#   1. Freezes the app with PyInstaller  -> app\dist\Muse\Muse.exe
#   2. Wraps it into an installer with Inno Setup -> out\Muse Setup.exe
#
# Run from anywhere:  powershell -ExecutionPolicy Bypass -File app\packaging\build.ps1
#
# Before a release: bump __version__ in muse\__init__.py. That single number
# flows into the installer and is what the auto-updater compares against.

$ErrorActionPreference = 'Stop'
# Paths come from where this script lives, so the repo builds on any machine.
# MUSE_BUILD_PYTHON overrides the interpreter.
$app  = Split-Path $PSScriptRoot -Parent
$root = Split-Path $app -Parent
$py = $env:MUSE_BUILD_PYTHON
if (-not $py) {
  $py = (Get-ChildItem "$env:LOCALAPPDATA\Programs\Python\Python3*\python.exe" -ErrorAction SilentlyContinue |
         Sort-Object FullName -Descending | Select-Object -First 1).FullName
}
if (-not $py) { $py = (Get-Command python.exe -ErrorAction SilentlyContinue).Source }
if (-not $py) { throw 'No Python found. Set MUSE_BUILD_PYTHON.' }
Set-Location $app

# One source of truth for the version: muse\__init__.py
$initText = Get-Content "$app\muse\__init__.py" -Raw
if ($initText -notmatch '__version__\s*=\s*"([^"]+)"') { throw 'Could not read __version__ from muse\__init__.py' }
$version = $Matches[1]
Write-Host "Building Muse $version" -ForegroundColor Cyan

Write-Host '== 1/2  PyInstaller ==' -ForegroundColor Cyan
Remove-Item -Recurse -Force "$app\build","$app\dist" -ErrorAction SilentlyContinue
& $py -m PyInstaller muse.spec --noconfirm --log-level WARN
if (-not (Test-Path "$app\dist\Muse\Muse.exe")) { throw 'PyInstaller build failed - no exe produced.' }
Write-Host "   built dist\Muse\Muse.exe" -ForegroundColor Green

Write-Host '== 2/2  Inno Setup ==' -ForegroundColor Cyan
$iscc = @(
  "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
  "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
  "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1

if ($iscc) {
  New-Item -ItemType Directory -Force (Join-Path $root 'out') | Out-Null
  & $iscc "/DMyAppVersion=$version" "$app\packaging\muse.iss"
  Write-Host "`nDone. Installer: out\Muse Setup.exe (v$version)" -ForegroundColor Green
  Write-Host "Upload that to your shop, and update latest.json to version $version." -ForegroundColor Green
} else {
  Write-Host "`nInno Setup not found." -ForegroundColor Yellow
  Write-Host "Install it once from https://jrsoftware.org/isdl.php (free), then re-run this script."
  Write-Host "The frozen app is ready at dist\Muse - the installer step just wraps it."
}
