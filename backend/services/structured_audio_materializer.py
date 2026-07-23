"""Transactional materialization for Fish timestamp Structured Audio."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from shared.structured_alignment import align_episode_blocks, generate_subtitles_from_alignment
from shared.media_probe import probe_media_duration
from services.project_service import update_project

ALIGNMENT_ALGORITHM_VERSION = 1
SUBTITLE_ALGORITHM_VERSION = 1


def episode_text(project: dict, block_ids: list[str] | None = None) -> tuple[str, list[dict]]:
    episode = ((project.get("structuredContent") or {}).get("episode") or {})
    wanted = set(block_ids) if block_ids else None
    blocks = [block for block in episode.get("blocks", []) if block.get("enabled", True) and str(block.get("text") or "").strip() and (wanted is None or block.get("id") in wanted)]
    return "\n\n".join(str(block["text"]).strip() for block in blocks), blocks


def build_structured_audio_input_hash(project: dict, options: dict, blocks: list[dict]) -> str:
    episode = ((project.get("structuredContent") or {}).get("episode") or {})
    payload = {
        "schemaVersion": 1, "episodeId": episode.get("episodeId", ""),
        "blocks": [{"id": block.get("id"), "enabled": bool(block.get("enabled", True)), "text": str(block.get("text") or "")} for block in blocks],
        "blockIds": [block.get("id") for block in blocks],
        "referenceId": str(options.get("referenceId") or ""), "model": str(options.get("model") or "s2-pro"),
        "format": str(options.get("format") or "wav"), "latency": str(options.get("latency") or "normal"),
        "normalize": bool(options.get("normalize", True)), "chunkLength": int(options.get("chunkLength", 200)),
        "conditionOnPreviousChunks": bool(options.get("conditionOnPreviousChunks", True)),
        "temperature": float(options.get("temperature", 0.7)), "topP": float(options.get("topP", 0.7)),
        "speed": float(options.get("speed", 1.0)), "volume": float(options.get("volume", 0)),
        "generateSubtitles": bool(options.get("generateSubtitles", True)),
        "alignmentAlgorithmVersion": ALIGNMENT_ALGORITHM_VERSION, "subtitleAlgorithmVersion": SUBTITLE_ALGORITHM_VERSION,
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def has_structured_alignment(project: dict, episode_id: str | None = None) -> bool:
    episode = ((project.get("structuredContent") or {}).get("episode") or {})
    if episode_id and episode.get("episodeId") != episode_id:
        return False
    if episode.get("alignment"):
        return True
    # A binding is explicit episode-local evidence. An unrelated historical
    # Fish voiceover alone is deliberately not enough to lock this draft.
    if any(item.get("audioSlice") for item in episode.get("bindings") or []):
        return True
    return any((item.get("metadata") or {}).get("generatedBy") == "fish_timestamp_alignment" and (not episode_id or (item.get("metadata") or {}).get("episodeId") == episode_id) for item in project.get("subtitles") or [])


def validate_structured_audio_cache(project: dict, project_dir: Path, options: dict, blocks: list[dict]) -> tuple[bool, str, dict | None]:
    """Return a precise cache decision without making a network request."""
    episode = ((project.get("structuredContent") or {}).get("episode") or {})
    record = episode.get("alignment") or {}
    if not record:
        return False, "missing_alignment_record", None
    input_hash = build_structured_audio_input_hash(project, options, blocks)
    if record.get("inputHash") != input_hash:
        return False, "input_hash_mismatch", None
    manifest_path = project_dir / str(record.get("manifestPath") or "")
    audio_path = project_dir / str(record.get("audioPath") or "")
    if not manifest_path.is_file():
        return False, "manifest_missing", None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False, "manifest_invalid", None
    required = ("generationId", "voiceoverId", "inputHash", "audioFile", "blockRanges")
    if any(key not in manifest for key in required) or manifest.get("inputHash") != input_hash:
        return False, "manifest_invalid", None
    if manifest.get("generationId") != record.get("generationId") or manifest.get("voiceoverId") != record.get("voiceoverId"):
        return False, "manifest_invalid", None
    if not audio_path.is_file() or probe_media_duration(audio_path) <= 0:
        return False, "audio_missing", None
    voiceover_id = str(record.get("voiceoverId") or "")
    voices = ((project.get("audio") or {}).get("voiceovers") or [])
    if voiceover_id not in {item.get("id") for item in voices}:
        return False, "voiceover_missing", None
    requested = {str(block.get("id")) for block in blocks}
    manifest_ranges = {str(item.get("block_id")): item for item in manifest.get("blockRanges") or []}
    bindings = {str(item.get("blockId")): item for item in episode.get("bindings") or []}
    for block_id in requested:
        binding, item = bindings.get(block_id), manifest_ranges.get(block_id)
        slice_ = (binding or {}).get("audioSlice")
        if not binding or not item or not slice_ or slice_.get("voiceoverId") != voiceover_id:
            return False, "binding_mismatch", None
        if abs(float(slice_.get("sourceStart", -1)) - float(item.get("source_start", -2))) > 0.001 or abs(float(slice_.get("sourceEnd", -1)) - float(item.get("source_end", -2))) > 0.001:
            return False, "binding_mismatch", None
    if bool(options.get("generateSubtitles", True)) and manifest.get("segments"):
        subtitles = {item.get("id"): item for item in project.get("subtitles") or []}
        for block_id in requested:
            subtitle_ids = (bindings.get(block_id) or {}).get("subtitleIds") or []
            if not subtitle_ids or any(subtitle_id not in subtitles or (subtitles[subtitle_id].get("metadata") or {}).get("generationId") != record.get("generationId") for subtitle_id in subtitle_ids):
                return False, "subtitle_mismatch", None
    return True, "hit", manifest


def _atomic_write(path: Path, payload: bytes) -> None:
    temp = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temp.open("wb") as handle:
            handle.write(payload); handle.flush(); os.fsync(handle.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def materialize_structured_audio(project_id: str, project: dict, parsed, *, project_dir: Path, options: dict, block_ids: list[str] | None = None, confidence_block: float = 0.75, confidence_overall: float = 0.90):
    episode = ((project.get("structuredContent") or {}).get("episode") or {})
    text, blocks = episode_text(project, block_ids)
    if not parsed.audio_bytes:
        raise ValueError("Fish Audio returned no audio")
    generation_id = uuid4().hex
    input_hash = build_structured_audio_input_hash(project, options, blocks)
    duration = parsed.duration or 0.0
    alignment = align_episode_blocks(blocks, list(parsed.segments), duration)
    if alignment.overall_confidence < confidence_overall or any(item.confidence < confidence_block for item in alignment.blocks):
        raise ValueError("alignment_confidence_too_low")

    fish_root = project_dir / "structured" / "fish"
    staging = fish_root / f"{generation_id}.staging"
    final = fish_root / generation_id
    audio_name, manifest_name = "master_voice.wav", "alignment_manifest.json"
    try:
        staging.mkdir(parents=True)
        audio_file = staging / audio_name
        _atomic_write(audio_file, parsed.audio_bytes)
        probed_duration = probe_media_duration(audio_file)
        if probed_duration <= 0:
            raise ValueError("generated_wav_probe_failed")
        duration = probed_duration
        ranges = {item.block_id: (item.source_start, item.source_end) for item in alignment.blocks}
        subtitles = generate_subtitles_from_alignment(list(parsed.segments), generation_id, ranges) if bool(options.get("generateSubtitles", True)) else []
        for subtitle in subtitles:
            subtitle.setdefault("metadata", {}).update({"episodeId": episode.get("episodeId"), "generationId": generation_id})
        voiceover_id = f"structured_master_{generation_id[:12]}"
        manifest = {
            "schemaVersion": 1, "generationId": generation_id, "provider": "fish_audio", "endpoint": "tts_stream_with_timestamp",
            "episodeId": episode.get("episodeId"), "voiceoverId": voiceover_id, "inputHash": input_hash,
            "model": str(options.get("model") or "s2-pro"), "referenceId": str(options.get("referenceId") or ""), "format": "wav",
            "settings": {key: options.get(key, default) for key, default in {"latency":"normal","normalize":True,"chunkLength":200,"conditionOnPreviousChunks":True,"temperature":0.7,"topP":0.7,"speed":1.0,"volume":0}.items()},
            "blockOrder": [item.get("id") for item in blocks], "submittedText": text, "audioFile": audio_name,
            "audioDuration": duration, "chunks": [], "segments": [item.__dict__ for item in parsed.segments],
            "blockRanges": [item.__dict__ for item in alignment.blocks], "overallConfidence": alignment.overall_confidence,
            "warnings": list(alignment.warnings), "generatedAt": datetime.now().isoformat(),
        }
        _atomic_write(staging / manifest_name, json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8"))
        json.loads((staging / manifest_name).read_text(encoding="utf-8"))
        os.replace(staging, final)

        new_project = deepcopy(project)
        rel_audio = (Path("structured") / "fish" / generation_id / audio_name).as_posix()
        rel_manifest = (Path("structured") / "fish" / generation_id / manifest_name).as_posix()
        audio = new_project.setdefault("audio", {})
        voice = {"id": voiceover_id, "api": "fish_audio_timestamp", "engine": "fish_audio", "file": rel_audio, "duration": duration, "isActive": False, "createdAt": manifest["generatedAt"]}
        audio.setdefault("voiceovers", []).append(voice)
        old_subtitles = list(new_project.get("subtitles") or [])
        kept = [item for item in old_subtitles if not ((item.get("metadata") or {}).get("generatedBy") == "fish_timestamp_alignment" and (item.get("metadata") or {}).get("episodeId") == episode.get("episodeId"))]
        new_project["subtitles"] = kept + subtitles
        bindings = {item.get("blockId"): deepcopy(item) for item in episode.get("bindings") or []}
        for item in alignment.blocks:
            binding = bindings.get(item.block_id, {"blockId": item.block_id, "visualAssetIds": [], "subtitleIds": []})
            binding["audioSlice"] = {"voiceoverId": voiceover_id, "sourceStart": item.source_start, "sourceEnd": item.source_end}
            binding["subtitleIds"] = [sub["id"] for sub in subtitles if (sub.get("metadata") or {}).get("blockId") == item.block_id]
            bindings[item.block_id] = binding
        target_episode = new_project["structuredContent"]["episode"]
        target_episode["bindings"] = list(bindings.values())
        target_episode["alignment"] = {"schemaVersion": 1, "generationId": generation_id, "provider": "fish_audio", "endpoint": "tts_stream_with_timestamp", "voiceoverId": voiceover_id, "manifestPath": rel_manifest, "audioPath": rel_audio, "inputHash": input_hash, "blockIds": manifest["blockOrder"], "overallConfidence": alignment.overall_confidence, "model": manifest["model"], "referenceId": manifest["referenceId"], "generatedAt": manifest["generatedAt"]}
        try:
            update_project(project_id, new_project)
        except Exception:
            shutil.rmtree(final, ignore_errors=True)
            raise
        return {"generationId": generation_id, "voiceoverId": voiceover_id, "audioPath": rel_audio, "manifestPath": rel_manifest, "inputHash": input_hash, "audioDuration": duration, "blockCount": len(alignment.blocks), "subtitleCount": len(subtitles), "overallConfidence": alignment.overall_confidence, "blockRanges": manifest["blockRanges"], "warnings": manifest["warnings"]}
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        if final.exists():
            shutil.rmtree(final, ignore_errors=True)
        raise
