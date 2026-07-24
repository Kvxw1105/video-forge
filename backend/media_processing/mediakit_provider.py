from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .contracts import MediaCapability, MediaExecutionRequest
from .provider import MediaProcessingError


CAPABILITIES = {
    "media.probe": MediaCapability(name="media.probe", providerCommand=["video", "probe-video-metadata"], local=True, asyncCapable=True, outputType="metadata"),
    "video.trim": MediaCapability(name="video.trim", providerCommand=["editing", "trim-video"], local=True, asyncCapable=True, outputType="video"),
    "audio.extract": MediaCapability(name="audio.extract", providerCommand=["editing", "extract-audio"], local=True, asyncCapable=True, outputType="audio"),
}


MediaKitError = MediaProcessingError


class MediaKitProvider:
    provider_id = "mediakit"

    def __init__(
        self,
        executable: str | list[str] | None = None,
        *,
        ffprobe: str = "ffprobe",
        ffmpeg_dir: str | Path | None = None,
    ):
        configured = executable or os.environ.get("VIDEOFORGE_MEDIAKIT_CLI") or shutil.which("mediakit-cli")
        self.command = [configured] if isinstance(configured, str) else list(configured or [])
        configured_ffmpeg_dir = ffmpeg_dir or os.environ.get("VIDEOFORGE_MEDIAKIT_FFMPEG_DIR")
        self.ffmpeg_dir = Path(configured_ffmpeg_dir).resolve() if configured_ffmpeg_dir else None
        self.ffprobe = str(self.ffmpeg_dir / "ffprobe.exe") if self.ffmpeg_dir else ffprobe

    def discover(self) -> dict[str, Any]:
        found = bool(self.command and Path(self.command[0]).exists() or (self.command and shutil.which(self.command[0])))
        capabilities = []
        for item in CAPABILITIES.values():
            schema = self._schema(item.providerCommand) if found else {}
            capabilities.append(item.model_copy(update={"schema_": schema}).model_dump(mode="json", by_alias=True))
        return {"provider": self.provider_id, "installed": found, "executable": self.command[0] if self.command else None, "capabilities": capabilities}

    def execute(self, request: MediaExecutionRequest, source: Path, output: Path | None = None) -> dict[str, Any]:
        if request.capability not in CAPABILITIES:
            raise MediaKitError("capability is not implemented by MediaKit", details={"capability": request.capability})
        if not source.exists() or not source.is_file():
            raise MediaKitError("source media file does not exist", details={"sourcePath": str(source)})
        if not self.command:
            raise MediaKitError("MediaKit CLI is not installed", details={"code": "mediakit_not_installed"}, retryable=False)
        capability = CAPABILITIES[request.capability]
        args = [*self.command, "--local", *capability.providerCommand, "--video-url", str(source)]
        if request.capability == "video.trim":
            args += ["--start-time", str(request.startTime), "--end-time", str(request.endTime)]
        if request.capability == "audio.extract":
            args += ["--format", "mp3"]
        if output is not None:
            output.parent.mkdir(parents=True, exist_ok=True)
            args += ["--output-path", str(output)]
        completed = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180, check=False, env=self._environment())
        payload = self._json_output(completed.stdout)
        if completed.returncode != 0:
            raise MediaKitError("MediaKit CLI execution failed", details={"returncode": completed.returncode, "stdout": completed.stdout[-4000:], "stderr": completed.stderr[-4000:], "result": payload}, retryable=False)
        if isinstance(payload.get("error"), dict) or payload.get("error"):
            raise MediaKitError("MediaKit CLI returned an error", details={"result": payload}, retryable=False)
        return payload

    def verify_media(self, path: Path) -> dict[str, Any]:
        if not path.exists() or path.stat().st_size == 0:
            raise MediaKitError("MediaKit reported an output that does not exist", details={"outputPath": str(path)})
        result = subprocess.run([self.ffprobe, "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30, check=False, env=self._environment())
        if result.returncode:
            raise MediaKitError("ffprobe rejected MediaKit output", details={"outputPath": str(path), "stderr": result.stderr[-4000:]})
        return json.loads(result.stdout)

    def _schema(self, command: list[str]) -> dict[str, Any]:
        result = subprocess.run([*self.command, "--local", *command, "--schema"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30, check=False, env=self._environment())
        return self._json_output(result.stdout) if result.returncode == 0 else {}

    def _environment(self) -> dict[str, str]:
        environment = os.environ.copy()
        if self.ffmpeg_dir:
            environment["PATH"] = str(self.ffmpeg_dir) + os.pathsep + environment.get("PATH", "")
        return environment

    @staticmethod
    def _json_output(stdout: str) -> dict[str, Any]:
        start, end = stdout.find("{"), stdout.rfind("}")
        if start < 0 or end < start:
            return {}
        try:
            value = json.loads(stdout[start:end + 1])
        except json.JSONDecodeError:
            return {}
        return value if isinstance(value, dict) else {}
