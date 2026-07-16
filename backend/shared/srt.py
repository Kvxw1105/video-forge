from __future__ import annotations

import re
from typing import Any


_TIMECODE_RE = re.compile(
    r"^(\d{1,}):(\d{2}):(\d{2})[,.](\d{1,3})\s*-->\s*"
    r"(\d{1,}):(\d{2}):(\d{2})[,.](\d{1,3})(?:\s+.*)?$"
)


def decode_srt(content: bytes) -> str:
    """Decode common SRT encodings used by Chinese Windows editors."""
    for encoding in ("utf-8-sig", "gb18030"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("SRT 文件编码无法识别，请使用 UTF-8 或 GB18030")


def parse_srt(content: str) -> tuple[list[dict[str, Any]], int]:
    """Parse valid SRT blocks and report how many malformed blocks were ignored."""
    normalized = content.replace("\r\n", "\n").replace("\r", "\n").strip()
    blocks = re.split(r"\n[ \t]*\n", normalized) if normalized else []
    subtitles: list[dict[str, Any]] = []
    ignored = 0

    for block in blocks:
        lines = block.split("\n")
        time_index = next(
            (index for index, line in enumerate(lines) if _TIMECODE_RE.match(line.strip())),
            None,
        )
        if time_index is None:
            ignored += 1
            continue

        match = _TIMECODE_RE.match(lines[time_index].strip())
        text = "\n".join(lines[time_index + 1 :]).strip()
        if match is None or not text:
            ignored += 1
            continue

        values = match.groups()
        start = _timecode_seconds(*values[:4])
        end = _timecode_seconds(*values[4:])
        if end <= start:
            ignored += 1
            continue

        subtitles.append(
            {
                "id": f"sub_{len(subtitles) + 1:03d}",
                "text": text,
                "start": round(start, 3),
                "end": round(end, 3),
            }
        )

    if not subtitles:
        raise ValueError("SRT 文件中没有识别到有效字幕")
    return subtitles, ignored


def subtitles_to_transcript(subtitles: list[dict[str, Any]]) -> str:
    lines = []
    for subtitle in subtitles:
        text = re.sub(r"[ \t]*\n[ \t]*", " ", str(subtitle.get("text", ""))).strip()
        if text:
            lines.append(text)
    return "\n".join(lines)


def serialize_srt(subtitles: list[dict[str, Any]]) -> str:
    blocks = []
    for subtitle in subtitles:
        text = str(subtitle.get("text", "")).replace("\r\n", "\n").replace("\r", "\n").strip()
        if not text:
            continue
        index = len(blocks) + 1
        blocks.append(
            "\r\n".join(
                (
                    str(index),
                    f"{_format_time(float(subtitle.get('start', 0)))} --> "
                    f"{_format_time(float(subtitle.get('end', 0)))}",
                    text.replace("\n", "\r\n"),
                )
            )
        )
    return "\r\n\r\n".join(blocks) + ("\r\n" if blocks else "")


def _timecode_seconds(hours: str, minutes: str, seconds: str, millis: str) -> float:
    milliseconds = int(millis.ljust(3, "0")[:3])
    return int(hours) * 3600 + int(minutes) * 60 + int(seconds) + milliseconds / 1000


def _format_time(seconds: float) -> str:
    total_ms = max(0, round(seconds * 1000))
    hours, remainder = divmod(total_ms, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"
