import json
from pathlib import Path
from typing import Any


TIME_SCALE = 1_000_000


def parse_jianying_draft(draft_dir: Path | str) -> dict[str, Any]:
    """Read a JianYing draft_content.json and extract editable transform/text params."""
    root = Path(draft_dir)
    content_path = root / "draft_content.json"
    if not content_path.exists():
        raise FileNotFoundError(f"draft_content.json not found: {root}")

    data = json.loads(content_path.read_text(encoding="utf-8"))
    materials = data.get("materials", {}) if isinstance(data.get("materials"), dict) else {}
    video_materials = _material_index(materials.get("videos", []) + materials.get("images", []))
    text_materials = _material_index(materials.get("texts", []))

    video_segments: list[dict[str, Any]] = []
    text_segments: list[dict[str, Any]] = []
    for track in data.get("tracks", []) or []:
        track_type = track.get("type")
        for segment in track.get("segments", []) or []:
            if track_type == "video":
                video_segments.append(_parse_video_segment(segment, video_materials))
            elif track_type == "text":
                text_segments.append(_parse_text_segment(segment, text_materials))

    return {
        "draftPath": str(root),
        "videoSegments": video_segments,
        "textSegments": text_segments,
    }


def _material_index(items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(item.get("id")): item for item in items if item.get("id")}


def _parse_video_segment(segment: dict[str, Any], materials: dict[str, dict[str, Any]]) -> dict[str, Any]:
    material_id = str(segment.get("material_id", ""))
    material = materials.get(material_id, {})
    clip = segment.get("clip", {}) or {}
    scale = clip.get("scale", {}) or {}
    transform = clip.get("transform", {}) or {}
    uniform = segment.get("uniform_scale", {}) or {}
    timerange = segment.get("target_timerange", {}) or {}
    return {
        "id": segment.get("id", ""),
        "materialId": material_id,
        "path": material.get("path", material.get("local_material_id", "")),
        "start": _jy_time(timerange.get("start", 0)),
        "duration": _jy_time(timerange.get("duration", 0)),
        "scaleX": _num(scale.get("x"), 1.0),
        "scaleY": _num(scale.get("y"), 1.0),
        "uniformScale": _num(uniform.get("value"), None),
        "transformX": _num(transform.get("x"), 0.0),
        "transformY": _num(transform.get("y"), 0.0),
        "rotation": _num(clip.get("rotation"), 0.0),
    }


def _parse_text_segment(segment: dict[str, Any], materials: dict[str, dict[str, Any]]) -> dict[str, Any]:
    material_id = str(segment.get("material_id", ""))
    material = materials.get(material_id, {})
    content = _parse_text_content(material.get("content", ""))
    styles = content.get("styles", []) if isinstance(content.get("styles"), list) else []
    clip = segment.get("clip", {}) or {}
    scale = clip.get("scale", {}) or {}
    transform = clip.get("transform", {}) or {}
    timerange = segment.get("target_timerange", {}) or {}
    style_sizes = [_num(style.get("size"), None) for style in styles if isinstance(style, dict) and style.get("size") is not None]
    return {
        "id": segment.get("id", ""),
        "materialId": material_id,
        "type": material.get("type", ""),
        "text": content.get("text", ""),
        "start": _jy_time(timerange.get("start", 0)),
        "duration": _jy_time(timerange.get("duration", 0)),
        "fontSize": style_sizes[0] if style_sizes else None,
        "styleSizes": style_sizes,
        "scaleX": _num(scale.get("x"), 1.0),
        "scaleY": _num(scale.get("y"), 1.0),
        "transformX": _num(transform.get("x"), 0.0),
        "transformY": _num(transform.get("y"), 0.0),
    }


def _parse_text_content(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str) or not raw:
        return {}
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}


def _jy_time(value: Any) -> float:
    return round(_num(value, 0.0) / TIME_SCALE, 6)


def _num(value: Any, default: float | None) -> float | None:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
