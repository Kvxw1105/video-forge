"""Pure semantic visual scene planning and subtitle-timed lowering."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from copy import deepcopy


@dataclass(frozen=True)
class NarrationUnit:
    id: str
    subtitle_ids: tuple[str, ...]
    text: str
    start: float
    end: float


def build_narration_units(subtitles: list[dict]) -> list[NarrationUnit]:
    """Restore sentence-sized narration units without modifying subtitles."""
    ordered = sorted(subtitles, key=lambda item: (float(item.get("start", 0)), str(item.get("id", ""))))
    units, bucket = [], []
    for subtitle in ordered:
        bucket.append(subtitle)
        text = str(subtitle.get("text") or "")
        if re.search(r"[。！？；!?;]$", text.strip()) or "\n\n" in text:
            units.append(_unit(bucket, len(units) + 1)); bucket = []
    if bucket: units.append(_unit(bucket, len(units) + 1))
    return units


def _unit(items: list[dict], index: int) -> NarrationUnit:
    return NarrationUnit(f"unit_{index:03d}", tuple(str(item["id"]) for item in items), "".join(str(item.get("text") or "") for item in items), float(items[0].get("start", 0)), float(items[-1].get("end", 0)))


def visual_source_hash(project: dict) -> str:
    episode = ((project.get("structuredContent") or {}).get("episode") or {})
    blocks = episode.get("blocks") or []; bindings = {item.get("blockId"): item for item in episode.get("bindings") or []}
    subtitles = {item.get("id"): item for item in project.get("subtitles") or []}
    payload = {"episodeId": episode.get("episodeId"), "alignmentGenerationId": (episode.get("alignment") or {}).get("generationId"), "blocks": [{"id": block.get("id"), "revision": block.get("revision", 1)} for block in blocks], "bindings": [{"blockId": block.get("id"), "audioSlice": (bindings.get(block.get("id")) or {}).get("audioSlice"), "subtitles": [{"id": sid, "text": (subtitles.get(sid) or {}).get("text"), "start": (subtitles.get(sid) or {}).get("start"), "end": (subtitles.get(sid) or {}).get("end")} for sid in (bindings.get(block.get("id")) or {}).get("subtitleIds") or []] } for block in blocks]}
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def planning_context(project: dict) -> dict:
    episode = project["structuredContent"]["episode"]; subtitles = {item.get("id"): item for item in project.get("subtitles") or []}; bindings = {item.get("blockId"): item for item in episode.get("bindings") or []}
    blocks = []
    for block in episode.get("blocks") or []:
        binding = bindings.get(block["id"], {}); ids = binding.get("subtitleIds") or []
        selected = [subtitles[item] for item in ids if item in subtitles]
        units = build_narration_units(selected)
        slice_ = binding.get("audioSlice") or {}
        blocks.append({"blockId": block["id"], "blockType": block.get("type"), "text": block.get("text", ""), "sourceStart": slice_.get("sourceStart"), "sourceEnd": slice_.get("sourceEnd"), "narrationUnits": [{"id": unit.id, "subtitleIds": list(unit.subtitle_ids), "text": unit.text, "start": unit.start, "end": unit.end} for unit in units]})
    return {"projectId": project.get("id"), "episodeId": episode.get("episodeId"), "alignmentGenerationId": (episode.get("alignment") or {}).get("generationId"), "sourceHash": visual_source_hash(project), "blocks": blocks}


def propose_scenes(project: dict, settings: dict) -> list[dict]:
    context = planning_context(project); scenes = []; mode = settings.get("mode", "hybrid")
    for block in context["blocks"]:
        units = block["narrationUnits"]
        groups = _groups(units, settings, mode)
        for index, group in enumerate(groups, 1):
            scenes.append({"id": f"scene_{block['blockId']}_{index:03d}", "blockId": block["blockId"], "subtitleIds": [sid for unit in group for sid in unit["subtitleIds"]], "summary": "", "prompt": "", "negativePrompt": "", "requestedMediaType": "image", "visualAssetIds": [], "primaryAssetId": None, "durationPolicy": "fit_scene", "locked": False, "metadata": {}})
    return scenes


def _groups(units: list[dict], settings: dict, mode: str) -> list[list[dict]]:
    if not units: return []
    if mode == "fixed_units":
        step = max(1, int(settings.get("unitsPerScene", 3))); return [units[index:index + step] for index in range(0, len(units), step)]
    target = float(settings.get("targetDuration", 7)); minimum = float(settings.get("minDuration", 3)); maximum = float(settings.get("maxDuration", 12)); groups=[]; current=[]
    for unit in units:
        current.append(unit); duration = current[-1]["end"] - current[0]["start"]
        if duration >= target or (duration >= minimum and duration + (units[units.index(unit)+1]["end"] - unit["end"] if units.index(unit)+1 < len(units) else 0) > maximum): groups.append(current); current=[]
    if current: groups.append(current)
    return groups


def validate_plan(project: dict, plan: dict) -> list[str]:
    episode = project["structuredContent"]["episode"]; bindings = {item.get("blockId"): item for item in episode.get("bindings") or []}; subtitles = {item.get("id"): item for item in project.get("subtitles") or []}
    errors=[]; seen=set(); previous=(-1.0, "")
    for scene in plan.get("scenes") or []:
        binding = bindings.get(scene.get("blockId")); ids = scene.get("subtitleIds") or []
        if not binding: errors.append(f"scene {scene.get('id')} references unknown block"); continue
        expected = binding.get("subtitleIds") or []
        if any(item not in expected for item in ids): errors.append(f"scene {scene.get('id')} crosses block subtitle binding")
        positions=[expected.index(item) for item in ids if item in expected]
        if positions != list(range(min(positions), max(positions)+1)) if positions else True: errors.append(f"scene {scene.get('id')} subtitleIds are not continuous")
        if any(item in seen for item in ids): errors.append(f"scene {scene.get('id')} overlaps a prior scene")
        seen.update(ids)
        if ids and ids[0] in subtitles:
            key=(float(subtitles[ids[0]].get("start", 0)), scene.get("id", ""))
            if key < previous: errors.append("scene order must follow subtitle time")
            previous=key
    required={sid for binding in bindings.values() for sid in binding.get("subtitleIds") or [] if sid in subtitles}
    missing=required-seen
    if missing: errors.append(f"plan omits subtitles: {', '.join(sorted(missing))}")
    if plan.get("sourceHash") != visual_source_hash(project): errors.append("visual plan sourceHash is stale")
    return errors


def scene_timing(project: dict, scene: dict, block_target_start: float) -> dict:
    episode=project["structuredContent"]["episode"]; bindings={item.get("blockId"):item for item in episode.get("bindings") or []}; subtitles={item.get("id"):item for item in project.get("subtitles") or []}; binding=bindings[scene["blockId"]]; slice_=binding.get("audioSlice") or {}; ids=scene["subtitleIds"]
    start=float(subtitles[ids[0]]["start"]); end=float(subtitles[ids[-1]]["end"]); source_start=float(slice_.get("sourceStart", 0)); return {"sourceStart": start, "sourceEnd": end, "duration": end-start, "targetStart": block_target_start+start-source_start, "targetEnd": block_target_start+end-source_start}
