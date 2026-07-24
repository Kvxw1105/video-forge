from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from fractions import Fraction
from pathlib import Path
from typing import Any

from .contracts import MediaCapability, MediaExecutionRequest
from .provider import MediaProcessingError


CAPABILITIES = {
    "media.probe": MediaCapability(
        name="media.probe",
        local=True,
        asyncCapable=False,
        outputType="metadata",
        schema={"type": "object", "required": ["sourceAssetId"], "properties": {"sourceAssetId": {"type": "string"}}},
    ),
    "video.trim": MediaCapability(
        name="video.trim",
        local=True,
        asyncCapable=False,
        outputType="video",
        schema={"type": "object", "required": ["sourceAssetId", "startTime", "endTime"], "properties": {"sourceAssetId": {"type": "string"}, "startTime": {"type": "number", "minimum": 0}, "endTime": {"type": "number", "exclusiveMinimum": 0}}},
    ),
    "audio.extract": MediaCapability(
        name="audio.extract",
        local=True,
        asyncCapable=False,
        outputType="audio",
        schema={"type": "object", "required": ["sourceAssetId"], "properties": {"sourceAssetId": {"type": "string"}, "format": {"const": "mp3"}}},
    ),
}


class VideoForgeNativeMediaProvider:
    provider_id = "videoforge_native"

    def __init__(self, *, ffmpeg_dir: str | Path | None = None):
        configured = ffmpeg_dir or os.environ.get("VIDEOFORGE_MEDIA_FFMPEG_DIR") or os.environ.get("VIDEOFORGE_MEDIAKIT_FFMPEG_DIR")
        self.ffmpeg_dir = Path(configured).resolve() if configured else None
        self.ffmpeg = str(self.ffmpeg_dir / "ffmpeg.exe") if self.ffmpeg_dir else (shutil.which("ffmpeg") or "ffmpeg")
        self.ffprobe = str(self.ffmpeg_dir / "ffprobe.exe") if self.ffmpeg_dir else (shutil.which("ffprobe") or "ffprobe")

    def discover(self) -> dict[str, Any]:
        ffmpeg_available = self._available(self.ffmpeg)
        ffprobe_available = self._available(self.ffprobe)
        return {
            "provider": self.provider_id,
            "installed": ffmpeg_available and ffprobe_available,
            "dependencies": {
                "ffmpeg": {"available": ffmpeg_available, "path": self.ffmpeg, "version": self._version(self.ffmpeg)},
                "ffprobe": {"available": ffprobe_available, "path": self.ffprobe, "version": self._version(self.ffprobe)},
            },
            "capabilities": [item.model_dump(mode="json", by_alias=True) for item in CAPABILITIES.values()],
        }

    def execute(self, request: MediaExecutionRequest, source: Path, output: Path | None = None) -> dict[str, Any]:
        if request.capability not in CAPABILITIES:
            raise MediaProcessingError("capability is not implemented by VideoForge", details={"capability": request.capability})
        self._validate_local_file(source, "source")
        if request.capability == "media.probe":
            return self._normalized_probe(source)
        if output is None:
            raise MediaProcessingError("derived media capability requires an output path")
        self._validate_path(output, "output")
        output.parent.mkdir(parents=True, exist_ok=True)
        if request.capability == "video.trim":
            args = ["-y", "-hide_banner", "-ss", str(request.startTime), "-to", str(request.endTime), "-i", str(source), "-map", "0:v:0", "-map", "0:a:0?", "-c", "copy", str(output)]
        else:
            args = ["-y", "-hide_banner", "-i", str(source), "-map", "0:a:0", "-c:a", "libmp3lame", str(output)]
        self._run(self.ffmpeg, args, timeout=180)
        probe = self.verify_media(output)
        duration = _float((probe.get("format") or {}).get("duration"))
        if request.capability == "video.trim":
            return {"video_url": str(output), "duration": duration, "resolution": _resolution(probe)}
        return {"audio_url": str(output), "duration": duration, "format": "mp3"}

    def verify_media(self, path: Path) -> dict[str, Any]:
        self._validate_local_file(path, "output")
        return self._probe(path)

    def _normalized_probe(self, path: Path) -> dict[str, Any]:
        raw = self._probe(path)
        fmt = raw.get("format") or {}
        streams = raw.get("streams") or []
        video = next((item for item in streams if item.get("codec_type") == "video"), {})
        audio = next((item for item in streams if item.get("codec_type") == "audio"), {})
        result: dict[str, Any] = {
            "format_meta": {
                "container": fmt.get("format_name"),
                "bitrate": _int(fmt.get("bit_rate")),
                "duration": _float(fmt.get("duration")),
                "size": _int(fmt.get("size")),
                "sha256": _sha256(path),
            },
            "video_stream_meta": {
                "codec": video.get("codec_name"),
                "bitrate": _int(video.get("bit_rate")),
                "duration": _float(video.get("duration")),
                "fps": _fps(video.get("avg_frame_rate") or video.get("r_frame_rate")),
                "width": _int(video.get("width")),
                "height": _int(video.get("height")),
                "dynamic_range": _dynamic_range(video),
            },
        }
        if audio:
            result["audio_stream_meta"] = {
                "codec": audio.get("codec_name"),
                "bitrate": _int(audio.get("bit_rate")),
                "duration": _float(audio.get("duration")),
                "sample_rate": _int(audio.get("sample_rate")),
                "channels": _int(audio.get("channels")),
            }
        return result

    def _probe(self, path: Path) -> dict[str, Any]:
        completed = self._run(self.ffprobe, ["-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)], timeout=30)
        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise MediaProcessingError("ffprobe returned invalid JSON", details={"stdout": completed.stdout[-4000:]}) from exc
        if not payload.get("streams"):
            raise MediaProcessingError("ffprobe found no media streams", details={"path": str(path)})
        return payload

    def _run(self, executable: str, args: list[str], *, timeout: int) -> subprocess.CompletedProcess[str]:
        try:
            completed = subprocess.run([executable, *args], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, check=False, env=self._environment())
        except subprocess.TimeoutExpired as exc:
            raise MediaProcessingError("native media command timed out", details={"executable": Path(executable).name, "timeout": timeout}, retryable=True) from exc
        except OSError as exc:
            raise MediaProcessingError("native media dependency is unavailable", details={"executable": executable, "error": str(exc)}) from exc
        if completed.returncode:
            raise MediaProcessingError("native media command failed", details={"executable": Path(executable).name, "returncode": completed.returncode, "stderr": completed.stderr[-4000:]})
        return completed

    def _environment(self) -> dict[str, str]:
        environment = os.environ.copy()
        if self.ffmpeg_dir:
            environment["PATH"] = str(self.ffmpeg_dir) + os.pathsep + environment.get("PATH", "")
        return environment

    @staticmethod
    def _validate_path(path: Path, field: str) -> None:
        if any(ord(char) < 32 or char in "\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069" for char in str(path)):
            raise MediaProcessingError(f"{field} path contains unsupported control characters")

    @classmethod
    def _validate_local_file(cls, path: Path, field: str) -> None:
        cls._validate_path(path, field)
        if not path.exists() or not path.is_file() or path.stat().st_size == 0:
            raise MediaProcessingError(f"{field} media file does not exist", details={"path": str(path)})

    @staticmethod
    def _available(executable: str) -> bool:
        return Path(executable).is_file() or bool(shutil.which(executable))

    def _version(self, executable: str) -> str | None:
        if not self._available(executable):
            return None
        try:
            result = subprocess.run([executable, "-version"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10, check=False, env=self._environment())
        except OSError:
            return None
        return result.stdout.splitlines()[0].strip() if result.returncode == 0 and result.stdout else None


def _float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _fps(value: Any) -> float | None:
    try:
        return round(float(Fraction(str(value))), 6)
    except (ValueError, ZeroDivisionError):
        return None


def _dynamic_range(stream: dict[str, Any]) -> str | None:
    values = " ".join(str(stream.get(key) or "") for key in ("color_transfer", "color_primaries", "color_space")).lower()
    if any(item in values for item in ("smpte2084", "arib-std-b67", "bt2020")):
        return "HDR"
    return "SDR" if values.strip() else None


def _resolution(probe: dict[str, Any]) -> str | None:
    stream = next((item for item in probe.get("streams") or [] if item.get("codec_type") == "video"), None)
    height = _int((stream or {}).get("height"))
    if not height:
        return None
    for limit, label in ((240, "240p"), (360, "360p"), (480, "480p"), (720, "720p"), (1080, "1080p"), (1440, "2k")):
        if height <= limit:
            return label
    return "4k"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
