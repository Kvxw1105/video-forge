"""Deterministic runtime compiler for VideoForge project timelines."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import math
from pathlib import Path
from typing import Callable

from shared.timeline_blocks import build_segments_from_blocks
from shared.voiceover import select_active_voiceover


DurationResolver = Callable[[str], float]
VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".tiff"}
SUPPORTED_VISUAL_EXTENSIONS = VIDEO_EXTENSIONS | IMAGE_EXTENSIONS


@dataclass(frozen=True)
class CompiledKeyframe:
    property: str
    time: float
    value: float
    easing: str = "linear"


@dataclass(frozen=True)
class CompiledVisualClip:
    id: str
    asset_path: str
    media_type: str
    start: float
    end: float
    duration: float
    transform: dict
    animation: dict | None
    source_start: float = 0.0
    bg_color: str | None = None
    keyframes: tuple[CompiledKeyframe, ...] = ()

    def to_segment(self) -> dict:
        segment = {
            "id": self.id,
            "assetPath": self.asset_path,
            "type": self.media_type,
            "start": self.start,
            "end": self.end,
            "transform": deepcopy(self.transform),
            "animation": deepcopy(self.animation),
            "sourceStart": self.source_start,
        }
        if self.bg_color is not None:
            segment["bgColor"] = self.bg_color
        if self.keyframes:
            segment["keyframes"] = [
                {"property": item.property, "time": item.time, "value": item.value, "easing": item.easing}
                for item in self.keyframes
            ]
        return segment


@dataclass(frozen=True)
class CompiledAudioClip:
    id: str
    file: str
    start: float
    end: float
    duration: float
    source_start: float
    volume: float
    fade_in: float = 0.0
    fade_out: float = 0.0

    def to_track(self) -> dict:
        return {
            "id": self.id,
            "file": self.file,
            "startAt": self.start,
            "trimStart": self.source_start,
            "trimEnd": self.source_start + self.duration,
            "volume": self.volume,
            "fadeIn": self.fade_in,
            "fadeOut": self.fade_out,
        }


@dataclass(frozen=True)
class CompiledTimeline:
    canvas: dict
    fps: int
    total_duration: float
    visual_clips: tuple[CompiledVisualClip, ...]
    voiceover_clips: tuple[CompiledAudioClip, ...]
    bgm_clips: tuple[CompiledAudioClip, ...]
    sfx_clips: tuple[CompiledAudioClip, ...]
    subtitles: tuple[dict, ...]
    overlays: dict
    warnings: tuple[str, ...]

    def visual_segments(self) -> list[dict]:
        return [clip.to_segment() for clip in self.visual_clips]


def compile_project_timeline(
    project: dict,
    cue_points: list | None = None,
    *,
    duration_resolver: DurationResolver | None = None,
) -> CompiledTimeline:
    """Compile persisted project data into one absolute, immutable timeline."""
    canvas = deepcopy(project.get("canvas") or {})
    fps = int(canvas.get("fps", 30) or 30)
    timeline = project.get("timeline") or {}
    voiceover_start = max(0.0, float(timeline.get("voiceoverStartAt", 0.0) or 0.0))
    audio = project.get("audio") or {}
    warnings: list[str] = []

    voiceover_clips = _compile_voiceover(audio, voiceover_start, duration_resolver, warnings)
    subtitles = _compile_subtitles(project.get("subtitles") or [], voiceover_start)
    persisted_segments = deepcopy(project.get("segments") or [])
    valid_persisted = _validate_visual_sources(persisted_segments, warnings)
    blocks = timeline.get("blocks") or []
    fixed_block_duration = sum(
        max(0.0, float(block.get("duration", 0) or 0))
        for block in blocks if block.get("duration") != "rest"
    ) if not valid_persisted else 0.0

    voice_end = max((clip.end for clip in voiceover_clips), default=0.0)
    subtitle_end = max((float(item.get("end", 0) or 0) for item in subtitles), default=0.0)
    segment_end = max((float(item.get("end", 0) or 0) for item in valid_persisted), default=0.0)
    content_duration = max(5.0, voice_end, subtitle_end, segment_end, fixed_block_duration)

    source_segments = valid_persisted
    if not source_segments and blocks:
        source_segments = build_segments_from_blocks(
            _valid_block_assets(deepcopy(project.get("assets") or []), warnings),
            deepcopy(blocks),
            content_duration,
            default_per_asset_duration=float(project.get("perImageDuration", 1.0) or 1.0),
            warnings=warnings,
        )
        source_segments = _validate_visual_sources(
            source_segments, warnings, fallback_invalid=True
        )

    pattern = _resolve_visual_pattern(source_segments, cue_points, warnings)
    pattern_end = max((float(item.get("end", 0) or 0) for item in pattern), default=0.0)
    content_duration = max(content_duration, pattern_end)
    tail_padding = 0.5
    total_duration = round(content_duration + tail_padding, 6)
    visual_clips = _expand_visuals(pattern, content_duration, warnings)
    bgm_clips = _compile_audio_tracks(audio.get("bgm") or {}, total_duration, duration_resolver, warnings, "bgm")
    sfx_clips = _compile_audio_tracks(audio.get("sfx") or [], total_duration, duration_resolver, warnings, "sfx")

    return CompiledTimeline(
        canvas=canvas,
        fps=fps,
        total_duration=total_duration,
        visual_clips=tuple(visual_clips),
        voiceover_clips=tuple(voiceover_clips),
        bgm_clips=tuple(bgm_clips),
        sfx_clips=tuple(sfx_clips),
        subtitles=tuple(subtitles),
        overlays=deepcopy(project.get("overlays") or {}),
        warnings=tuple(warnings),
    )


def _duration(config: dict, path: str, resolver: DurationResolver | None, warnings: list[str], kind: str) -> float:
    declared = float(config.get("duration", 0) or 0)
    if resolver is not None:
        try:
            actual = max(0.0, float(resolver(path) or 0.0))
            if actual > 0:
                return actual
        except Exception as error:
            warnings.append(f"Unable to probe {kind} duration for {path}: {error}; using declared duration")
    return max(0.0, declared)


def _volume(value, default: float) -> float:
    raw = default if value is None else float(value)
    return max(0.0, min(1.0, raw))


def _compile_voiceover(audio: dict, start: float, resolver: DurationResolver | None, warnings: list[str]) -> list[CompiledAudioClip]:
    config = select_active_voiceover(audio)
    path = str(config.get("file", "") or "")
    if not path:
        return []
    if not Path(path).exists():
        warnings.append(f"Missing voiceover asset: {path}")
        return []
    duration = _duration(config, path, resolver, warnings, "voiceover")
    if duration <= 0:
        warnings.append(f"Unable to determine voiceover duration: {path}")
        return []
    return [CompiledAudioClip(
        id=str(config.get("id", "voiceover")), file=path, start=start,
        end=start + duration, duration=duration, source_start=0.0,
        volume=_volume(config.get("volume"), 1.0),
    )]


def _compile_subtitles(subtitles: list[dict], offset: float) -> list[dict]:
    compiled = []
    for subtitle in subtitles:
        item = deepcopy(subtitle)
        item["start"] = max(0.0, float(item.get("start", 0) or 0) + offset)
        item["end"] = max(item["start"], float(item.get("end", 0) or 0) + offset)
        compiled.append(item)
    return compiled


def _resolve_visual_pattern(segments: list[dict], cue_points: list | None, warnings: list[str]) -> list[dict]:
    if not segments:
        return []
    if not cue_points:
        cursor = 0.0
        out = []
        for segment in segments:
            natural = max(0.0, float(segment.get("end", 0) or 0) - float(segment.get("start", 0) or 0))
            if natural <= 0:
                continue
            item = deepcopy(segment)
            item["start"], item["end"] = cursor, cursor + natural
            out.append(item)
            cursor += natural
        return out

    out = []
    cursor = 0.0
    for index, segment in enumerate(segments):
        natural = max(0.0, float(segment.get("end", 0) or 0) - float(segment.get("start", 0) or 0))
        if natural <= 0:
            continue
        if index < len(cue_points):
            cue = cue_points[index]
            requested = float(cue.get("time", cursor) or 0) if isinstance(cue, dict) else float(cue or 0)
            if isinstance(cue, dict):
                raw_duration = float(cue.get("duration", 0) or 0)
                duration = raw_duration if raw_duration > 0 else natural
            elif index + 1 < len(cue_points):
                duration = max(0.0, float(cue_points[index + 1]) - requested)
                if duration <= 0:
                    duration = natural
            else:
                duration = natural
            start = max(cursor, max(0.0, requested))
            if requested < cursor:
                warnings.append(f"Cue {index} start {requested:g} overlaps prior visual; clamped to {cursor:g}")
            if start > cursor:
                out.append(_black_segment(cursor, start, f"cue_gap_{index}"))
            item = deepcopy(segment)
            item["start"], item["end"] = start, start + duration
            out.append(item)
            cursor = item["end"]
        else:
            item = deepcopy(segment)
            item["start"], item["end"] = cursor, cursor + natural
            out.append(item)
            cursor = item["end"]
    return out


def _black_segment(start: float, end: float, clip_id: str) -> dict:
    return {
        "id": clip_id, "assetPath": "", "type": "black", "start": start, "end": end,
        "transform": {"x": 0.5, "y": 0.5, "scale": 1, "rotation": 0, "fit": "stretch"},
        "bgColor": "#000000",
    }


def _valid_block_assets(assets: list[dict], warnings: list[str]) -> list[dict]:
    valid = []
    for asset in assets:
        path = str(asset.get("path", "") or "")
        if not path or not Path(path).exists():
            continue
        if Path(path).suffix.lower() not in SUPPORTED_VISUAL_EXTENSIONS:
            warnings.append(f"Unsupported visual asset: {path}")
            continue
        valid.append(asset)
    return valid


def _validate_visual_sources(
    segments: list[dict], warnings: list[str], *, fallback_invalid: bool = False
) -> list[dict]:
    valid = []
    for segment in segments:
        if segment.get("type") == "black":
            valid.append(segment)
            continue
        path = str(segment.get("assetPath", "") or "")
        if not path or not Path(path).exists():
            if fallback_invalid:
                warnings.append(
                    f"Timeline block visual asset is missing: {path or '<empty>'}; using black fallback"
                )
                valid.append(_black_segment(
                    float(segment.get("start", 0) or 0),
                    float(segment.get("end", 0) or 0),
                    f"{segment.get('id', 'block')}__fallback",
                ))
            else:
                warnings.append(f"Missing visual asset: {path or '<empty>'}")
            continue
        if Path(path).suffix.lower() not in SUPPORTED_VISUAL_EXTENSIONS:
            if fallback_invalid:
                warnings.append(
                    f"Timeline block visual asset is unsupported: {path}; using black fallback"
                )
                valid.append(_black_segment(
                    float(segment.get("start", 0) or 0),
                    float(segment.get("end", 0) or 0),
                    f"{segment.get('id', 'block')}__fallback",
                ))
            else:
                warnings.append(f"Unsupported visual asset: {path}")
            continue
        valid.append(segment)
    return valid


SUPPORTED_VISUAL_KEYFRAME_PROPERTIES = {
    "position_x", "position_y", "scale_x", "scale_y", "rotation", "opacity",
}
_KEYFRAME_TIME_EPSILON = 1e-6


def interpolate_keyframe_value(
    keyframes: tuple[CompiledKeyframe, ...], property_name: str, at_time: float,
) -> float | None:
    points = sorted(
        (item for item in keyframes if item.property == property_name),
        key=lambda item: item.time,
    )
    if not points:
        return None
    if at_time <= points[0].time:
        return points[0].value
    if at_time >= points[-1].time:
        return points[-1].value
    for left, right in zip(points, points[1:]):
        if left.time <= at_time <= right.time:
            if right.time == left.time:
                return right.value
            ratio = (at_time - left.time) / (right.time - left.time)
            return left.value + ratio * (right.value - left.value)
    return points[-1].value


def slice_keyframes_for_window(
    keyframes: tuple[CompiledKeyframe, ...], window_start: float, window_duration: float,
) -> tuple[CompiledKeyframe, ...]:
    window_end = window_start + window_duration
    result: dict[tuple[str, float], CompiledKeyframe] = {}
    properties = list(dict.fromkeys(item.property for item in keyframes))
    for property_name in properties:
        start_value = interpolate_keyframe_value(keyframes, property_name, window_start)
        end_value = interpolate_keyframe_value(keyframes, property_name, window_end)
        if start_value is not None:
            result[(property_name, 0.0)] = CompiledKeyframe(property_name, 0.0, start_value, "linear")
        for item in keyframes:
            if item.property == property_name and window_start < item.time < window_end:
                local_time = round(item.time - window_start, 6)
                result[(property_name, local_time)] = CompiledKeyframe(
                    item.property, local_time, item.value, item.easing
                )
        if end_value is not None:
            local_end = round(window_duration, 6)
            result[(property_name, local_end)] = CompiledKeyframe(
                property_name, local_end, end_value, "linear"
            )
    return tuple(sorted(result.values(), key=lambda item: (item.property, item.time)))


def _compile_visual_keyframes(
    raw_keyframes: list, clip_duration: float, warnings: list[str], clip_id: str,
) -> tuple[CompiledKeyframe, ...]:
    if not raw_keyframes:
        return ()
    dedup: dict[tuple[str, float], CompiledKeyframe] = {}
    for raw in raw_keyframes:
        if not isinstance(raw, dict):
            warnings.append(f"Clip {clip_id} has invalid keyframe object")
            continue
        property_name = raw.get("property")
        if property_name not in SUPPORTED_VISUAL_KEYFRAME_PROPERTIES:
            warnings.append(f"Clip {clip_id} has unsupported keyframe property: {property_name}")
            continue
        try:
            time = float(raw.get("time"))
        except (TypeError, ValueError):
            warnings.append(f"Clip {clip_id} keyframe {property_name} has invalid time")
            continue
        if not math.isfinite(time) or time < 0 or time > clip_duration + _KEYFRAME_TIME_EPSILON:
            warnings.append(f"Clip {clip_id} keyframe {property_name} time is outside clip duration")
            continue
        if abs(time - clip_duration) <= _KEYFRAME_TIME_EPSILON:
            time = clip_duration
        try:
            value = float(raw.get("value"))
        except (TypeError, ValueError):
            warnings.append(f"Clip {clip_id} keyframe {property_name} has invalid value")
            continue
        if not math.isfinite(value):
            warnings.append(f"Clip {clip_id} keyframe {property_name} value is not finite")
            continue
        if property_name in {"scale_x", "scale_y"} and value <= 0:
            warnings.append(f"Clip {clip_id} keyframe {property_name} value must be positive")
            continue
        if property_name == "opacity":
            clamped = max(0.0, min(1.0, value))
            if clamped != value:
                warnings.append(f"Clip {clip_id} keyframe opacity was clamped to [0, 1]")
            value = clamped
        easing = str(raw.get("easing", "linear") or "linear")
        if easing != "linear":
            warnings.append(f"Clip {clip_id} keyframe {property_name} uses unsupported easing: {easing}")
            easing = "linear"
        dedup[(property_name, round(time, 6))] = CompiledKeyframe(property_name, round(time, 6), value, easing)
    return tuple(sorted(dedup.values(), key=lambda item: (item.property, item.time)))


def _expand_visuals(pattern: list[dict], target: float, warnings: list[str]) -> list[CompiledVisualClip]:
    sources = [segment for segment in pattern if float(segment.get("end", 0) or 0) > float(segment.get("start", 0) or 0)]
    if not sources:
        return []
    clips = []
    pattern_end = max(float(segment["end"]) for segment in sources)
    if pattern_end <= 0:
        return []
    prepared_sources = []
    for segment in sources:
        semantic_start = float(segment.get("start", 0) or 0)
        semantic_duration = max(0.0, float(segment.get("end", 0) or 0) - semantic_start)
        semantic_keyframes = _compile_visual_keyframes(
            segment.get("keyframes") or [], semantic_duration, warnings, str(segment.get("id", "clip"))
        )
        prepared_sources.append((segment, semantic_start, semantic_duration, semantic_keyframes))
    cycle = 0
    cap = max(1, min(10000, int(target / 0.05) + len(sources) + 2))
    while cycle * pattern_end < target - 1e-6 and len(clips) < cap:
        offset = cycle * pattern_end
        for position, (segment, semantic_start, semantic_duration, semantic_keyframes) in enumerate(prepared_sources):
            start = offset + float(segment["start"])
            if start >= target - 1e-6:
                break
            end = min(offset + float(segment["end"]), target)
            duration = max(0.0, end - start)
            if duration <= 0:
                continue
            local_offset = start - (offset + semantic_start)
            if abs(local_offset) <= _KEYFRAME_TIME_EPSILON and abs(duration - semantic_duration) <= _KEYFRAME_TIME_EPSILON:
                child_keyframes = semantic_keyframes
            else:
                child_keyframes = slice_keyframes_for_window(
                    semantic_keyframes, window_start=local_offset, window_duration=duration,
                )
            clips.append(CompiledVisualClip(
                id=f"{segment.get('id', 'clip')}__c{cycle}_p{position}",
                asset_path=str(segment.get("assetPath", "") or ""),
                media_type=str(segment.get("type", "image")),
                start=round(start, 6), end=round(end, 6), duration=round(duration, 6),
                transform=deepcopy(segment.get("transform") or {}),
                animation=deepcopy(segment.get("animation")),
                source_start=float(segment.get("sourceStart", 0) or 0),
                bg_color=segment.get("bgColor"),
                keyframes=child_keyframes,
            ))
        cycle += 1
    return clips


def _compile_audio_tracks(config, total: float, resolver: DurationResolver | None, warnings: list[str], kind: str) -> list[CompiledAudioClip]:
    if isinstance(config, dict):
        tracks = config.get("tracks") or ([] if not config.get("file") else [config])
    else:
        tracks = config
    clips = []
    for index, track in enumerate(tracks or []):
        path = str(track.get("file", "") or "")
        if not path or not Path(path).exists():
            if path:
                warnings.append(f"Missing {kind} asset: {path}")
            continue
        full = _duration(track, path, resolver, warnings, kind)
        source_start = max(0.0, float(track.get("trimStart", 0) or 0))
        trim_end = float(track.get("trimEnd", 0) or 0)
        source_end = trim_end if trim_end > source_start else full
        start = max(0.0, float(track.get("startAt", 0) or 0))
        duration = min(max(0.0, source_end - source_start), max(0.0, total - start))
        if duration <= 0:
            continue
        clips.append(CompiledAudioClip(
            id=str(track.get("id", f"{kind}_{index}")), file=path, start=start,
            end=start + duration, duration=duration, source_start=source_start,
            volume=_volume(track.get("volume"), 0.3 if kind == "bgm" else 0.8),
            fade_in=float(track.get("fadeIn", 0) or 0), fade_out=float(track.get("fadeOut", 0) or 0),
        ))
    return clips
