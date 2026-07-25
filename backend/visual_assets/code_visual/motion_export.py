from __future__ import annotations

import math
import os
import shutil
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

from visual_assets.rasterizer import ResvgSvgRasterizer

SVG_NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG_NS)


def _ease(name: str, x: float) -> float:
    x = max(0.0, min(1.0, x))
    if name == "linear":
        return x
    if name == "easeOutCubic":
        return 1 - (1 - x) ** 3
    if name == "easeInOutSine":
        return -(math.cos(math.pi * x) - 1) / 2
    if name == "easeOutBack":
        c1 = 1.70158
        c3 = c1 + 1
        return 1 + c3 * (x - 1) ** 3 + c1 * (x - 1) ** 2
    if name == "easeInOutCubic":
        return 4 * x**3 if x < 0.5 else 1 - ((-2 * x + 2) ** 3) / 2
    return x


def _value(instruction: dict, t: float) -> float:
    start = float(instruction.get("start_time", 0) or 0)
    end = float(instruction.get("end_time", start) or start)
    from_value = float(instruction.get("from_value", 0) or 0)
    to_value = float(instruction.get("to_value", from_value) or from_value)
    if end <= start:
        return to_value
    if t <= start:
        return from_value
    if t >= end:
        return to_value
    p = _ease(str(instruction.get("easing") or "linear"), (t - start) / (end - start))
    return from_value + (to_value - from_value) * p


def _motions(plan: dict) -> list[dict]:
    return [
        *list(plan.get("actor_motions") or []),
        *list(plan.get("symbol_motions") or []),
        *list(plan.get("environment_motions") or []),
        *list(plan.get("camera_motions") or []),
    ]


def _theme_background(plan: dict) -> str:
    return "#f5f1e8" if plan.get("theme_mode") == "light" else "#090909"


def frame_svg(svg_text: str, motion_plan: dict, t: float, *, width: int, height: int) -> str:
    root = ET.fromstring(svg_text)
    background = ET.Element(
        f"{{{SVG_NS}}}rect",
        {"x": "0", "y": "0", "width": str(width), "height": str(height), "fill": _theme_background(motion_plan)},
    )
    root.insert(0, background)

    by_id = {element.attrib.get("id"): element for element in root.iter() if element.attrib.get("id")}
    state: dict[str, dict[str, float | None]] = {}
    for instruction in _motions(motion_plan):
        target_id = str(instruction.get("target_id") or "")
        if not target_id:
            continue
        target_state = state.setdefault(
            target_id,
            {"x": 0.0, "y": 0.0, "scale": 1.0, "rotation": 0.0, "opacity": None},
        )
        prop = str(instruction.get("property") or "")
        if prop in target_state:
            target_state[prop] = _value(instruction, t)

    cx, cy = width / 2, height / 2
    for target_id, target_state in state.items():
        element = by_id.get(target_id)
        if element is None:
            continue
        x = float(target_state.get("x") or 0)
        y = float(target_state.get("y") or 0)
        scale = float(target_state.get("scale") or 1)
        rotation = float(target_state.get("rotation") or 0)
        transform = f"translate({x:.4f} {y:.4f})"
        if rotation:
            transform += f" rotate({rotation:.4f} {cx:.4f} {cy:.4f})"
        if scale != 1:
            transform += f" translate({cx:.4f} {cy:.4f}) scale({scale:.6f}) translate({-cx:.4f} {-cy:.4f})"
        element.set("transform", transform)
        if target_state.get("opacity") is not None:
            element.set("opacity", f"{float(target_state['opacity']):.6f}")

    duration = max(0.1, float(motion_plan.get("duration", 1) or 1))
    reveal = min(1.0, max(0.0, t / (duration * 0.26)))
    if motion_plan.get("theme_mode") == "dark":
        scene = by_id.get("scene_root")
        if scene is not None:
            scene.set("opacity", f"{0.2 + 0.8 * reveal:.6f}")
    else:
        for element in root.iter():
            tag = element.tag.rsplit("}", 1)[-1]
            if tag in {"path", "line", "circle", "ellipse", "polygon", "polyline", "rect"} and element is not background:
                base = float(element.attrib.get("opacity", "1") or 1)
                element.set("opacity", f"{base * (0.08 + 0.92 * reveal):.6f}")

    return ET.tostring(root, encoding="unicode")


def render_motion_mp4(
    svg_path: Path,
    motion_plan: dict,
    mp4_path: Path,
    *,
    width: int = 1080,
    height: int = 1920,
    fps: int = 12,
) -> Path:
    rasterizer = ResvgSvgRasterizer()
    if not rasterizer.is_available():
        raise RuntimeError("resvg-py is required to render code visual motion")
    svg_text = svg_path.read_text(encoding="utf-8")
    duration = max(0.25, float(motion_plan.get("duration", 0) or 0))
    frame_count = max(2, int(math.ceil(duration * fps)))
    frame_dir = mp4_path.with_name(f".{mp4_path.stem}_frames")
    shutil.rmtree(frame_dir, ignore_errors=True)
    frame_dir.mkdir(parents=True, exist_ok=True)
    tmp_mp4 = mp4_path.with_name(f".{mp4_path.stem}.tmp.mp4")
    tmp_mp4.unlink(missing_ok=True)
    try:
        for index in range(frame_count):
            t = min(duration, index / fps)
            frame_svg_text = frame_svg(svg_text, motion_plan, t, width=width, height=height)
            frame_svg_path = frame_dir / f"{index:04d}.svg"
            frame_png_path = frame_dir / f"{index:04d}.png"
            frame_svg_path.write_text(frame_svg_text, encoding="utf-8")
            result = rasterizer.rasterize(frame_svg_path, frame_png_path, width, height)
            if not result.succeeded:
                raise RuntimeError(result.message or result.error_code or "frame rasterization failed")
        cmd = [
            "ffmpeg", "-hide_banner", "-y",
            "-framerate", str(fps),
            "-i", str(frame_dir / "%04d.png"),
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-r", str(fps),
            "-movflags", "+faststart",
            str(tmp_mp4),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if proc.returncode != 0 or not tmp_mp4.exists() or tmp_mp4.stat().st_size == 0:
            raise RuntimeError((proc.stderr or proc.stdout)[-1000:])
        os.replace(tmp_mp4, mp4_path)
        return mp4_path
    finally:
        tmp_mp4.unlink(missing_ok=True)
        shutil.rmtree(frame_dir, ignore_errors=True)
