from __future__ import annotations
import json
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from uuid import uuid4
from shared.structured_alignment import align_episode_blocks, generate_subtitles_from_alignment
from shared.media_probe import probe_media_duration
from services.project_service import update_project


def episode_text(project: dict, block_ids: list[str] | None = None) -> tuple[str, list[dict]]:
    episode = ((project.get("structuredContent") or {}).get("episode") or {})
    wanted = set(block_ids) if block_ids else None
    blocks = [b for b in episode.get("blocks", []) if b.get("enabled", True) and str(b.get("text") or "").strip() and (wanted is None or b.get("id") in wanted)]
    return "\n\n".join(str(b["text"]).strip() for b in blocks), blocks


def materialize_structured_audio(project_id: str, project: dict, parsed, *, project_dir: Path, block_ids: list[str] | None = None, generate_subtitles: bool = True, confidence_block: float = 0.75, confidence_overall: float = 0.90):
    episode = ((project.get("structuredContent") or {}).get("episode") or {})
    text, blocks = episode_text(project, block_ids)
    generation_id = uuid4().hex
    duration = parsed.duration or probe_media_duration_from_bytes(parsed.audio_bytes)
    alignment = align_episode_blocks(blocks, list(parsed.segments), duration)
    if alignment.overall_confidence < confidence_overall or any(item.confidence < confidence_block for item in alignment.blocks):
        raise ValueError("alignment_confidence_too_low")
    if not parsed.audio_bytes:
        raise ValueError("Fish Audio returned no audio")
    audio_path = project_dir / f"structured_master_{generation_id}.wav"
    manifest_path = project_dir / f"structured_alignment_{generation_id}.json"
    audio_path.write_bytes(parsed.audio_bytes)
    ranges = {item.block_id: (item.source_start, item.source_end) for item in alignment.blocks}
    subtitles = generate_subtitles_from_alignment(list(parsed.segments), generation_id, ranges) if generate_subtitles else []
    for subtitle in subtitles:
        subtitle.setdefault("metadata", {})["episodeId"] = episode.get("episodeId")
    old_subtitles = list(project.get("subtitles") or [])
    old_auto = [s for s in old_subtitles if (s.get("metadata") or {}).get("generatedBy") == "fish_timestamp_alignment" and (s.get("metadata") or {}).get("episodeId") == episode.get("episodeId")]
    kept_subtitles = [s for s in old_subtitles if s not in old_auto]
    subtitle_index = {s["id"]: s for s in kept_subtitles}
    subtitle_index.update({s["id"]: s for s in subtitles})
    voiceover_id = f"structured_master_{generation_id[:12]}"
    new_project = deepcopy(project)
    audio = new_project.setdefault("audio", {})
    voice = {"id": voiceover_id, "api": "fish_audio_timestamp", "engine": "fish_audio", "file": str(audio_path), "duration": duration, "isActive": True, "createdAt": datetime.now().isoformat()}
    for item in audio.get("voiceovers") or []: item["isActive"] = False
    audio.setdefault("voiceovers", []).append(voice); audio["voiceover"] = voice
    new_project["subtitles"] = list(subtitle_index.values())
    bindings = {item.get("blockId"): item for item in episode.get("bindings", [])}
    for item in alignment.blocks:
        binding = deepcopy(bindings.get(item.block_id) or {"blockId": item.block_id, "visualAssetIds": [], "subtitleIds": []})
        binding["audioSlice"] = {"voiceoverId": voiceover_id, "sourceStart": item.source_start, "sourceEnd": item.source_end}
        binding["subtitleIds"] = [s["id"] for s in subtitles if (s.get("metadata") or {}).get("blockId") == item.block_id] + [sid for sid in binding.get("subtitleIds", []) if sid in subtitle_index and sid not in {s["id"] for s in subtitles}]
        bindings[item.block_id] = binding
    new_project["structuredContent"]["episode"]["bindings"] = list(bindings.values())
    manifest = {"generationId": generation_id, "voiceoverId": voiceover_id, "audioDuration": duration, "overallConfidence": alignment.overall_confidence, "blocks": [item.__dict__ for item in alignment.blocks], "segments": [item.__dict__ for item in parsed.segments], "alignmentByChunk": parsed.alignment_by_chunk, "warnings": list(alignment.warnings)}
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        update_project(project_id, new_project)
    except Exception:
        audio_path.unlink(missing_ok=True); manifest_path.unlink(missing_ok=True); raise
    return {"generationId": generation_id, "voiceoverId": voiceover_id, "audioPath": str(audio_path), "manifestPath": str(manifest_path), "audioDuration": duration, "blockCount": len(alignment.blocks), "subtitleCount": len(subtitles), "overallConfidence": alignment.overall_confidence, "blockRanges": [item.__dict__ for item in alignment.blocks], "warnings": list(alignment.warnings)}


def probe_media_duration_from_bytes(data: bytes) -> float:
    # Fish supplies alignment duration; this fallback intentionally avoids guessing.
    return 0.0
