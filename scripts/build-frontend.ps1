$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$frontend = Join-Path $projectRoot 'frontend'
if (-not (Test-Path (Join-Path $frontend 'node_modules'))) {
    throw "frontend/node_modules is missing. Run 'npm install' or 'npm ci' in frontend first."
}
Push-Location $frontend
try {
    npm run build
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
} finally {
    Pop-Location
}
$index = Join-Path $frontend 'dist/index.html'
if (-not (Test-Path $index)) { throw "Frontend build did not produce $index" }
$assets = Join-Path $frontend 'dist/assets'
if (-not (Test-Path $assets -PathType Container) -or -not (Get-ChildItem $assets -File | Select-Object -First 1)) { throw "Frontend build did not produce assets in $assets" }
Write-Output "Frontend production build ready: $index"
