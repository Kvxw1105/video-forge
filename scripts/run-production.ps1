$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
python (Join-Path $projectRoot 'backend/launcher.py') @args
exit $LASTEXITCODE
