param(
  [string]$PortableRoot = (Join-Path (Resolve-Path (Join-Path $PSScriptRoot '..')).Path 'release\VideoForge-Windows-Portable'),
  [int]$Port = 8765
)
$ErrorActionPreference = 'Stop'

$exe = Join-Path $PortableRoot 'VideoForge.exe'
if (-not (Test-Path $exe)) { throw "Portable executable not found: $exe" }
$process = Start-Process -FilePath $exe -WorkingDirectory $PortableRoot -PassThru
try {
  $health = $null
  for ($i = 0; $i -lt 60; $i++) {
    Start-Sleep -Milliseconds 500
    try { $health = Invoke-RestMethod "http://127.0.0.1:$Port/api/health" -TimeoutSec 2; break } catch {}
  }
  if (-not $health) { throw 'Portable backend did not become ready within 30 seconds' }
  $projects = Invoke-RestMethod "http://127.0.0.1:$Port/api/projects"
  $readiness = Invoke-RestMethod "http://127.0.0.1:$Port/api/system/readiness"
  [pscustomobject]@{
    health = $health.status
    projects = $true
    readiness = $readiness.status
    portableRoot = $PortableRoot
  } | ConvertTo-Json -Compress
} finally {
  if (-not $process.HasExited) { Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue }
  Start-Sleep -Seconds 2
}
