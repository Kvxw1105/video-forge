param(
  [Parameter(Mandatory = $true)][string]$BackupPath,
  [switch]$ConfirmRestore
)
$ErrorActionPreference = 'Stop'

if (-not $ConfirmRestore) { throw 'Restoring data is destructive. Re-run with -ConfirmRestore.' }
if (-not (Test-Path $BackupPath)) { throw "Backup not found: $BackupPath" }

$dataRoot = if ($env:VIDEOFORGE_DATA_DIR) { $env:VIDEOFORGE_DATA_DIR } else { Join-Path $env:LOCALAPPDATA 'VideoForge' }
$safetyBackup = Join-Path (Split-Path -Parent ([System.IO.Path]::GetFullPath($BackupPath))) ("VideoForge-before-restore-" + (Get-Date -Format yyyyMMdd-HHmmss) + '.zip')
& (Join-Path $PSScriptRoot 'backup-data.ps1') -OutputPath $safetyBackup
Expand-Archive -LiteralPath $BackupPath -DestinationPath $dataRoot -Force
Write-Output "Data restored to: $dataRoot"
Write-Output "Safety backup: $safetyBackup"
