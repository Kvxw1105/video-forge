"""Deterministic compiler for long-form compositions built from Episode variants."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Callable, Any

from models.project import Project
from shared.structured_content import compile_structured_media_variant


@dataclass(frozen=True)
class CompiledCompositionItem:
    item_id: str
    source_project_id: str
    variant_id: str
    start: float
    end: float
    duration: float
    chapter_card_duration: float
    gap_after: float
    block_count: int
    voiceover_clip_count: int
    visual_clip_count: int
    subtitle_count: int


@dataclass(frozen=True)
class CompiledStructuredComposition:
    composition_id: str
    title: str
    items: tuple[CompiledCompositionItem, ...]
    total_duration: float
    project_view: dict[str, Any]
    warnings: tuple[str, ...]


def compile_structured_composition(
    composition_project: Project | dict,
    load_source_project: Callable[[str], Project | dict | None],
    resolve_source_paths: Callable[[Any, dict], dict] | None = None,
    duration_resolver=None,
) -> CompiledStructuredComposition:
    raw = composition_project.model_dump(mode="python") if isinstance(composition_project, Project) else deepcopy(composition_project)
    composition = raw.get("composition")
    if not isinstance(composition, dict):
        raise ValueError("project does not contain composition")
    warnings: list[str] = []
    out_segments: list[dict] = []
    out_subtitles: list[dict] = []
    out_voice_segments: list[dict] = []
    out_assets: list[dict] = []
    seen_assets: set[tuple[str, str]] = set()
    compiled_items: list[CompiledCompositionItem] = []
    cursor = 0.0
    scripts: list[str] = []
    canvas = raw.get("canvas") or {}

    for item in composition.get("items") or []:
        if not item.get("enabled", True):
            continue
        item_id = str(item.get("id"))
        source_id = str(item.get("sourceProjectId"))
        variant_id = str(item.get("variantId"))
        source = load_source_project(source_id)
        if source is None:
            raise ValueError(f"source project not found: {source_id}")
        source_dict = source.model_dump(mode="python") if isinstance(source, Project) else deepcopy(source)
        if not source_dict.get("structuredContent"):
            raise ValueError(f"source project is not structured: {source_id}")
        if resolve_source_paths is not None:
            source_dict = resolve_source_paths(source_id, source_dict)
        compiled = compile_structured_media_variant(source_dict, variant_id, duration_resolver=duration_resolver)
        source_canvas = source_dict.get("canvas") or {}
        if (source_canvas.get("width"), source_canvas.get("height")) != (canvas.get("width"), canvas.get("height")):
            warnings.append(f"canvas differs for composition item {item_id}; composition canvas is used")

        card_duration = float(item.get("chapterCardDuration", 0) or 0)
        gap_after = float(item.get("gapAfter", 0) or 0)
        item_start = cursor
        if item.get("chapterTitle") and card_duration > 0:
            out_segments.append({"id": f"{item_id}__chapter_card", "assetPath": "", "type": "black", "start": cursor, "end": cursor + card_duration, "bgColor": "#000000"})
            out_subtitles.append({"id": f"{item_id}__chapter_title", "text": str(item["chapterTitle"]), "start": cursor, "end": cursor + card_duration, "style": {"fontSize": 64, "color": "#ffffff", "strokeColor": "#000000", "strokeWidth": 2, "position": "middle_center"}, "metadata": {"generatedBy": "structured_composition", "compositionItemId": item_id}})
            cursor += card_duration
        content_start = cursor
        for index, segment in enumerate(compiled.project_view.get("segments") or []):
            shifted = deepcopy(segment)
            shifted["id"] = f"{item_id}__{segment.get('id', f'visual_{index:03d}') }"
            shifted["start"] = float(segment.get("start", 0) or 0) + content_start
            shifted["end"] = float(segment.get("end", 0) or 0) + content_start
            out_segments.append(shifted)
        for index, segment in enumerate(compiled.project_view.get("audio", {}).get("voiceoverSegments") or []):
            shifted = deepcopy(segment)
            shifted["id"] = f"{item_id}__{segment.get('id', f'voice_{index:03d}') }"
            shifted["startAt"] = float(segment.get("startAt", 0) or 0) + content_start
            out_voice_segments.append(shifted)
        for index, subtitle in enumerate(compiled.project_view.get("subtitles") or []):
            shifted = deepcopy(subtitle)
            shifted["id"] = f"{item_id}__{subtitle.get('id', f'subtitle_{index:03d}') }"
            shifted["start"] = float(subtitle.get("start", 0) or 0) + content_start
            shifted["end"] = float(subtitle.get("end", 0) or 0) + content_start
            shifted.setdefault("metadata", {})["compositionItemId"] = item_id
            out_subtitles.append(shifted)
        source_assets = {str(asset.get("id")): asset for asset in source_dict.get("assets") or []}
        for asset in source_assets.values():
            key = (source_id, str(asset.get("id")))
            if key not in seen_assets:
                seen_assets.add(key)
                out_assets.append(deepcopy(asset))
        scripts.append(compiled.project_view.get("script", ""))
        content_duration = float(compiled.total_duration)
        cursor = content_start + content_duration
        if gap_after > 0:
            out_segments.append({"id": f"{item_id}__gap", "assetPath": "", "type": "black", "start": cursor, "end": cursor + gap_after, "bgColor": "#000000"})
            cursor += gap_after
        compiled_items.append(CompiledCompositionItem(item_id, source_id, variant_id, item_start, cursor, cursor - item_start, card_duration, gap_after, len(compiled.block_windows), len(compiled.project_view.get("audio", {}).get("voiceoverSegments") or []), len(compiled.project_view.get("segments") or []), len(compiled.project_view.get("subtitles") or [])))

    view = deepcopy(raw)
    view["name"] = f"{raw.get('name', 'Composition')} [composition]"
    view["segments"] = out_segments
    view["subtitles"] = out_subtitles
    view["assets"] = out_assets
    view["script"] = "\n\n".join(item for item in scripts if item)
    view["audio"] = {**(raw.get("audio") or {}), "voiceover": {}, "voiceovers": [], "voiceoverSegments": out_voice_segments}
    view["timeline"] = {"voiceoverStartAt": 0.0, "blocks": []}
    view["composition"] = composition
    return CompiledStructuredComposition(str(composition.get("compositionId")), str(composition.get("title") or raw.get("name", "")), tuple(compiled_items), round(cursor, 6), view, tuple(dict.fromkeys(warnings)))
