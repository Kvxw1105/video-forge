param(
  [string]$OutputPath = "$(Get-Location)\VideoForge-Data-$(Get-Date -Format yyyyMMdd-HHmmss).zip"
)
$ErrorActionPreference = 'Stop'

$dataRoot = if ($env:VIDEOFORGE_DATA_DIR) { $env:VIDEOFORGE_DATA_DIR } else { Join-Path $env:LOCALAPPDATA 'VideoForge' }
if (-not (Test-Path $dataRoot)) { throw "VideoForge data directory not found: $dataRoot" }

$staging = Join-Path ([System.IO.Path]::GetTempPath()) ("videoforge-backup-" + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Force -Path $staging | Out-Null
try {
  foreach ($name in @('projects', 'library', 'config', 'tts_settings.json')) {
    $source = Join-Path $dataRoot $name
    if (Test-Path $source) {
      Copy-Item -LiteralPath $source -Destination $staging -Recurse -Force
    }
  }
  $parent = Split-Path -Parent ([System.IO.Path]::GetFullPath($OutputPath))
  New-Item -ItemType Directory -Force -Path $parent | Out-Null
  Remove-Item -LiteralPath $OutputPath -Force -ErrorAction SilentlyContinue
  Compress-Archive -Path (Join-Path $staging '*') -DestinationPath $OutputPath -CompressionLevel Optimal
  Write-Output "Backup created: $OutputPath"
} finally {
  Remove-Item -LiteralPath $staging -Recurse -Force -ErrorAction SilentlyContinue
}
