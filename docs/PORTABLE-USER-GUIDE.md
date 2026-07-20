# VideoForge Portable User Guide

## Start

Unzip the release package to any writable folder and double-click `VideoForge.exe`.
The launcher starts the local FastAPI service, selects an available port, and opens the browser.

Runtime data is kept outside the executable under `%LOCALAPPDATA%\VideoForge` unless
`VIDEOFORGE_DATA_DIR` is set. The data directory contains projects, library assets,
configuration, temporary files, and logs.

## Optional Components

- FFmpeg is required for MP4 preview rendering. Install it separately and put `ffmpeg` on `PATH`.
- JianYing is required only for direct draft export. ZIP draft export does not require the client.
- Edge TTS works without a provider key. Fish Audio, Manbo, and custom APIs require their own credentials.

Missing optional components should leave the editor usable. Check `/api/system/readiness` when diagnosing a machine.

## Backup and Restore

Run the scripts from the repository checkout, not from inside the compressed executable bundle:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\backup-data.ps1
powershell -ExecutionPolicy Bypass -File scripts\restore-data.ps1 -BackupPath .\VideoForge-Data-20260721.zip -ConfirmRestore
```

The restore command creates a safety backup before replacing data. Stop VideoForge before restoring.

## Support Checklist

1. Confirm `http://127.0.0.1:8765/api/health` returns `{"status":"ok"}`.
2. Confirm `/api/system/readiness` reports which optional component is unavailable.
3. Check `%LOCALAPPDATA%\VideoForge\logs\launcher.log` for the full startup or render error.
4. Reproduce with a short script and one local image before retrying a long project.
