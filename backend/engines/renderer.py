"""
FFmpeg-based video preview renderer.

Duration rule: voiceover drives total duration.
Images cycle to fill voiceover time. If no voiceover, images use perImageDuration.
Supports: multi-BGM tracks, BGM trimming, cue-point-driven timing.
"""

import logging
from pathlib import Path
from process_utils import run as run_process

from shared.render_params import (
    subtitle_xy_exprs,
    ffmpeg_color_with_alpha,
    normalize_hex,
    overlay_to_ffmpeg_exprs,
)
from shared.timeline_compiler import compile_project_timeline
from shared.media_probe import probe_media_duration

logger = logging.getLogger(__name__)

VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".tiff"}

CHINESE_FONT_CANDIDATES = [
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\simhei.ttf",
    r"C:\Windows\Fonts\simsun.ttc",
    r"C:\Windows\Fonts\NotoSansCJK-Regular.ttc",
]


def _run_cmd(cmd: list, **kwargs):
    return run_process(cmd, **kwargs)


def _is_video(path: str) -> bool:
    return Path(path).suffix.lower() in VIDEO_EXTS


def get_drawtext_fontfile() -> str:
    for font_path in CHINESE_FONT_CANDIDATES:
        if Path(font_path).exists():
            return font_path
    return ""


def _drawtext_font_arg() -> str:
    fontfile = get_drawtext_fontfile()
    if not fontfile:
        return ""
    escaped = fontfile.replace("\\", "/").replace(":", r"\:")
    return f":fontfile='{escaped}'"


def render_preview(project: dict, output_path: Path, cue_points: list = None) -> Path:
    compiled = compile_project_timeline(project, cue_points, duration_resolver=probe_media_duration)
    for warning in compiled.warnings:
        logger.warning("Timeline compiler: %s", warning)
    segments = compiled.visual_segments()
    subtitles = list(compiled.subtitles)
    overlays = compiled.overlays
    canvas = compiled.canvas
    subtitle_enabled = overlays.get("subtitle_enabled", True) if overlays else True

    # Read adjustments (brightness: -1~1, contrast: 0~2)
    adj = overlays.get("adjustments", {}) if overlays else {}
    adj_brightness = float(adj.get("brightness", 0))
    adj_contrast = float(adj.get("contrast", 1))
    eq_filter = ""
    if adj_brightness != 0 or adj_contrast != 1:
        eq_filter = f"eq=brightness={adj_brightness}:contrast={adj_contrast}"

    w = canvas.get("width", 1080)
    h = canvas.get("height", 1920)
    bg = canvas.get("background", {})
    bg_color = bg.get("value", "#000000") if isinstance(bg, dict) else "#000000"
    bg_ffmpeg = bg_color.lstrip('#') if bg_color.startswith('#') else '000000'

    voiceover = compiled.voiceover_clips[0] if compiled.voiceover_clips else None
    voiceover_start_at = voiceover.start if voiceover else 0.0
    vo_path = voiceover.file if voiceover else ""
    vo_duration = voiceover.duration if voiceover else 0.0
    dur = compiled.total_duration

    # --- Collect unique media paths ---
    media_paths = []
    for seg in segments:
        mp = seg.get("assetPath", "")
        if mp and Path(mp).exists() and mp not in media_paths:
            media_paths.append(mp)

    # --- Pre-strip audio streams from video segments ---
    # Video files (.mov/.mp4) often contain audio tracks + cover art metadata.
    # These extra streams break FFmpeg concat and amix filters.
    # Strip them upfront: video-only, copy codec (fast).
    clean_media: dict[str, str] = {}  # original path -> cleaned path
    for mp in media_paths:
        if _is_video(mp):
            cleaned = _strip_video_audio(mp, output_path.parent)
            clean_media[mp] = cleaned if cleaned else mp
        else:
            clean_media[mp] = mp

    # --- Pre-mix ALL audio into a single WAV file ---
    # This avoids amix filter_complex issues with cover art in video segment inputs.
    vo_vol = voiceover.volume if voiceover else 1.0
    bgm_tracks = [clip.to_track() for clip in compiled.bgm_clips]

    # Prepare BGM/SFX: strip cover art, apply volume, timeline startAt, trim, fade
    prepared_bgm = _prepare_bgm(bgm_tracks, "", 0.3, output_path.parent)
    bgm_prepared_path = prepared_bgm[0] if prepared_bgm else None
    bgm_already_baked_vol = prepared_bgm[1] if prepared_bgm else 1.0  # volume already baked into file
    sfx_prepared_path = _prepare_multi_bgm(
        [clip.to_track() for clip in compiled.sfx_clips], output_path.parent
    )

    # Pre-mix voiceover + BGM + SFX into single WAV
    # Use bgm_already_baked_vol (1.0) since _prepare_bgm already applied volume to the file
    mixed_audio = _premix_audio(vo_path, vo_vol, bgm_prepared_path, bgm_already_baked_vol, dur, output_path.parent, voiceover_start_at=voiceover_start_at, sfx_path=sfx_prepared_path)
    has_mixed_audio = mixed_audio and mixed_audio.exists() and mixed_audio.stat().st_size > 0

    n_media = len(media_paths)
    n_audio = 1 if has_mixed_audio else 0

    render_segments = segments

    # --- Build FFmpeg command ---
    cmd = ["ffmpeg", "-y"]

    for seg in render_segments:
        mp = seg.get("assetPath", "")
        seg_dur = max(0.01, float(seg.get("end", 0)) - float(seg.get("start", 0)))
        if seg.get("type") == "black":
            color = str(seg.get("bgColor", bg_color)).lstrip('#') or bg_ffmpeg
            cmd.extend(["-f", "lavfi", "-i", f"color=c=0x{color}:s={w}x{h}:d={seg_dur}:r=30"])
            continue
        # Use cleaned (audio-stripped) path for video files
        input_path = clean_media.get(mp, mp)
        if _is_video(mp):
            cmd.extend(["-stream_loop", "-1", "-t", str(seg_dur), "-i", input_path])
        else:
            cmd.extend(["-loop", "1", "-t", str(seg_dur), "-i", input_path])

    total_inputs = len(render_segments)

    # Single pre-mixed audio input (avoids amix filter issues)
    if has_mixed_audio:
        cmd.extend(["-i", str(mixed_audio)])

    # --- Build filter_complex ---
    fc_parts = []

    # Build overlay drawtexts (title + watermark) — applied on top of everything
    overlay_drawtexts = _build_overlay_drawtexts(overlays, w, h, dur, voiceover_start_at, vo_duration)

    if total_inputs == 0:
        cmd.extend(["-f", "lavfi", "-i", f"color=c=0x{bg_ffmpeg}:s={w}x{h}:d={dur}:r=30"])
        lavfi_idx = total_inputs + n_audio
        drawtexts = _build_drawtexts(subtitles, subtitle_enabled, h, w, 0.0)
        chain = f"[{lavfi_idx}:v]"
        filters = [x for x in (drawtexts, overlay_drawtexts) if x]
        if filters:
            chain += ",".join(filters)
        else:
            chain += "null"
        chain += "[vout]"
        fc_parts.append(chain)
        cmd.extend(["-map", f"[vout]"])

    elif total_inputs == 1:
        seg0 = render_segments[0] if render_segments else {}
        xf = seg0.get("transform", {})
        sc = xf.get("scale", 0.85)
        fit = xf.get("fit", "contain")
        vf = _build_scale_filter(w, h, sc, fit, bg_ffmpeg)
        drawtexts = _build_drawtexts(subtitles, subtitle_enabled, h, w, 0.0)
        if drawtexts:
            vf += "," + drawtexts
        if overlay_drawtexts:
            vf += "," + overlay_drawtexts
        if eq_filter:
            vf += "," + eq_filter
        fc_parts.append(f"[0:v]{vf}[vout]")
        cmd.extend(["-map", "[vout]"])

    else:
        for i, seg in enumerate(render_segments):
            if seg.get("type") == "black":
                vf_base = f"format=yuv420p,setsar=1,scale={w}:{h}"
            else:
                xf = seg.get("transform", {})
                sc = xf.get("scale", 0.85)
                fit = xf.get("fit", "contain")
                vf_base = _build_scale_filter(w, h, sc, fit, bg_ffmpeg)
                if eq_filter:
                    vf_base += "," + eq_filter
            fc_parts.append(f"[{i}:v]{vf_base}[v{i}]")

        concat_in = "".join(f"[v{i}]" for i in range(total_inputs))
        fc_parts.append(f"{concat_in}concat=n={total_inputs}:v=1:a=0[vconcat]")

        drawtexts = _build_drawtexts(subtitles, subtitle_enabled, h, w, 0.0)
        chain = "[vconcat]"
        if drawtexts:
            chain += drawtexts
        if overlay_drawtexts:
            chain += "," + overlay_drawtexts
        chain += "[vout]"
        fc_parts.append(chain)
        cmd.extend(["-map", "[vout]"])

    # --- Audio filter chain ---
    audio_offset = total_inputs
    audio_out_label = None

    if has_mixed_audio:
        # Pre-mixed audio is already at correct volume and duration — just map it
        # No amix needed: voiceover + BGM were mixed in _premix_audio
        audio_out_label = "aout"
        # No filter_complex audio chain needed — use stream mapping directly

    if fc_parts:
        cmd.extend(["-filter_complex", ";".join(fc_parts)])

    if audio_out_label and has_mixed_audio:
        # Pre-mixed audio is input at index total_inputs
        cmd.extend(["-map", f"{total_inputs}:a", "-c:a", "aac", "-b:a", "128k"])

    cmd.extend(["-c:v", "libx264", "-preset", "fast", "-crf", "23", "-pix_fmt", "yuv420p", "-r", "25", "-movflags", "+faststart"])
    cmd.extend(["-t", str(dur)])
    cmd.append(str(output_path))

    logger.info("Render: %d source media -> %d timeline inputs, dur=%.1fs", n_media, total_inputs, dur)
    logger.info("FFmpeg cmd length: %d args", len(cmd))
    logger.info("FFmpeg cmd snippet: %s", " ".join(cmd[:20]) + " ...")

    result = _run_cmd(cmd, timeout=300)
    if result.returncode != 0:
        stderr_tail = result.stderr[-3000:] if result.stderr else "(empty)"
        logger.error("FFmpeg failed (rc=%d):\n%s", result.returncode, stderr_tail)
        # Show full stderr in error for debugging
        raise RuntimeError(f"FFmpeg failed (rc={result.returncode}):\n{stderr_tail}")

    if not output_path.exists() or output_path.stat().st_size == 0:
        raise RuntimeError("Render produced no output file")

    logger.info("Render OK: %s (%d bytes)", output_path, output_path.stat().st_size)
    return output_path


def _prepare_bgm(tracks: list[dict], single_file: str, single_volume: float, work_dir: Path,
                 fade_in: float = 0.0, fade_out: float = 0.0) -> tuple[str, float] | None:
    if tracks:
        path = _prepare_multi_bgm(tracks, work_dir)
        if path:
            return path, 1.0  # per-track volume is baked into prepared file
    if single_file and Path(single_file).exists():
        return _prepare_single_bgm(
            single_file, single_volume,
            trim_start=0.0, trim_end=0.0,
            fade_in=fade_in, fade_out=fade_out,
            work_dir=work_dir,
        )
    return None


def _prepare_single_bgm(
    track_path: str,
    volume: float,
    trim_start: float,
    trim_end: float,
    fade_in: float,
    fade_out: float,
    work_dir: Path,
) -> tuple[str, float]:
    """Prepare a single BGM file: trim, volume, fade, strip cover art."""
    prepared = work_dir / f"_bgm_clean_{Path(track_path).stem}.mp3"
    cmd = ["ffmpeg", "-y"]
    if trim_start > 0:
        cmd.extend(["-ss", str(trim_start)])
    cmd.extend(["-i", str(track_path)])
    cmd.extend(["-map", "0:a?"])

    if trim_end > trim_start:
        cmd.extend(["-t", str(trim_end - trim_start)])

    filters = [f"volume={volume}"]
    if fade_in > 0:
        filters.append(f"afade=t=in:st=0:d={fade_in}")

    if fade_out > 0:
        full_dur = probe_media_duration(track_path)
        actual_dur = max(0.0, full_dur - trim_start)
        if trim_end > trim_start:
            actual_dur = min(actual_dur, trim_end - trim_start)
        if actual_dur > fade_out:
            filters.append(f"afade=t=out:st={actual_dur - fade_out}:d={fade_out}")

    cmd.extend(["-af", ",".join(filters), str(prepared)])
    r = _run_cmd(cmd, timeout=30)
    if r.returncode == 0 and prepared.exists() and prepared.stat().st_size > 0:
        return str(prepared), 1.0
    logger.warning("Single BGM clean failed, using original: %s", r.stderr[-200:] if r.stderr else "")
    return track_path, volume


def _prepare_multi_bgm(tracks: list[dict], work_dir: Path) -> str:
    """Prepare BGM tracks with independent source trim and timeline startAt, then mix them."""
    parts = []
    for i, track in enumerate(tracks):
        track_path = track.get("file", "")
        if not track_path or not Path(track_path).exists():
            continue

        trim_start = float(track.get("trimStart", 0) or 0)
        trim_end = float(track.get("trimEnd", 0) or 0)
        start_at = max(0.0, float(track.get("startAt", 0) or 0))
        fade_in = float(track.get("fadeIn", 0) or 0)
        fade_out = float(track.get("fadeOut", 0) or 0)
        volume = max(0.0, float(track.get("volume", 0.3) or 0.3))

        part_path = work_dir / f"_bgm_part_{i:03d}.mp3"
        cmd = ["ffmpeg", "-y"]
        if trim_start > 0:
            cmd.extend(["-ss", str(trim_start)])
        cmd.extend(["-i", str(track_path)])
        cmd.extend(["-map", "0:a?"])
        if trim_end > trim_start:
            cmd.extend(["-t", str(trim_end - trim_start)])

        filters = [f"volume={volume}"]
        if fade_in > 0:
            filters.append(f"afade=t=in:st=0:d={fade_in}")
        if fade_out > 0:
            full_dur = probe_media_duration(track_path)
            actual_dur = max(0.0, full_dur - trim_start)
            if trim_end > trim_start:
                actual_dur = min(actual_dur, trim_end - trim_start)
            if actual_dur > fade_out:
                filters.append(f"afade=t=out:st={actual_dur - fade_out}:d={fade_out}")
        if start_at > 0:
            delay = int(start_at * 1000)
            filters.append(f"adelay={delay}|{delay}")

        cmd.extend(["-af", ",".join(filters), str(part_path)])
        r = _run_cmd(cmd, timeout=30)
        if r.returncode == 0 and part_path.exists() and part_path.stat().st_size > 0:
            parts.append(part_path)

    if not parts:
        return ""
    if len(parts) == 1:
        return str(parts[0])

    final_bgm = work_dir / "_bgm_mixed.mp3"
    cmd = ["ffmpeg", "-y"]
    for p in parts:
        cmd.extend(["-i", str(p)])
    inputs = "".join(f"[{i}:a]" for i in range(len(parts)))
    cmd.extend([
        "-filter_complex",
        f"{inputs}amix=inputs={len(parts)}:duration=longest:dropout_transition=0[out]",
        "-map", "[out]", str(final_bgm)
    ])
    r = _run_cmd(cmd, timeout=60)
    for p in parts:
        p.unlink(missing_ok=True)
    return str(final_bgm) if r.returncode == 0 and final_bgm.exists() else ""



def _build_drawtexts(subtitles: list, subtitle_enabled: bool, h: int, w: int, voiceover_start_at: float = 0.0) -> str:
    if not subtitle_enabled or not subtitles:
        return ""
    parts = []
    offset = max(0.0, float(voiceover_start_at or 0.0))
    font_arg = _drawtext_font_arg()
    for sub in subtitles:
        txt = sub.get("text", "").strip()
        if not txt:
            continue
        s = float(sub.get("start", 0) or 0) + offset
        e = float(sub.get("end", 0) or 0) + offset
        # Use fontSize directly as pixel size — canvas preview and FFmpeg share the same unit
        style = sub.get("style", {}) or {}
        fs = max(16, int(style.get("fontSize", 48)))
        position = style.get("position", "bottom_center")
        x_expr, y_expr = subtitle_xy_exprs(position, w, h)
        color = normalize_hex(style.get("color", "#ffffff"))
        opacity = float(style.get("opacity", 1.0) or 1.0)
        color_str = ffmpeg_color_with_alpha(color, opacity)
        stroke_color = normalize_hex(style.get("strokeColor", "#000000"))
        stroke_w = int(style.get("strokeWidth", 2) or 2)
        txt_esc = _escape_drawtext(txt)
        parts.append(
            f"drawtext=text='{txt_esc}'{font_arg}:fontsize={fs}:fontcolor={color_str}:"
            f"borderw={stroke_w}:bordercolor=0x{stroke_color}:"
            f"x={x_expr}:y={y_expr}:enable='between(t,{s},{e})'"
        )
    return ",".join(parts)


def _build_overlay_drawtexts(overlays: dict, w: int, h: int, duration: float, voiceover_start_at: float = 0.0, voiceover_duration: float = 0.0) -> str:
    """Build drawtext filters for title and watermark overlays."""
    if not overlays:
        return ""
    parts = []
    font_arg = _drawtext_font_arg()

    # Title
    title_cfg = overlays.get("title", {})
    if title_cfg.get("enabled") and title_cfg.get("text"):
        txt_esc = _escape_drawtext(title_cfg["text"])
        fs = max(16, int(title_cfg.get("fontSize", 48)))
        opacity = title_cfg.get("opacity", 1.0)
        color_hex = normalize_hex(title_cfg.get("color", "#ffffff"))
        tx = title_cfg.get("x", 0.5)
        ty = title_cfg.get("y", 0.08)
        x_expr, y_expr = overlay_to_ffmpeg_exprs(tx, ty)
        color_str = ffmpeg_color_with_alpha(color_hex, opacity)
        parts.append(
            f"drawtext=text='{txt_esc}'{font_arg}:fontsize={fs}:fontcolor={color_str}:"
            f"borderw=2:bordercolor=black@0.5:"
            f"x={x_expr}:y={y_expr}:enable='between(t,0,{duration})'"
        )

    # Watermark
    wm_cfg = overlays.get("watermark", {})
    if wm_cfg.get("enabled") and wm_cfg.get("text"):
        txt_esc = _escape_drawtext(wm_cfg["text"])
        fs = max(12, int(wm_cfg.get("fontSize", 24)))
        opacity = wm_cfg.get("opacity", 0.35)
        color_hex = normalize_hex(wm_cfg.get("color", "#ffffff"))
        wx = wm_cfg.get("x", 0.85)
        wy = wm_cfg.get("y", 0.92)
        x_expr, y_expr = overlay_to_ffmpeg_exprs(wx, wy)
        color_str = ffmpeg_color_with_alpha(color_hex, opacity)
        parts.append(
            f"drawtext=text='{txt_esc}'{font_arg}:fontsize={fs}:fontcolor={color_str}:"
            f"x={x_expr}:y={y_expr}:enable='between(t,0,{duration})'"
        )

    # Directory progress: moving bottom text over the active voiceover range.
    # ponytail: first version only implements marquee_text; line/highlight can reuse the same timing later.
    dp_cfg = overlays.get("directoryProgress", {})
    if dp_cfg.get("enabled") and dp_cfg.get("text") and voiceover_duration > 0:
        txt_esc = _escape_drawtext(str(dp_cfg.get("text", "")))
        fs = max(10, int(dp_cfg.get("fontSize", 22) or 22))
        opacity = float(dp_cfg.get("opacity", 0.72) or 0.72)
        color_hex = normalize_hex(dp_cfg.get("color", "#F4EBDD"))
        y = max(0.0, min(1.0, float(dp_cfg.get("y", 0.94) or 0.94)))
        sx = float(dp_cfg.get("startX", -0.35) or -0.35)
        ex = float(dp_cfg.get("endX", 1.05) or 1.05)
        start = max(0.0, float(voiceover_start_at or 0.0))
        end = start + float(voiceover_duration)
        x_expr = f"w*{sx}+((w*{ex})-(w*{sx}))*(t-{start})/{max(0.001, float(voiceover_duration))}"
        color_str = ffmpeg_color_with_alpha(color_hex, opacity)
        parts.append(
            f"drawtext=text='{txt_esc}'{font_arg}:fontsize={fs}:fontcolor={color_str}:"
            f"borderw=1:bordercolor=black@0.35:"
            f"x='{x_expr}':y=h*{y}-text_h/2:enable='between(t,{start},{end})'"
        )

    return ",".join(parts)


def _escape_drawtext(text: str) -> str:
    """Escape special characters for FFmpeg drawtext filter.
    FFmpeg drawtext uses single-quote text, with these escape rules:
      ' → '\\'' (close quote, escape, reopen)
      : \\ ; , % [ ] { } → use backslash
    """
    if not text:
        return ""
    # Escape backslashes first, then single quotes, then other special chars
    out = text.replace("\\", "\\\\")
    out = out.replace("'", "\\'")
    out = out.replace(":", "\\:")
    out = out.replace(";", "\\;")
    out = out.replace(",", "\\,")
    out = out.replace("%", "\\%")
    out = out.replace("[", "\\[")
    out = out.replace("]", "\\]")
    return out


def _premix_audio(vo_path: str, vo_vol: float, bgm_path: str, bgm_vol: float, target_dur: float, work_dir: Path, voiceover_start_at: float = 0.0, sfx_path: str = "") -> Path | None:
    """Pre-mix voiceover + BGM + SFX into a single WAV.

    This avoids amix filter_complex issues when video segment inputs contain
    cover art / metadata streams that confuse the amix filter.
    """
    has_vo = vo_path and Path(vo_path).exists()
    has_bgm = bgm_path and Path(bgm_path).exists()
    has_sfx = sfx_path and Path(sfx_path).exists()

    if not has_vo and not has_bgm and not has_sfx:
        return None

    mixed = work_dir / "_audio_mixed.wav"
    cmd = ["ffmpeg", "-y"]
    chains = []
    labels = []
    idx = 0

    if has_vo:
        cmd.extend(["-i", vo_path])
        delay = int(voiceover_start_at * 1000)
        chains.append(f"[{idx}:a]volume={vo_vol},adelay={delay}|{delay}[vo]")
        labels.append("[vo]")
        idx += 1
    if has_bgm:
        cmd.extend(["-i", bgm_path])
        chains.append(f"[{idx}:a]volume={bgm_vol}[bgm]")
        labels.append("[bgm]")
        idx += 1
    if has_sfx:
        cmd.extend(["-i", sfx_path])
        chains.append(f"[{idx}:a]volume=1.0[sfx]")
        labels.append("[sfx]")
        idx += 1

    if len(labels) == 1:
        chains.append(f"{labels[0]}atrim=0:{target_dur},apad[out]")
    else:
        chains.append(f"{''.join(labels)}amix=inputs={len(labels)}:duration=longest:dropout_transition=0,atrim=0:{target_dur},apad[out]")

    cmd.extend([
        "-t", str(target_dur + 5),
        "-filter_complex", ";".join(chains),
        "-map", "[out]",
        "-ar", "44100", "-ac", "2",
        str(mixed),
    ])

    r = _run_cmd(cmd, timeout=120)
    if r.returncode == 0 and mixed.exists() and mixed.stat().st_size > 0:
        return mixed

    logger.error("Audio premix failed: %s", r.stderr[-500:] if r.stderr else "(empty)")
    return None


def _strip_video_audio(video_path: str, work_dir: Path) -> str | None:
    """Strip audio streams + cover art from a video file, outputting a clean video-only file.

    Video files (.mov/.mp4) often contain:
    - Audio tracks (aistream)
    - Cover art / metadata streams (attachment)
    These break FFmpeg concat and amix filters.

    Returns the cleaned path, or None if stripping failed (caller falls back to original).
    """
    cleaned = work_dir / f"_vclean_{Path(video_path).stem}.mp4"
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-an",  # strip all audio streams
        "-map", "0:v?",  # only video streams (if any)
        "-c:v", "copy",  # fast, no re-encode
        str(cleaned),
    ]
    r = _run_cmd(cmd, timeout=120)
    if r.returncode == 0 and cleaned.exists() and cleaned.stat().st_size > 0:
        return str(cleaned)
    logger.warning("Video audio strip failed for %s, using original: %s", video_path,
                   r.stderr[-200:] if r.stderr else "")
    return None


def _build_scale_filter(w: int, h: int, scale: float = 0.85, fit: str = "contain", bg_ffmpeg: str = "000000") -> str:
    """Build FFmpeg scale+pad filter matching segment transform.

    contain: fit inside canvas, letterbox (default)
    cover: fill canvas, crop overflow
    stretch: fill canvas, distort
    """
    if fit == "cover":
        # Cover: fill canvas, crop excess
        return (
            f"scale='{int(w*scale)}:{int(h*scale)}':force_original_aspect_ratio=increase,"
            f"crop={w}:{h},setsar=1"
        )
    elif fit == "stretch":
        # Stretch: force exact canvas size (may distort)
        return f"scale={w}:{h},setsar=1"
    else:
        # Contain (default): fit inside, letterbox
        return (
            f"scale='min({int(w*scale)},iw)':'min({int(h*scale)},ih)':"
            f"force_original_aspect_ratio=decrease,"
            f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=0x{bg_ffmpeg},setsar=1"
        )
