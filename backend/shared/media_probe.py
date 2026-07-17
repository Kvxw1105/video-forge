"""Shared ffprobe boundary for canonical media duration resolution."""
from __future__ import annotations

import json
import math
from pathlib import Path

from process_utils import run as run_process


def probe_media_duration(path: str | Path) -> float:
    """Return one finite positive media duration, or 0.0 when probing fails."""
    try:
        result = run_process(
            [
                "ffprobe", "-v", "quiet", "-print_format", "json",
                "-show_format", "-show_streams", str(path),
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return 0.0
        payload = json.loads(result.stdout)
        format_duration = _valid_duration((payload.get("format") or {}).get("duration"))
        if format_duration > 0:
            return format_duration
        stream_durations = [
            _valid_duration(stream.get("duration"))
            for stream in payload.get("streams") or []
        ]
        return max(stream_durations, default=0.0)
    except Exception:
        return 0.0


def _valid_duration(value) -> float:
    try:
        duration = float(value)
    except (TypeError, ValueError):
        return 0.0
    return duration if math.isfinite(duration) and duration > 0 else 0.0
