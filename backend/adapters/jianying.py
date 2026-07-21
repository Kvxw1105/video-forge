import json
import os
import re
import shutil
import struct
import subprocess
from process_utils import run as run_process
from shared.timeline_compiler import CompiledTimeline, compile_project_timeline
from shared.timeline_compiler import CompiledKeyframe
from adapters.jianying_keyframes import apply_keyframes_to_video_segment, lower_keyframes_for_segment
from shared.media_probe import probe_media_duration
import zlib
from pathlib import Path
from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4
from pyJianYingDraft import ScriptFile, VideoSegment, AudioSegment, TextSegment, DraftFolder, TrackType, trange, ClipSettings
from pyJianYingDraft.keyframe import KeyframeProperty
from pyJianYingDraft.text_segment import TextStyle

from shared.render_params import (
    subtitle_to_jianying_transform,
    overlay_to_jianying_transform,
    font_size_to_jianying,
    normalize_hex,
)


def _resolve_path(file_path: str) -> Path | None:
    """尝试解析文件路径，找不到返回 None"""
    if not file_path:
        return None
    p = Path(file_path)
    if p.exists():
        return p
    return None


def _ensure_color_image(work_dir: Path, width: int, height: int, color: str) -> Path:
    """Create a canvas-sized solid PNG for editable JianYing color clips."""
    width = max(1, int(width))
    height = max(1, int(height))
    hex_color = normalize_hex(color)
    try:
        rgb = bytes.fromhex(hex_color)
    except ValueError:
        hex_color = "000000"
        rgb = bytes.fromhex(hex_color)
    output = work_dir / f"_vf_color_{width}x{height}_{hex_color}.png"
    if output.exists() and output.stat().st_size > 0:
        return output

    def chunk(kind: bytes, data: bytes) -> bytes:
        checksum = zlib.crc32(kind + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", checksum)

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    row = b"\x00" + rgb * width
    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", header)
    png += chunk(b"IDAT", zlib.compress(row * height, level=9))
    png += chunk(b"IEND", b"")
    output.write_bytes(png)
    return output


def _jianying_source_duration(duration: float) -> float:
    """Keep real pyJianYingDraft source ranges just inside material duration."""
    module = getattr(AudioSegment, "__module__", "")
    if module.startswith("pyJianYingDraft"):
        return max(0.0, float(duration) - 0.001)
    return float(duration)


@dataclass(frozen=True)
class DraftWriteResult:
    policy: str
    final_path: Path
    source_draft: str | None = None
    backup_path: Path | None = None
    revision: int | None = None
    warnings: tuple[str, ...] = ()

    def to_metadata(self) -> dict:
        return {"policy": self.policy, "draftName": self.final_path.name,
                "finalDraftName": self.final_path.name, "finalPath": str(self.final_path.resolve()),
                "sourceDraft": self.source_draft, "revision": self.revision,
                "backupPath": str(self.backup_path.resolve()) if self.backup_path else None,
                "warnings": list(self.warnings)}

    def __getattr__(self, name):
        return getattr(self.final_path, name)


class DraftRollbackError(RuntimeError):
    def __init__(self, backup_path: Path, publish_error: Exception, rollback_error: Exception):
        self.backup_path = backup_path
        self.publish_error = publish_error
        self.rollback_error = rollback_error
        super().__init__(
            f"JianYing draft publish failed ({publish_error}); rollback also failed "
            f"({rollback_error}). Original draft backup remains at: {backup_path}"
        )


class DraftMediaPathRewriteError(RuntimeError):
    """Raised when a staged JianYing draft cannot be made publishable."""


def _rename_directory(source: Path, target: Path) -> Path:
    return source.rename(target)


def _validate_source_draft(base_dir: Path, source_draft: str | None) -> Path:
    if not isinstance(source_draft, str) or not source_draft or source_draft in {".", ".."}:
        raise ValueError("replace_explicit requires a source_draft folder name")
    if "/" in source_draft or "\\" in source_draft or ".." in source_draft:
        raise ValueError("source_draft must be a single folder name")
    root = base_dir.resolve()
    target = (root / source_draft).resolve()
    if target.parent != root or not (target / "draft_content.json").is_file():
        raise ValueError("source_draft must name an existing JianYing draft")
    return target


def _reserve_versioned_name(base_dir: Path, raw_name: str) -> tuple[str, int, Path]:
    safe_name = _sanitize_folder_name(raw_name)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    reservation_root = base_dir / ".videoforge-reservations"
    reservation_root.mkdir(exist_ok=True)
    for revision in range(1, 1001):
        draft_name = f"{safe_name}_{stamp}_r{revision}"
        if (base_dir / draft_name).exists():
            continue
        reservation = reservation_root / draft_name
        try:
            reservation.mkdir()
        except FileExistsError:
            continue
        if (base_dir / draft_name).exists():
            reservation.rmdir()
            continue
        return draft_name, revision, reservation
    raise RuntimeError("unable to reserve a JianYing draft revision after 1000 attempts")


def generate_jianying_draft(project: dict, output_dir: Path | None = None, cue_points: list | None = None, *, policy: str = "create_new", source_draft: str | None = None, direct_export: bool = False) -> DraftWriteResult:
    if policy not in {"create_new", "replace_explicit"}:
        raise ValueError("policy must be create_new or replace_explicit")
    if policy == "replace_explicit" and not direct_export:
        raise ValueError("replace_explicit is only supported by direct JianYing export")
    base_dir = Path(output_dir) if output_dir is not None else Path(project.get("exportSettings", {}).get("outputDir", "projects/temp"))
    base_dir.mkdir(parents=True, exist_ok=True)
    source_path = _validate_source_draft(base_dir, source_draft) if policy == "replace_explicit" else None
    compiled = compile_project_timeline(
        project, cue_points,
        duration_resolver=probe_media_duration,
    )
    raw_name = project.get("name", project.get("id", "video"))
    if policy == "create_new":
        final_name, revision, reservation_path = _reserve_versioned_name(base_dir, raw_name)
    else:
        final_name, revision, reservation_path = source_path.name, None, None
    final_path = base_dir / final_name if policy == "create_new" else source_path
    # JianYing watches its draft root while exporting. Keep direct-export
    # staging outside that watched tree so the client cannot encrypt or move
    # draft_content.json before media paths are rewritten and published.
    staging_parent = base_dir.parent if direct_export else base_dir
    staging_root = staging_parent / f".videoforge-staging-{uuid4().hex}"
    try:
        staging_root.mkdir()
        rendered = _render_jianying_draft(
            staging_root, final_name, compiled
        )
        if isinstance(rendered, tuple):
            staged_draft, adapter_warnings = rendered
        else:  # compatibility for focused tests replacing the renderer
            staged_draft, adapter_warnings = rendered, ()
        content_file = staged_draft / "draft_content.json"
        real_jianying_runtime = str(getattr(DraftFolder, "__module__", "")).startswith("pyJianYingDraft")
        if not content_file.exists() and real_jianying_runtime:
            raise DraftMediaPathRewriteError(
                "failed to rewrite generated JianYing media paths: draft_content.json is missing"
            )
        # Focused renderer doubles may intentionally keep serialization in memory.
        if content_file.exists() and real_jianying_runtime:
            _rewrite_draft_media_paths(
                draft_dir=staged_draft,
                old_root=staged_draft,
                new_root=final_path,
            )
        if policy == "create_new":
            _rename_directory(staged_draft, final_path)
            backup_path = None
        else:
            backup_root = base_dir / ".videoforge-backups"
            backup_root.mkdir(exist_ok=True)
            backup_path = backup_root / f"{source_path.name}-{datetime.now().strftime('%Y%m%d_%H%M%S')}-{uuid4().hex[:8]}"
            _rename_directory(source_path, backup_path)
            try:
                _rename_directory(staged_draft, source_path)
            except Exception as publish_error:
                try:
                    _rename_directory(backup_path, source_path)
                except Exception as rollback_error:
                    raise DraftRollbackError(
                        backup_path, publish_error, rollback_error
                    ) from rollback_error
                raise
        _fix_meta_paths(final_path, final_name)
        all_warnings = tuple(dict.fromkeys((*compiled.warnings, *adapter_warnings)))
        return DraftWriteResult(
            policy, final_path,
            source_draft if policy == "replace_explicit" else None,
            backup_path, revision, all_warnings,
        )
    finally:
        if staging_root.exists():
            shutil.rmtree(staging_root, ignore_errors=True)
        if reservation_path is not None and reservation_path.exists():
            reservation_path.rmdir()


def _render_jianying_draft(
    base_dir: Path, safe_name: str, compiled_timeline: CompiledTimeline,
) -> tuple[Path, tuple[str, ...]]:
    """
    生成剪映草稿。

    Args:
        output_dir: 输出目录。为 None 时使用 project 内的 exportSettings.outputDir。
                     传剪映草稿目录（com.lveditor.draft）则直接生成到目标位置。
    Returns:
        草稿文件夹路径
    """
    compiled = compiled_timeline
    adapter_warnings: list[str] = []
    canvas = compiled.canvas
    width = canvas["width"]
    height = canvas["height"]
    fps = canvas.get("fps", 30)

    # 确定基础输出目录
    # 草稿名称 = 项目名（sanitized）
    draft_dir = base_dir / safe_name

    draft_folder = DraftFolder(str(base_dir))
    script = draft_folder.create_draft(
        safe_name,
        width, height, fps,
        allow_replace=False
    )

    total_duration = compiled.total_duration
    # Pre-process media with brightness/contrast adjustments if needed
    overlays = compiled.overlays
    adjustments = overlays.get("adjustments", {}) if overlays else {}
    adj_map = _preprocess_media_with_adjustments(
        compiled.visual_segments(), adjustments, draft_dir
    )

    voiceover = compiled.voiceover_clips[0] if compiled.voiceover_clips else None
    voiceover_start_at = voiceover.start if voiceover else 0.0

    # 1. Main image/video track
    segments = _lower_jianying_visual_segments(compiled.visual_segments())
    if segments:
        script.add_track(TrackType.video, "main")
        main_track = script.tracks["main"]
        for seg in segments:
            seg_start = seg.get("start", 0)
            seg_end = seg.get("end", total_duration)
            is_color_clip = seg.get("type") in {"black", "color"}
            if is_color_clip:
                asset_path = _ensure_color_image(
                    draft_dir,
                    width,
                    height,
                    seg.get("bgColor", "#000000"),
                )
            else:
                asset_path = _resolve_path(adj_map.get(seg.get("assetPath", ""), seg.get("assetPath", "")))
            if not asset_path:
                continue

            # Build clip_settings from segment transform
            xf = seg.get("transform", {})
            tx = 0.5 if is_color_clip else xf.get("x", 0.5)
            ty = 0.5 if is_color_clip else xf.get("y", 0.5)
            sc = 1.0 if is_color_clip else xf.get("scale", 0.85)
            rot = 0 if is_color_clip else xf.get("rotation", 0)

            # Convert to JianYing coordinate system: (0,0)=center, ±0.5=edge
            clip = ClipSettings(
                scale_x=sc, scale_y=sc,
                transform_x=(tx - 0.5) * 2,  # 0.5→0(center), 0→-1(left edge)
                transform_y=(ty - 0.5) * 2,
                rotation=rot,
            )

            duration = max(0.0, float(seg_end) - float(seg_start))
            v = VideoSegment(
                str(asset_path),
                target_timerange=trange(f"{seg_start}s", f"{duration}s"),
                clip_settings=clip,
            )
            raw_keyframes = tuple(
                CompiledKeyframe(
                    str(item.get("property")), float(item.get("time", 0)),
                    float(item.get("value", 0)), str(item.get("easing", "linear") or "linear"),
                )
                for item in (seg.get("keyframes") or [])
            )
            lowered_keyframes = lower_keyframes_for_segment(
                semantic_keyframes=raw_keyframes,
                semantic_duration=float(seg.get("_semanticDuration", duration) or duration),
                child_start=float(seg.get("_semanticOffset", 0) or 0),
                child_duration=duration,
                warnings=adapter_warnings,
            )
            apply_keyframes_to_video_segment(v, lowered_keyframes, adapter_warnings)
            script.add_material(v.material_instance)
            main_track.add_segment(v)

    # 2. BGM tracks — each track has independent timeline startAt and source trim
    bgm_tracks = list(compiled.bgm_clips)
    if bgm_tracks:
        script.add_track(TrackType.audio, "bgm")
        for i, track in enumerate(bgm_tracks):
            bgm_path = _resolve_path(track.file)
            if not bgm_path:
                continue
            source_duration = _jianying_source_duration(track.duration)
            a = AudioSegment(
                str(bgm_path),
                target_timerange=trange(f"{track.start}s", f"{track.duration}s"),
                source_timerange=trange(f"{track.source_start}s", f"{source_duration}s"),
                volume=max(0.0, min(1.0, track.volume))
            )
            fade_in, fade_out = _audio_fade_seconds(
                {"fadeIn": track.fade_in, "fadeOut": track.fade_out}, track.duration
            )
            if fade_in > 0 or fade_out > 0:
                a.add_fade(f"{fade_in}s", f"{fade_out}s")
                script.materials.audio_fades.append(a.fade)
            script.add_material(a.material_instance)
            script.tracks["bgm"].add_segment(a)

    # 2.5 SFX tracks — local sound effects at explicit timeline positions
    sfx_tracks = list(compiled.sfx_clips)
    if sfx_tracks:
        script.add_track(TrackType.audio, "sfx")
        for i, track in enumerate(sfx_tracks):
            sfx_path = _resolve_path(track.file)
            if not sfx_path:
                continue
            source_duration = _jianying_source_duration(track.duration)
            a = AudioSegment(
                str(sfx_path),
                target_timerange=trange(f"{track.start}s", f"{track.duration}s"),
                source_timerange=trange(f"{track.source_start}s", f"{source_duration}s"),
                volume=max(0.0, min(1.0, track.volume))
            )
            script.add_material(a.material_instance)
            script.tracks["sfx"].add_segment(a)

    # 3. Voiceover track — 用当前激活配音的实际音频时长
    voiceover_path = _resolve_path(voiceover.file) if voiceover else None
    voiceover_vol = voiceover.volume if voiceover else 1.0
    if voiceover_path:
        dur = voiceover.duration
        if dur > 0:
            script.add_track(TrackType.audio, "voiceover")
            source_duration = _jianying_source_duration(dur)
            va = AudioSegment(
                str(voiceover_path),
                target_timerange=trange(f"{voiceover_start_at}s", f"{dur}s"),
                source_timerange=trange("0s", f"{source_duration}s"),
                volume=max(0.0, min(1.0, voiceover_vol)),
            )
            script.add_material(va.material_instance)
            script.tracks["voiceover"].add_segment(va)

    # 4. Subtitle track (if enabled)
    overlays = compiled.overlays
    subtitle_enabled = overlays.get("subtitle_enabled", True) if overlays else True
    subtitles = list(compiled.subtitles)
    if subtitle_enabled and subtitles:
        script.add_track(TrackType.text, "subtitles")
        subtitle_track = script.tracks["subtitles"]
        for sub in subtitles:
            txt = str(sub.get("text", "")).strip()
            if not txt:
                continue
            style_cfg = sub.get("style", {}) or {}
            font_size = max(6.0, min(120.0, float(style_cfg.get("fontSize", 48))))
            tsize = font_size_to_jianying(font_size)
            position = style_cfg.get("position", "bottom_center")
            _, _, horiz = position.partition("_")
            text_align = {"left": 1, "right": 2}.get(horiz, 0)
            subtitle_style = TextStyle(size=tsize, align=text_align, auto_wrapping=True)
            s = max(0.0, float(sub.get("start", 0.0)))
            e = max(s, float(sub.get("end", 0.0)))
            ts = TextSegment(
                txt,
                timerange=trange(f"{s}s", f"{max(0.01, e - s)}s"),
                style=subtitle_style,
            )
            transform_x, transform_y = subtitle_to_jianying_transform(position)
            try:
                ts.clip_settings.transform_y = transform_y
                ts.clip_settings.transform_x = transform_x
            except Exception:
                pass
            _add_jianying_text_segment(script, ts, "subtitles")

    # 5. Title text
    title_cfg = overlays.get("title", {})
    if title_cfg.get("enabled") and title_cfg.get("text"):
        script.add_track(TrackType.text, "title")
        title_fs = font_size_to_jianying(
            max(6.0, min(120.0, float(title_cfg.get("fontSize", 48))))
        )
        title_style = TextStyle(size=title_fs, align=0, auto_wrapping=True)
        ts = TextSegment(title_cfg["text"], timerange=trange("0s", f"{total_duration}s"), style=title_style)
        # Apply position
        try:
            tx = float(title_cfg.get("x", 0.5))
            ty = float(title_cfg.get("y", 0.08))
            jx, jy = overlay_to_jianying_transform(tx, ty)
            ts.clip_settings.transform_x = jx
            ts.clip_settings.transform_y = jy
        except Exception:
            pass
        _add_jianying_text_segment(script, ts, "title")

    # 6. Watermark text
    watermark_cfg = overlays.get("watermark", {})
    if watermark_cfg.get("enabled") and watermark_cfg.get("text"):
        script.add_track(TrackType.text, "watermark")
        wm_fs = font_size_to_jianying(
            max(4.0, min(60.0, float(watermark_cfg.get("fontSize", 24))))
        )
        wm_style = TextStyle(size=wm_fs, align=2, auto_wrapping=True)  # align=2: right
        ws = TextSegment(watermark_cfg["text"], timerange=trange("0s", f"{total_duration}s"), style=wm_style)
        # Apply position
        try:
            wx = float(watermark_cfg.get("x", 0.85))
            wy = float(watermark_cfg.get("y", 0.92))
            jx, jy = overlay_to_jianying_transform(wx, wy)
            ws.clip_settings.transform_x = jx
            ws.clip_settings.transform_y = jy
        except Exception:
            pass
        _add_jianying_text_segment(script, ws, "watermark")

    # 6.5 Directory progress — editable text, with position keyframes when supported.
    # ponytail: no full keyframe editor; just start/end X over the active voiceover range.
    dp_cfg = overlays.get("directoryProgress", {})
    vo_dur = voiceover.duration if voiceover else 0
    if dp_cfg.get("enabled") and dp_cfg.get("text") and vo_dur > 0:
        script.add_track(TrackType.text, "directory_progress")
        fs = font_size_to_jianying(max(8.0, min(80.0, float(dp_cfg.get("fontSize", 22) or 22))))
        style = TextStyle(size=fs, align=0, auto_wrapping=False)
        start_x = float(dp_cfg.get("startX", -0.35) or -0.35)
        end_x = float(dp_cfg.get("endX", 1.05) or 1.05)
        y = float(dp_cfg.get("y", 0.94) or 0.94)
        clip = ClipSettings(transform_x=(start_x - 0.5) * 2, transform_y=(y - 0.5) * 2)
        ds = TextSegment(
            str(dp_cfg.get("text", "")),
            timerange=trange(f"{voiceover_start_at}s", f"{vo_dur}s"),
            style=style,
            clip_settings=clip,
        )
        try:
            ds.add_keyframe(KeyframeProperty.position_x, "0s", (start_x - 0.5) * 2)
            ds.add_keyframe(KeyframeProperty.position_x, f"{vo_dur}s", (end_x - 0.5) * 2)
        except Exception:
            pass  # fallback: fixed editable text if this pyJianYingDraft version changes
        _add_jianying_text_segment(script, ds, "directory_progress")

    # 7. Save draft
    script.save()

    # 如果直接导出到剪映草稿目录，修正 draft_meta_info.json 的路径
    return draft_dir, tuple(dict.fromkeys(adapter_warnings))


def _add_jianying_text_segment(script, segment, track_name: str) -> None:
    """Add text and repair pyJianYingDraft's missing speed material registration."""
    script.add_segment(segment, track_name)
    materials = getattr(script, "materials", None)
    speeds = getattr(materials, "speeds", None)
    speed = getattr(segment, "speed", None)
    if isinstance(speeds, list) and speed is not None and speed not in speeds:
        speeds.append(speed)


def _lower_jianying_visual_segments(
    segments: list[dict], image_limit: float = 6.0,
) -> list[dict]:
    """Lower semantic clips to JianYing's physical still-image segment limit."""
    lowered = []
    for segment in segments:
        start = float(segment.get("start", 0) or 0)
        end = max(start, float(segment.get("end", start) or start))
        media_type = segment.get("type")
        if media_type == "video":
            lowered.append(dict(segment))
            continue
        cursor = start
        part = 0
        while cursor < end - 1e-6:
            part_end = min(cursor + image_limit, end)
            item = dict(segment)
            item["id"] = f"{segment.get('id', 'clip')}__jy{part}"
            item["start"], item["end"] = cursor, part_end
            item["_semanticOffset"] = round(cursor - start, 6)
            item["_semanticDuration"] = round(end - start, 6)
            lowered.append(item)
            cursor = part_end
            part += 1
    return lowered


def _audio_fade_seconds(track: dict, duration: float) -> tuple[float, float]:
    """Clamp fade-in/out so fade durations never exceed the audio segment length."""
    fade_in = max(0.0, float(track.get("fadeIn", 0.0) or 0.0))
    fade_out = max(0.0, float(track.get("fadeOut", 0.0) or 0.0))
    if duration <= 0:
        return 0.0, 0.0
    if fade_in + fade_out > duration:
        scale = duration / (fade_in + fade_out)
        fade_in *= scale
        fade_out *= scale
    return round(fade_in, 3), round(fade_out, 3)


def _sanitize_folder_name(name: str) -> str:
    """把项目名变成合法的文件夹名"""
    s = re.sub(r'[<>:"/\\|?*]', '_', name)
    s = re.sub(r'\s+', ' ', s).strip()
    return s or "untitled"


def _fix_meta_paths(draft_dir: Path, draft_name: str):
    """修正 draft_meta_info.json 中的路径字段"""
    meta_file = draft_dir / "draft_meta_info.json"
    if not meta_file.exists():
        return
    try:
        meta = json.loads(meta_file.read_text(encoding="utf-8"))
        meta["draft_fold_path"] = str(draft_dir.resolve()).replace("\\", "/")
        meta["draft_name"] = draft_name
        meta["draft_root_path"] = str(draft_dir.parent.resolve()).replace("\\", "/")
        meta_file.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass  # 不阻塞导出


def _rewrite_draft_media_paths(draft_dir: Path, old_root: Path, new_root: Path) -> None:
    """Rewrite staged media paths before the draft is atomically published."""
    content_file = draft_dir / "draft_content.json"
    if not content_file.exists():
        raise DraftMediaPathRewriteError(
            "failed to rewrite generated JianYing media paths: draft_content.json is missing"
        )

    old_root_text = str(old_root.resolve())
    old_prefixes = {old_root_text, old_root_text.replace("\\", "/")}
    new_root_text = str(new_root.resolve())

    def rewrite(value):
        if isinstance(value, str):
            for prefix in old_prefixes:
                if value == prefix:
                    return new_root_text
                if value.startswith(prefix + "\\") or value.startswith(prefix + "/"):
                    suffix = value[len(prefix):].lstrip("\\/")
                    return str(Path(new_root_text) / Path(suffix))
            return value
        if isinstance(value, list):
            return [rewrite(item) for item in value]
        if isinstance(value, dict):
            return {key: rewrite(item) for key, item in value.items()}
        return value

    try:
        payload = json.loads(content_file.read_text(encoding="utf-8"))
        rewritten = rewrite(payload)
        temp_file = content_file.with_name(
            f".{content_file.name}.videoforge-rewrite-{uuid4().hex}.tmp"
        )
        try:
            with temp_file.open("w", encoding="utf-8", newline="") as handle:
                json.dump(rewritten, handle, ensure_ascii=False, indent=4)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_file, content_file)
        finally:
            if temp_file.exists():
                temp_file.unlink()
    except DraftMediaPathRewriteError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DraftMediaPathRewriteError(
            "failed to rewrite generated JianYing media paths"
        ) from exc


def _fmt_time(seconds: float) -> str:
    """秒 → SRT 时间格式 HH:MM:SS,mmm"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds - int(seconds)) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _preprocess_media_with_adjustments(segments: list[dict], adjustments: dict, work_dir: Path) -> dict[str, str]:
    """用 FFmpeg 给素材预处理亮度/对比度，返回 {原路径: 调整后路径} 映射。"""
    brightness = float(adjustments.get("brightness", 0))
    contrast = float(adjustments.get("contrast", 1))
    if brightness == 0 and contrast == 1:
        return {}  # 无调整，不需要预处理

    mapping = {}
    eq_filter = f"eq=brightness={brightness}:contrast={contrast}"
    for seg in segments:
        src = seg.get("assetPath", "")
        if not src or src in mapping:
            continue
        src_path = Path(src)
        if not src_path.exists():
            continue
        # 图片直接加滤镜输出 PNG；视频用 -vf 输出 MP4
        is_video = src_path.suffix.lower() in {".mp4", ".mov", ".avi", ".mkv", ".webm"}
        out_name = f"_adj_{src_path.stem}{src_path.suffix if is_video else '.png'}"
        out_path = work_dir / out_name
        cmd = ["ffmpeg", "-y", "-i", str(src_path), "-vf", eq_filter]
        if is_video:
            cmd.extend(["-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p", "-an"])
        cmd.append(str(out_path))
        try:
            r = run_process(cmd, capture_output=True, timeout=60, encoding="utf-8", errors="replace")
            if r.returncode == 0 and out_path.exists():
                mapping[src] = str(out_path)
        except Exception:
            pass  # 预处理失败，用原文件
    return mapping
