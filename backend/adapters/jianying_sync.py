from copy import deepcopy
from pathlib import Path
import re
from typing import Any

def apply_draft_params_to_project(project: dict[str, Any], draft_params: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Apply readable JianYing draft params back to a VideoForge project dict."""
    updated = deepcopy(project)
    changes = {"segments": 0, "subtitles": 0}

    _sync_segment_params(updated, draft_params.get("videoSegments", []) or [], changes)
    _sync_subtitle_params(updated, draft_params.get("textSegments", []) or [], changes)

    return updated, changes


def select_draft_for_project(project: dict[str, Any], draft_root: Path) -> tuple[Path, str]:
    """Prefer the project's exported draft name; fall back to most recently modified draft."""
    if not draft_root.exists():
        raise FileNotFoundError(f"JianYing draft root not found: {draft_root}")

    safe_name = _sanitize_folder_name(project.get("name") or project.get("id") or "video")
    exact = draft_root / safe_name
    if (exact / "draft_content.json").exists():
        return exact, "project-name"

    candidates = [p for p in draft_root.iterdir() if p.is_dir() and (p / "draft_content.json").exists()]
    if not candidates:
        raise FileNotFoundError("No readable JianYing drafts found")
    return max(candidates, key=lambda p: (p / "draft_content.json").stat().st_mtime), "latest"


def _sync_segment_params(project: dict[str, Any], draft_segments: list[dict[str, Any]], changes: dict[str, int]) -> None:
    usable_draft_segments = [s for s in draft_segments if not _is_generated_color_asset(s.get("path", ""))]
    used: set[int] = set()
    for segment in project.get("segments", []) or []:
        if segment.get("type") == "black":
            continue
        match_idx = _match_draft_segment(segment, usable_draft_segments, used)
        if match_idx is None:
            continue
        used.add(match_idx)
        source = usable_draft_segments[match_idx]
        transform = dict(segment.get("transform") or {})
        scale = source.get("scaleX")
        if isinstance(scale, (int, float)):
            transform["scale"] = round(float(scale), 4)
        transform["x"] = round((float(source.get("transformX") or 0.0) / 2.0) + 0.5, 4)
        transform["y"] = round((float(source.get("transformY") or 0.0) / 2.0) + 0.5, 4)
        if source.get("rotation") is not None:
            transform["rotation"] = float(source.get("rotation") or 0.0)
        segment["transform"] = transform
        changes["segments"] += 1


def _sync_subtitle_params(project: dict[str, Any], text_segments: list[dict[str, Any]], changes: dict[str, int]) -> None:
    subtitle_sources = [s for s in text_segments if s.get("type") == "subtitle" and s.get("fontSize") is not None]
    if not subtitle_sources:
        return
    subtitles = project.get("subtitles", []) or []
    for idx, subtitle in enumerate(subtitles):
        source = subtitle_sources[min(idx, len(subtitle_sources) - 1)]
        style = dict(subtitle.get("style") or {})
        style["fontSize"] = round(float(source["fontSize"]) * 3.0, 2)
        style["position"] = _position_from_transform(source.get("transformX"), source.get("transformY"))
        subtitle["style"] = style
        changes["subtitles"] += 1


def _match_draft_segment(segment: dict[str, Any], draft_segments: list[dict[str, Any]], used: set[int]) -> int | None:
    asset_path = _norm_path(segment.get("assetPath", ""))
    asset_name = Path(asset_path).name.lower()
    for idx, draft_segment in enumerate(draft_segments):
        if idx in used:
            continue
        draft_path = _norm_path(draft_segment.get("path", ""))
        if asset_path and draft_path and (asset_path == draft_path or Path(draft_path).name.lower() == asset_name):
            return idx
    for idx, draft_segment in enumerate(draft_segments):
        if idx not in used:
            return idx
    return None


def _position_from_transform(x: Any, y: Any) -> str:
    fx = float(x or 0.0)
    fy = float(y or 0.0)
    horiz = min((("left", -0.78), ("center", 0.0), ("right", 0.78)), key=lambda item: abs(fx - item[1]))[0]
    vert = min((("top", -0.78), ("middle", 0.0), ("bottom", 0.78)), key=lambda item: abs(fy - item[1]))[0]
    return f"{vert}_{horiz}"


def _norm_path(path: str) -> str:
    return str(path or "").replace("\\", "/").lower()


def _is_generated_color_asset(path: str) -> bool:
    return "_vf_color_" in _norm_path(path)


def _sanitize_folder_name(name: str) -> str:
    s = re.sub(r'[<>:"/\\|?*]', "_", str(name))
    s = re.sub(r"\s+", " ", s).strip()
    return s or "untitled"
