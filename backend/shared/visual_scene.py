"""Pure semantic visual scene planning and subtitle-timed lowering."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from copy import deepcopy
from typing import Any, Mapping, Protocol


_MEDIA_TYPES = frozenset({"image", "video", "either", "black", "color", "text_card"})
_SCENE_POLICIES = frozenset({"single_clip", "fixed_units", "split_by_semantic_cluster", "one_scene_per_step", "auto"})
_STYLE_MEDIA_TYPES = {
    "black_screen_text": "text_card",
    "color_card": "color",
    "cinematic_images": "image",
    "diagram_or_steps": "image",
    "mixed": "either",
}


class VisualSceneProposalProvider(Protocol):
    """Optional future AI seam.

    Providers may enrich a deterministic scene proposal with visual language
    (summary, prompts, and asset preference). They do not receive or emit
    ``start`` / ``end`` fields: subtitle alignment stays time authority.
    """

    name: str

    def enrich(self, context: Mapping[str, Any], scenes: list[dict[str, Any]]) -> list[dict[str, Any]]: ...


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
    payload = {"episodeId": episode.get("episodeId"), "alignmentGenerationId": (episode.get("alignment") or {}).get("generationId"), "profile": _profile_snapshot(project), "blocks": [{"id": block.get("id"), "revision": block.get("revision", 1), "visualPolicy": (block.get("metadata") or {}).get("visualPolicy")} for block in blocks], "bindings": [{"blockId": block.get("id"), "audioSlice": (bindings.get(block.get("id")) or {}).get("audioSlice"), "subtitles": [{"id": sid, "text": (subtitles.get(sid) or {}).get("text"), "start": (subtitles.get(sid) or {}).get("start"), "end": (subtitles.get(sid) or {}).get("end")} for sid in (bindings.get(block.get("id")) or {}).get("subtitleIds") or []] } for block in blocks]}
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def planning_context(project: dict) -> dict:
    episode = project["structuredContent"]["episode"]; subtitles = {item.get("id"): item for item in project.get("subtitles") or []}; bindings = {item.get("blockId"): item for item in episode.get("bindings") or []}
    blocks = []
    for block in episode.get("blocks") or []:
        binding = bindings.get(block["id"], {}); ids = binding.get("subtitleIds") or []
        selected = [subtitles[item] for item in ids if item in subtitles]
        units = build_narration_units(selected)
        slice_ = binding.get("audioSlice") or {}
        blocks.append({"blockId": block["id"], "blockType": block.get("type"), "text": block.get("text", ""), "sourceStart": slice_.get("sourceStart"), "sourceEnd": slice_.get("sourceEnd"), "visualPolicy": resolve_block_visual_policy(project, block), "narrationUnits": [{"id": unit.id, "subtitleIds": list(unit.subtitle_ids), "text": unit.text, "start": unit.start, "end": unit.end} for unit in units]})
    return {"projectId": project.get("id"), "episodeId": episode.get("episodeId"), "alignmentGenerationId": (episode.get("alignment") or {}).get("generationId"), "sourceHash": visual_source_hash(project), "blocks": blocks}


def propose_scenes(project: dict, settings: dict) -> list[dict]:
    context = planning_context(project); scenes = []; mode = settings.get("mode", "hybrid")
    for block in context["blocks"]:
        units = block["narrationUnits"]
        policy = block["visualPolicy"]
        groups = _groups(units, settings, mode, policy)
        for index, group in enumerate(groups, 1):
            scenes.append({"id": f"scene_{block['blockId']}_{index:03d}", "blockId": block["blockId"], "subtitleIds": [sid for unit in group for sid in unit["subtitleIds"]], "summary": "", "prompt": "", "negativePrompt": "", "requestedMediaType": policy["mediaType"], "visualAssetIds": [], "primaryAssetId": None, "durationPolicy": "fit_scene", "locked": False, "metadata": {"visualPolicy": policy}})
    return scenes


def _groups(units: list[dict], settings: dict, mode: str, policy: Mapping[str, Any] | None = None) -> list[list[dict]]:
    if not units: return []
    scene_policy = str((policy or {}).get("scenePolicy") or "auto")
    if scene_policy == "single_clip": return [units]
    if scene_policy == "one_scene_per_step": return [[unit] for unit in units]
    if scene_policy == "fixed_units" or (scene_policy == "auto" and mode == "fixed_units"):
        step = max(1, int((policy or {}).get("unitsPerScene") or settings.get("unitsPerScene", 3))); return [units[index:index + step] for index in range(0, len(units), step)]
    if scene_policy == "split_by_semantic_cluster": mode = "hybrid"
    target = float(settings.get("targetDuration", 7)); minimum = float(settings.get("minDuration", 3)); maximum = float(settings.get("maxDuration", 12)); groups=[]; current=[]
    for index, unit in enumerate(units):
        current.append(unit); duration = current[-1]["end"] - current[0]["start"]
        if duration >= target or (duration >= minimum and duration + (units[index + 1]["end"] - unit["end"] if index + 1 < len(units) else 0) > maximum): groups.append(current); current=[]
    if current: groups.append(current)
    return groups


def _profile_snapshot(project: Mapping[str, Any]) -> dict[str, Any] | None:
    """Use the immutable project snapshot first, then legacy episode metadata."""
    snapshot = project.get("structureProfileSnapshot")
    if isinstance(snapshot, Mapping): return deepcopy(dict(snapshot))
    episode = ((project.get("structuredContent") or {}).get("episode") or {})
    snapshot = ((episode.get("metadata") or {}).get("scriptStructuring") or {}).get("profileSnapshot")
    return deepcopy(dict(snapshot)) if isinstance(snapshot, Mapping) else None


def resolve_block_visual_policy(project: Mapping[str, Any], block: Mapping[str, Any]) -> dict[str, Any]:
    """Resolve a block visual policy without introducing any timing values."""
    raw: Mapping[str, Any] | None = None
    override = (block.get("metadata") or {}).get("visualPolicy")
    if isinstance(override, Mapping): raw = override
    if raw is None:
        profile = (_profile_snapshot(project) or {}).get("profile")
        rules = profile.get("blocks") if isinstance(profile, Mapping) else None
        if isinstance(rules, list):
            raw = next((item.get("visualPolicy") for item in rules if isinstance(item, Mapping) and item.get("type") == block.get("type") and isinstance(item.get("visualPolicy"), Mapping)), None)
    # Preserve the pre-profile proposal contract for old projects: it produced
    # image scenes. A profile's explicit ``mixed`` default may still opt into
    # the broader ``either`` intent.
    if raw is None:
        return {"style": "mixed", "scenePolicy": "auto", "mediaType": "image", "unitsPerScene": None, "notes": ""}
    style = str(raw.get("style") or "mixed")
    requested = str(raw.get("mediaType") or "auto")
    media_type = _STYLE_MEDIA_TYPES.get(style, "either") if requested == "auto" else requested
    if media_type not in _MEDIA_TYPES: media_type = "either"
    scene_policy = str(raw.get("scenePolicy") or "auto")
    if scene_policy not in _SCENE_POLICIES: scene_policy = "auto"
    units = raw.get("unitsPerScene")
    return {"style": style, "scenePolicy": scene_policy, "mediaType": media_type, "unitsPerScene": units if isinstance(units, int) and units > 0 else None, "notes": str(raw.get("notes") or "")}


def validate_plan(project: dict, plan: dict) -> list[str]:
    episode = project["structuredContent"]["episode"]; bindings = {item.get("blockId"): item for item in episode.get("bindings") or []}; subtitles = {item.get("id"): item for item in project.get("subtitles") or []}
    errors=[]; seen=set(); previous=(-1.0, "")
    for scene in plan.get("scenes") or []:
        binding = bindings.get(scene.get("blockId")); ids = scene.get("subtitleIds") or []
        if not binding: errors.append(f"scene {scene.get('id')} references unknown block"); continue
        expected = binding.get("subtitleIds") or []
        if any(item not in subtitles for item in ids): errors.append(f"scene {scene.get('id')} references unknown subtitle")
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
    current_alignment = (episode.get("alignment") or {}).get("generationId")
    declared_alignment = plan.get("alignmentGenerationId")
    if declared_alignment is not None and declared_alignment != current_alignment: errors.append("visual plan alignmentGenerationId is stale")
    return errors


def scene_timing(project: dict, scene: dict, block_target_start: float) -> dict:
    episode=project["structuredContent"]["episode"]; bindings={item.get("blockId"):item for item in episode.get("bindings") or []}; subtitles={item.get("id"):item for item in project.get("subtitles") or []}; binding=bindings[scene["blockId"]]; slice_=binding.get("audioSlice") or {}; ids=scene["subtitleIds"]
    start=float(subtitles[ids[0]]["start"]); end=float(subtitles[ids[-1]]["end"]); source_start=float(slice_.get("sourceStart", 0)); return {"sourceStart": start, "sourceEnd": end, "duration": end-start, "targetStart": block_target_start+start-source_start, "targetEnd": block_target_start+end-source_start}
