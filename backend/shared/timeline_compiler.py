"""Deterministic runtime compiler for VideoForge project timelines."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from shared.timeline_blocks import build_segments_from_blocks
from shared.voiceover import select_active_voiceover


DurationResolver = Callable[[str], float]


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
    resolve_duration = duration_resolver or (lambda _path: 0.0)
    canvas = deepcopy(project.get("canvas") or {})
    fps = int(canvas.get("fps", 30) or 30)
    timeline = project.get("timeline") or {}
    voiceover_start = max(0.0, float(timeline.get("voiceoverStartAt", 0.0) or 0.0))
    audio = project.get("audio") or {}
    warnings: list[str] = []

    voiceover_clips = _compile_voiceover(audio, voiceover_start, resolve_duration, warnings)
    subtitles = _compile_subtitles(project.get("subtitles") or [], voiceover_start)
    source_segments = deepcopy(project.get("segments") or [])

    voice_end = max((clip.end for clip in voiceover_clips), default=0.0)
    subtitle_end = max((float(item.get("end", 0) or 0) for item in subtitles), default=0.0)
    segment_end = max((float(item.get("end", 0) or 0) for item in source_segments), default=0.0)
    cue_end = _cue_end(cue_points)
    total_duration = round(max(5.0, voice_end, subtitle_end, segment_end, cue_end) + 0.5, 6)

    blocks = timeline.get("blocks") or []
    if not source_segments and blocks:
        source_segments = build_segments_from_blocks(
            deepcopy(project.get("assets") or []),
            deepcopy(blocks),
            total_duration,
            default_per_asset_duration=float(project.get("perImageDuration", 1.0) or 1.0),
        )

    timed_sources = _apply_cue_points(source_segments, cue_points)
    valid_sources = _validate_visual_sources(timed_sources, warnings)
    visual_clips = _expand_visuals(valid_sources, total_duration)
    bgm_clips = _compile_audio_tracks(audio.get("bgm") or {}, total_duration, resolve_duration, warnings, "bgm")
    sfx_clips = _compile_audio_tracks(audio.get("sfx") or [], total_duration, resolve_duration, warnings, "sfx")

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


def _duration(config: dict, path: str, resolver: DurationResolver) -> float:
    declared = float(config.get("duration", 0) or 0)
    return declared if declared > 0 else max(0.0, float(resolver(path) or 0.0))


def _compile_voiceover(audio: dict, start: float, resolver: DurationResolver, warnings: list[str]) -> list[CompiledAudioClip]:
    config = select_active_voiceover(audio)
    path = str(config.get("file", "") or "")
    if not path:
        return []
    if not Path(path).exists():
        warnings.append(f"Missing voiceover asset: {path}")
        return []
    duration = _duration(config, path, resolver)
    if duration <= 0:
        warnings.append(f"Unable to determine voiceover duration: {path}")
        return []
    return [CompiledAudioClip(
        id=str(config.get("id", "voiceover")), file=path, start=start,
        end=start + duration, duration=duration, source_start=0.0,
        volume=float(config.get("volume", 1.0) or 1.0),
    )]


def _compile_subtitles(subtitles: list[dict], offset: float) -> list[dict]:
    compiled = []
    for subtitle in subtitles:
        item = deepcopy(subtitle)
        item["start"] = max(0.0, float(item.get("start", 0) or 0) + offset)
        item["end"] = max(item["start"], float(item.get("end", 0) or 0) + offset)
        compiled.append(item)
    return compiled


def _cue_end(cue_points: list | None) -> float:
    if not cue_points:
        return 0.0
    cue = cue_points[-1]
    if isinstance(cue, dict):
        return float(cue.get("time", 0) or 0) + float(cue.get("duration", 0) or 0)
    return float(cue or 0)


def _apply_cue_points(segments: list[dict], cue_points: list | None) -> list[dict]:
    if not cue_points:
        return segments
    out = []
    for index, segment in enumerate(segments):
        item = deepcopy(segment)
        natural = max(0.0, float(item.get("end", 0) or 0) - float(item.get("start", 0) or 0))
        if index < len(cue_points):
            cue = cue_points[index]
            if isinstance(cue, dict):
                start = float(cue.get("time", item.get("start", 0)) or 0)
                duration = float(cue.get("duration", natural) or natural)
            else:
                start = float(cue or 0)
                next_time = float(cue_points[index + 1]) if index + 1 < len(cue_points) else start + natural
                duration = max(0.0, next_time - start)
            item["start"], item["end"] = start, start + duration
        out.append(item)
    return out


def _validate_visual_sources(segments: list[dict], warnings: list[str]) -> list[dict]:
    valid = []
    for segment in segments:
        if segment.get("type") == "black":
            valid.append(segment)
            continue
        path = str(segment.get("assetPath", "") or "")
        if not path or not Path(path).exists():
            warnings.append(f"Missing visual asset: {path or '<empty>'}")
            continue
        valid.append(segment)
    return valid


def _expand_visuals(segments: list[dict], target: float) -> list[CompiledVisualClip]:
    sources = []
    for segment in segments:
        duration = float(segment.get("end", 0) or 0) - float(segment.get("start", 0) or 0)
        if duration > 0:
            sources.append((segment, duration))
    if not sources:
        return []
    clips = []
    cursor = 0.0
    index = 0
    cap = max(1, min(10000, int(target / 0.05) + len(sources) + 2))
    while cursor < target - 1e-6 and len(clips) < cap:
        segment, natural = sources[index % len(sources)]
        duration = min(natural, target - cursor)
        clips.append(CompiledVisualClip(
            id=str(segment.get("id", f"clip_{index}")),
            asset_path=str(segment.get("assetPath", "") or ""),
            media_type=str(segment.get("type", "image")),
            start=round(cursor, 6), end=round(cursor + duration, 6), duration=round(duration, 6),
            transform=deepcopy(segment.get("transform") or {}),
            animation=deepcopy(segment.get("animation")),
            source_start=float(segment.get("sourceStart", 0) or 0),
            bg_color=segment.get("bgColor"),
        ))
        cursor += duration
        index += 1
    return clips


def _compile_audio_tracks(config, total: float, resolver: DurationResolver, warnings: list[str], kind: str) -> list[CompiledAudioClip]:
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
        full = _duration(track, path, resolver)
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
            volume=float(track.get("volume", 0.3 if kind == "bgm" else 0.8) or 0),
            fade_in=float(track.get("fadeIn", 0) or 0), fade_out=float(track.get("fadeOut", 0) or 0),
        ))
    return clips
