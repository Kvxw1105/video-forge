$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$releaseRoot = Join-Path $projectRoot 'release'
$portableRoot = Join-Path $releaseRoot 'VideoForge-Windows-Portable'
$builtRoot = Join-Path $releaseRoot 'VideoForge'
$workRoot = Join-Path $projectRoot 'build\portable'

& (Join-Path $projectRoot 'scripts\build-frontend.ps1')
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

if (-not (Get-Command pyinstaller -ErrorAction SilentlyContinue)) {
  throw "PyInstaller is required. Install it with: python -m pip install pyinstaller"
}

Remove-Item $portableRoot -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item $builtRoot -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item $workRoot -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $releaseRoot, $workRoot | Out-Null

pyinstaller (Join-Path $projectRoot 'packaging\VideoForge.spec') --noconfirm --clean --distpath $releaseRoot --workpath $workRoot
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

if (-not (Test-Path (Join-Path $builtRoot 'VideoForge.exe'))) {
  throw "PyInstaller output was not found at $builtRoot"
}
Move-Item $builtRoot $portableRoot

$dataRoot = Join-Path $portableRoot 'data'
New-Item -ItemType Directory -Force -Path (Join-Path $dataRoot 'projects'), (Join-Path $dataRoot 'library'), (Join-Path $dataRoot 'logs'), (Join-Path $dataRoot 'config'), (Join-Path $dataRoot 'temp') | Out-Null
$launcherBat = @(
  '@echo off'
  'setlocal'
  '"%~dp0VideoForge.exe"'
  'if errorlevel 1 pause'
)
$launcherBat | Set-Content -Path (Join-Path $portableRoot 'Start VideoForge.bat') -Encoding ASCII
$readme = @(
  'VideoForge Windows Portable Alpha'
  ''
  'Double-click VideoForge.exe or Start VideoForge.bat.'
  'Runtime data is stored in the data folder.'
  'Logs: data\logs\launcher.log'
)
$readme | Set-Content -Path (Join-Path $portableRoot 'README.txt') -Encoding UTF8

$zip = Join-Path $releaseRoot 'VideoForge-Windows-Portable.zip'
Remove-Item $zip -Force -ErrorAction SilentlyContinue
Compress-Archive -Path (Join-Path $portableRoot '*') -DestinationPath $zip -CompressionLevel Optimal
Write-Output "Portable release ready: $portableRoot"
Write-Output "ZIP: $zip"
