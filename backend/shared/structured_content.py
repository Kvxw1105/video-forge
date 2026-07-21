"""Pure compilation of structured Episode variants into a legacy project view."""

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from models.project import Project
from shared.media_probe import probe_media_duration


@dataclass(frozen=True)
class CompiledStructuredBlock:
    id: str
    type: str
    text: str
    revision: int


@dataclass(frozen=True)
class CompiledStructuredVariant:
    episode_id: str
    variant_id: str
    variant_name: str
    blocks: tuple[CompiledStructuredBlock, ...]
    block_ids: tuple[str, ...]
    script: str
    warnings: tuple[str, ...]
    project_view: dict[str, Any]


@dataclass(frozen=True)
class CompiledBlockWindow:
    block_id: str
    block_type: str
    start: float
    end: float
    duration: float
    audio_source_start: float | None
    audio_source_end: float | None
    visual_count: int
    subtitle_count: int


@dataclass(frozen=True)
class CompiledStructuredMediaVariant:
    episode_id: str
    variant_id: str
    variant_name: str
    block_windows: tuple[CompiledBlockWindow, ...]
    total_duration: float
    project_view: dict[str, Any]
    warnings: tuple[str, ...]


def compile_structured_variant(project: Project | dict, variant_id: str) -> CompiledStructuredVariant:
    """Compile explicit block references without mutating or persisting ``project``."""
    raw = project.model_dump(mode="python") if isinstance(project, Project) else deepcopy(project)
    structured = raw.get("structuredContent")
    if not isinstance(structured, dict):
        raise ValueError("project is not a structured project")
    episode = structured.get("episode")
    if not isinstance(episode, dict):
        raise ValueError("structuredContent.episode is invalid")
    variants = episode.get("variants") or []
    variant = next((item for item in variants if item.get("id") == variant_id), None)
    if variant is None:
        raise KeyError(variant_id)
    blocks_by_id = {item.get("id"): item for item in episode.get("blocks") or []}
    warnings: list[str] = []
    compiled: list[CompiledStructuredBlock] = []
    for block_id in variant.get("blockIds") or []:
        block = blocks_by_id[block_id]
        if not block.get("enabled", True):
            warnings.append(f"block {block_id} is disabled and was skipped")
            continue
        text = str(block.get("text") or "").strip()
        if not text:
            warnings.append(f"block {block_id} has empty text and was skipped")
            continue
        compiled.append(CompiledStructuredBlock(
            id=block_id,
            type=str(block.get("type")),
            text=text,
            revision=int(block.get("revision", 1)),
        ))
    script = "\n\n".join(block.text for block in compiled)
    project_view = deepcopy(raw)
    project_view["script"] = script
    structured_view = project_view.get("structuredContent")
    if isinstance(structured_view, dict) and isinstance(structured_view.get("episode"), dict):
        structured_view["episode"]["activeVariantId"] = variant_id
    return CompiledStructuredVariant(
        episode_id=str(episode.get("episodeId")),
        variant_id=str(variant.get("id")),
        variant_name=str(variant.get("name") or ""),
        blocks=tuple(compiled),
        block_ids=tuple(block.id for block in compiled),
        script=script,
        warnings=tuple(warnings),
        project_view=project_view,
    )


def compile_structured_media_variant(
    project: Project | dict,
    variant_id: str,
    duration_resolver=None,
) -> CompiledStructuredMediaVariant:
    """Materialize one structured variant into a legacy-compatible media view."""
    raw = project.model_dump(mode="python") if isinstance(project, Project) else deepcopy(project)
    text_variant = compile_structured_variant(raw, variant_id)
    structured = raw["structuredContent"]
    episode = structured["episode"]
    blocks = {item["id"]: item for item in episode.get("blocks", [])}
    bindings = {item["blockId"]: item for item in episode.get("bindings", [])}
    assets = {item.get("id"): item for item in raw.get("assets", [])}
    subtitles = {item.get("id"): item for item in raw.get("subtitles", [])}
    voiceovers = {item.get("id"): item for item in (raw.get("audio", {}).get("voiceovers") or [])}
    legacy_voiceover = raw.get("audio", {}).get("voiceover") or {}
    warnings = list(text_variant.warnings)
    resolver = duration_resolver or probe_media_duration
    duration_cache: dict[str, float] = {}
    windows: list[CompiledBlockWindow] = []
    generated_segments: list[dict] = []
    generated_subtitles: list[dict] = []
    voice_segments: list[dict] = []
    cursor = 0.0

    for block in text_variant.blocks:
        binding = bindings.get(block.id)
        if binding is None:
            raise ValueError(f"missing media binding for block {block.id}")
        audio_slice = binding.get("audioSlice")
        source_start = source_end = None
        if audio_slice:
            source_start = float(audio_slice.get("sourceStart", 0) or 0)
            source_end = float(audio_slice.get("sourceEnd", 0) or 0)
            duration = source_end - source_start
            voiceover_id = str(audio_slice.get("voiceoverId") or "")
            voice = voiceovers.get(voiceover_id)
            if voice is None and legacy_voiceover.get("id") == voiceover_id:
                voice = legacy_voiceover
            if voice is None:
                raise ValueError(f"voiceoverId not found: {voiceover_id}")
            voice_path = str(voice.get("file") or "")
            if not voice_path or not Path(voice_path).exists():
                raise ValueError(f"voiceover file not found: {voice_path or voiceover_id}")
            if voice_path not in duration_cache:
                duration_cache[voice_path] = float(resolver(voice_path) or 0.0)
            actual = duration_cache[voice_path]
            if actual <= 0:
                actual = float(voice.get("duration", 0) or 0)
            if source_end > actual + 0.05:
                raise ValueError(f"audioSlice exceeds voiceover duration: {voiceover_id}")
            if binding.get("duration") is not None and abs(float(binding["duration"]) - duration) > 0.05:
                warnings.append(f"binding duration differs from audioSlice for block {block.id}")
            voice_segments.append({
                "id": f"{variant_id}__{block.id}__voice",
                "file": voice_path,
                "startAt": cursor,
                "trimStart": source_start,
                "trimEnd": source_end,
                "volume": float(voice.get("volume", 1.0) or 1.0),
                "blockId": block.id,
            })
        else:
            duration = float(binding.get("duration", 0) or 0)
            if duration <= 0:
                raise ValueError(f"block {block.id} requires a positive duration")

        visual_ids = list(binding.get("visualAssetIds") or [])
        visual_assets = []
        for asset_id in visual_ids:
            asset = assets.get(asset_id)
            if asset is None:
                warnings.append(f"visual asset not found: {asset_id}")
                continue
            path = str(asset.get("path") or "")
            if not path or not Path(path).exists():
                warnings.append(f"visual asset file not found: {asset_id}")
                continue
            visual_assets.append(asset)
        if not visual_assets:
            generated_segments.append({
                "id": f"{variant_id}__{block.id}__visual_000",
                "assetPath": "", "type": "black", "start": cursor, "end": cursor + duration,
                "transform": {"x": 0.5, "y": 0.5, "scale": 1.0, "rotation": 0, "fit": "stretch"},
                "bgColor": "#000000",
            })
            warnings.append(f"block {block.id} has no usable visual asset; using black fallback")
        else:
            per_asset = duration / len(visual_assets)
            for index, asset in enumerate(visual_assets):
                start = cursor + index * per_asset
                generated_segments.append({
                    "id": f"{variant_id}__{block.id}__visual_{index:03d}",
                    "assetPath": str(asset.get("path")),
                    "type": asset.get("type", "image") if asset.get("type") in {"image", "video"} else "image",
                    "start": start, "end": cursor + (index + 1) * per_asset,
                    "transform": deepcopy((asset.get("metadata") or {}).get("transform") or {
                        "x": 0.5, "y": 0.5, "scale": 0.85, "rotation": 0, "fit": "contain",
                    }),
                })
        block_subtitle_count = 0
        for subtitle_id in binding.get("subtitleIds") or []:
            subtitle = subtitles.get(subtitle_id)
            if subtitle is None:
                warnings.append(f"subtitle not found: {subtitle_id}")
                continue
            if audio_slice:
                start = cursor + float(subtitle.get("start", 0) or 0) - source_start
                end = cursor + float(subtitle.get("end", 0) or 0) - source_start
            else:
                start = cursor + float(subtitle.get("start", 0) or 0)
                end = cursor + float(subtitle.get("end", 0) or 0)
            clipped_start, clipped_end = max(cursor, start), min(cursor + duration, end)
            if clipped_end <= clipped_start:
                warnings.append(f"subtitle {subtitle_id} falls outside block {block.id}")
                continue
            if clipped_start != start or clipped_end != end:
                warnings.append(f"subtitle {subtitle_id} clipped to block {block.id}")
            item = deepcopy(subtitle)
            item["id"] = f"{variant_id}__{block.id}__{subtitle_id}"
            item["start"], item["end"] = clipped_start, clipped_end
            generated_subtitles.append(item)
            block_subtitle_count += 1
        windows.append(CompiledBlockWindow(
            block_id=block.id, block_type=block.type, start=cursor, end=cursor + duration,
            duration=duration, audio_source_start=source_start, audio_source_end=source_end,
            visual_count=max(1, len(visual_assets)), subtitle_count=block_subtitle_count,
        ))
        cursor += duration

    view = deepcopy(text_variant.project_view)
    view["name"] = f"{raw.get('name', 'Project')} [{variant_id}]"
    view["segments"] = generated_segments
    view["subtitles"] = generated_subtitles
    audio_view = view.setdefault("audio", {})
    audio_view["voiceoverSegments"] = voice_segments
    audio_view["voiceover"] = {}
    view["timeline"] = {**(view.get("timeline") or {}), "voiceoverStartAt": 0.0, "blocks": []}
    return CompiledStructuredMediaVariant(
        episode_id=text_variant.episode_id, variant_id=variant_id,
        variant_name=text_variant.variant_name, block_windows=tuple(windows),
        total_duration=round(cursor, 6), project_view=view, warnings=tuple(dict.fromkeys(warnings)),
    )
