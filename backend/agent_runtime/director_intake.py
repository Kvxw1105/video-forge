"""Compile VideoForge-owned inputs into a compact Director intake contract.

The Director never receives a writable project document.  This module reads the
existing project service and shared SRT parser, then produces an explicit,
serializable snapshot which can be persisted with a Director Run.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from agent.harness import ProductContextBuilder
from services.project_service import get_project, list_projects
from shared.srt import decode_srt, parse_srt, subtitles_to_transcript


INTAKE_VERSION = 1
MAX_PROMPT_SCRIPT_CHARS = 12_000
MAX_PROMPT_SUBTITLES = 160
_HARNESS = ProductContextBuilder()
_CONSTITUTION = (Path(__file__).resolve().parents[2] / "agent" / "harness" / "product-constitution.md").read_text(encoding="utf-8")


def list_project_intakes() -> list[dict[str, Any]]:
    """Return existing project choices enriched with non-mutating readiness facts."""
    choices: list[dict[str, Any]] = []
    for row in list_projects():
        project_id = str(row.get("id") or "")
        if not project_id:
            continue
        project = get_project(project_id)
        if project is None:
            continue
        choices.append({
            "id": project.id,
            "name": project.name,
            "createdAt": project.created_at,
            "updatedAt": project.updated_at,
            "subtitleCount": len(project.subtitles),
            "assetCount": len(project.assets),
            "hasScript": bool(project.script.strip()),
            "hasStructuredContent": project.structuredContent is not None,
        })
    return choices


def build_project_intake(project_id: str) -> dict[str, Any] | None:
    project = get_project(project_id)
    if project is None:
        return None
    subtitles = [_as_dict(item) for item in project.subtitles]
    transcript = subtitles_to_transcript(subtitles)
    source_script = project.script.strip() or transcript
    structured_content = _as_dict(project.structuredContent) if project.structuredContent is not None else None
    episode = structured_content.get("episode") if isinstance(structured_content, dict) else None
    intake = {
        "version": INTAKE_VERSION,
        "source": {"type": "project", "projectId": project.id, "projectName": project.name},
        "project": {
            "id": project.id,
            "name": project.name,
            "canvas": _as_dict(project.canvas),
            "templateId": project.templateId,
            "visualMode": project.visualMode,
            "updatedAt": project.updated_at,
        },
        "sourceScript": source_script,
        "subtitleTimeline": subtitles,
        "structuredContent": structured_content,
        "readiness": {
            "subtitleCount": len(subtitles),
            "assetCount": len(project.assets),
            "hasStructuredContent": structured_content is not None,
            "blockCount": len(episode.get("blocks") or []) if isinstance(episode, dict) else 0,
            "sceneCount": len(((episode or {}).get("visualPlan") or {}).get("scenes") or []) if isinstance(episode, dict) else 0,
        },
    }
    intake["harnessContext"] = _HARNESS.build(recipe_id="structured-knowledge-video", project=project.model_dump())
    return intake


def build_srt_intake(content: bytes, *, filename: str | None = None) -> dict[str, Any]:
    text = decode_srt(content)
    subtitles, ignored_count = parse_srt(text)
    transcript = subtitles_to_transcript(subtitles)
    intake = {
        "version": INTAKE_VERSION,
        "source": {"type": "srt_upload", "filename": filename or "subtitles.srt"},
        "project": None,
        "sourceScript": transcript,
        "subtitleTimeline": subtitles,
        "structuredContent": None,
        "readiness": {
            "subtitleCount": len(subtitles),
            "ignoredSubtitleBlocks": ignored_count,
            "durationSeconds": round(max(float(item["end"]) for item in subtitles), 3),
            "assetCount": 0,
            "hasStructuredContent": False,
            "blockCount": 0,
            "sceneCount": 0,
        },
    }
    intake["harnessContext"] = _HARNESS.build(recipe_id="structured-knowledge-video", project={"script": transcript, "subtitles": subtitles})
    return intake


def prompt_context(intake: dict[str, Any]) -> str:
    """Render bounded, deterministic input context for the Pi prompt."""
    harness_context = intake.get("harnessContext")
    if isinstance(harness_context, dict):
        # ProductContextBuilder is the authoritative bounded model context.
        import json
        return _CONSTITUTION + "\n\nVideoForge Product Harness context (read-only):\n" + json.dumps(harness_context, ensure_ascii=False, separators=(",", ":"))
    source = intake.get("source") if isinstance(intake.get("source"), dict) else {}
    project = intake.get("project") if isinstance(intake.get("project"), dict) else {}
    readiness = intake.get("readiness") if isinstance(intake.get("readiness"), dict) else {}
    script = str(intake.get("sourceScript") or "").strip()[:MAX_PROMPT_SCRIPT_CHARS]
    timeline = intake.get("subtitleTimeline") if isinstance(intake.get("subtitleTimeline"), list) else []
    caption_lines = []
    for item in timeline[:MAX_PROMPT_SUBTITLES]:
        if not isinstance(item, dict):
            continue
        caption_lines.append(f"[{item.get('start', 0):g}-{item.get('end', 0):g}] {str(item.get('text') or '').strip()}")
    source_label = source.get("projectName") or source.get("filename") or source.get("type") or "unknown"
    header = [
        "VideoForge structured intake (read-only snapshot):",
        f"- source: {source_label}",
        f"- projectId: {project.get('id') or source.get('projectId') or 'none'}",
        f"- subtitles: {readiness.get('subtitleCount', len(timeline))}; duration: {readiness.get('durationSeconds', 'project timeline')}s",
        f"- structured blocks: {readiness.get('blockCount', 0)}; scenes: {readiness.get('sceneCount', 0)}",
    ]
    if script:
        header.extend(("", "Source script:", script))
    if caption_lines:
        header.extend(("", "Subtitle timeline:", "\n".join(caption_lines)))
    return "\n".join(header)


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    model_dump = getattr(value, "model_dump", None)
    return model_dump() if callable(model_dump) else {}
