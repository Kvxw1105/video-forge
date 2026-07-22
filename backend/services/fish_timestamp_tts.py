"""Fish timestamp transport and SSE parsing."""
from __future__ import annotations
import base64
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
import httpx
from shared.structured_alignment import FishAlignmentSegment

FISH_TIMESTAMP_URL = "https://api.fish.audio/v1/tts/stream/with-timestamp"


class FishTimestampError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message); self.status_code = status_code


@dataclass(frozen=True)
class ParsedFishTimestamp:
    audio_bytes: bytes
    segments: tuple[FishAlignmentSegment, ...]
    alignment_by_chunk: dict[int, dict]
    duration: float


def _events(lines: Iterable[str | bytes]):
    data: list[str] = []
    for raw in lines:
        line = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else str(raw)
        line = line.rstrip("\r\n")
        if not line:
            if data:
                yield "\n".join(data); data = []
            continue
        if line.startswith(":"):
            continue
        if line.startswith("data:"):
            data.append(line[5:].lstrip())
    if data:
        yield "\n".join(data)


def parse_fish_timestamp_sse(lines_or_bytes: Iterable[str | bytes] | bytes) -> ParsedFishTimestamp:
    lines = lines_or_bytes.splitlines(keepends=True) if isinstance(lines_or_bytes, bytes) else lines_or_bytes
    audio_chunks: list[bytes] = []
    alignment_by_chunk: dict[int, dict] = {}
    segments_by_chunk: dict[int, list[FishAlignmentSegment]] = {}
    chunk_offsets: dict[int, float] = {}
    offset = 0.0
    for payload in _events(lines):
        try:
            event = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise FishTimestampError(f"invalid Fish SSE JSON: {exc}") from exc
        if not isinstance(event, dict):
            continue
        seq = int(event.get("chunk_seq", event.get("chunkSeq", len(audio_chunks))) or 0)
        chunk_offsets.setdefault(seq, offset)
        encoded = event.get("audio_base64") or event.get("audioBase64")
        if encoded:
            try: audio_chunks.append(base64.b64decode(encoded, validate=True))
            except Exception as exc: raise FishTimestampError("invalid audio_base64") from exc
        alignment = event.get("alignment")
        if alignment is not None:
            alignment_by_chunk[seq] = alignment
            chunk_segments: list[FishAlignmentSegment] = []
            for item in alignment.get("segments", []) if isinstance(alignment, dict) else []:
                start = float(item.get("start", 0) or 0); end = float(item.get("end", start) or start)
                content = str(item.get("text") or item.get("content") or "")
                chunk_segments.append(FishAlignmentSegment(content, chunk_offsets[seq] + start, chunk_offsets[seq] + end, seq, content))
            segments_by_chunk[seq] = chunk_segments
        chunk_duration = float(event.get("chunk_audio_duration", event.get("audio_duration", 0)) or 0)
        if chunk_duration > 0: offset += chunk_duration
    segments = [item for seq in sorted(segments_by_chunk) for item in segments_by_chunk[seq]]
    segments.sort(key=lambda item: (item.start, item.chunk_seq))
    duration = max(offset, max((s.end for s in segments), default=0.0))
    return ParsedFishTimestamp(b"".join(audio_chunks), tuple(segments), alignment_by_chunk, duration)


def request_fish_timestamp(text: str, api_key: str, reference_id: str, *, model: str = "s2-pro", fmt: str = "wav", latency: str = "normal", **options) -> ParsedFishTimestamp:
    if not api_key: raise FishTimestampError("Fish Audio API key is not configured")
    if not reference_id: raise FishTimestampError("Fish Audio reference ID is not configured")
    payload = {"text": text, "reference_id": reference_id, "model": model, "format": fmt, "latency": latency, "normalize": True, **options}
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json", "model": model}
    try:
        with httpx.Client(timeout=httpx.Timeout(120.0, connect=30.0)) as client:
            with client.stream("POST", FISH_TIMESTAMP_URL, json=payload, headers=headers) as response:
                if response.status_code != 200:
                    raise FishTimestampError(f"Fish Audio request failed: HTTP {response.status_code}", response.status_code)
                return parse_fish_timestamp_sse(response.iter_lines())
    except FishTimestampError: raise
    except httpx.HTTPError as exc: raise FishTimestampError(f"Fish Audio network error: {exc}") from exc
