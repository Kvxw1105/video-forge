"""Pure Fish timestamp alignment helpers. No network or project I/O."""
from __future__ import annotations

import difflib
import re
import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True)
class FishAlignmentSegment:
    text: str
    start: float
    end: float
    chunk_seq: int = 0
    content: str = ""


@dataclass(frozen=True)
class BlockAlignment:
    block_id: str
    source_start: float
    source_end: float
    confidence: float
    expected_units: int
    matched_units: int
    first_segment: int | None
    last_segment: int | None


@dataclass(frozen=True)
class StructuredAlignment:
    blocks: tuple[BlockAlignment, ...]
    overall_confidence: float
    audio_duration: float
    warnings: tuple[str, ...]


def normalize_alignment_text(value: str) -> str:
    value = unicodedata.normalize("NFKC", str(value or "")).lower()
    return re.sub(r"[^\w\u3400-\u9fff]", "", value, flags=re.UNICODE)


def align_episode_blocks(blocks: list[dict], segments: list[FishAlignmentSegment], audio_duration: float) -> StructuredAlignment:
    enabled = [b for b in blocks if b.get("enabled", True) and str(b.get("text") or "").strip()]
    expected = [normalize_alignment_text(b.get("text", "")) for b in enabled]
    observed = [normalize_alignment_text(s.text) for s in segments]
    expected_text = "".join(expected)
    observed_text = "".join(observed)
    warnings: list[str] = []
    if not expected_text or not observed_text:
        return StructuredAlignment(tuple(BlockAlignment(str(b.get("id")), 0.0, 0.0, 0.0, len(e), 0, None, None) for b, e in zip(enabled, expected)), 0.0, audio_duration, ("alignment text is empty",))
    # Match normalized character units while retaining observed segment indices.
    obs_units: list[tuple[str, int]] = [(char, i) for i, text in enumerate(observed) for char in text]
    matcher = difflib.SequenceMatcher(None, list(expected_text), [u[0] for u in obs_units], autojunk=False)
    matched_obs: dict[int, int] = {}
    for block in matcher.get_matching_blocks():
        for offset in range(block.size):
            matched_obs[block.a + offset] = obs_units[block.b + offset][1]
    results: list[BlockAlignment] = []
    expected_cursor = 0
    for source_index, (block, normalized) in enumerate(zip(enabled, expected)):
        length = len(normalized)
        indexes = [matched_obs[i] for i in range(expected_cursor, expected_cursor + length) if i in matched_obs]
        expected_cursor += length
        if indexes:
            first_idx, last_idx = min(indexes), max(indexes)
            start = segments[first_idx].start
            end = segments[last_idx].end
            if source_index == 0:
                start = 0.0
            if source_index == len(enabled) - 1:
                end = max(end, audio_duration)
            if source_index and results:
                boundary = (results[-1].source_end + start) / 2.0
                previous = results[-1]
                results[-1] = BlockAlignment(previous.block_id, previous.source_start, boundary, previous.confidence, previous.expected_units, previous.matched_units, previous.first_segment, previous.last_segment)
                start = boundary
            confidence = len(indexes) / max(1, length)
            results.append(BlockAlignment(str(block.get("id")), start, max(start, end), confidence, length, len(indexes), first_idx, last_idx))
        else:
            results.append(BlockAlignment(str(block.get("id")), 0.0, 0.0, 0.0, length, 0, None, None))
            warnings.append(f"block {block.get('id')} could not be aligned")
    total_expected = sum(item.expected_units for item in results)
    overall = sum(item.matched_units for item in results) / max(1, total_expected)
    return StructuredAlignment(tuple(results), overall, max(0.0, audio_duration), tuple(warnings))


def generate_subtitles_from_alignment(segments: list[FishAlignmentSegment], generation_id: str, block_ranges: dict[str, tuple[float, float]]) -> list[dict]:
    subtitles: list[dict] = []
    counters: dict[str, int] = {}
    for segment in segments:
        block_id = next((bid for bid, (start, end) in block_ranges.items() if segment.end > start and segment.start < end), None)
        if not block_id:
            continue
        text = str(segment.content or segment.text).strip()
        if not text:
            continue
        counters[block_id] = counters.get(block_id, 0) + 1
        subtitles.append({
            "id": f"fish__{generation_id}__{block_id}__{counters[block_id]:03d}",
            "text": text,
            "start": max(0.0, segment.start),
            "end": max(segment.start, segment.end),
            "style": {"fontSize": 36, "color": "#ffffff", "strokeColor": "#000000", "strokeWidth": 2, "position": "bottom_center"},
            "metadata": {"generatedBy": "fish_timestamp_alignment", "generationId": generation_id, "blockId": block_id},
        })
    return subtitles
