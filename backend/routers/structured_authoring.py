from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import ValidationError

from models.project import Project, StructuredContent
from services.project_service import create_project, get_project, update_project
from shared.structured_import import MAX_SOURCE_CHARS, parse_structured_markdown
from shared.structured_presets import build_blocks, build_default_structured_variants

router = APIRouter(prefix="/api", tags=["structured-authoring"])


def _suggested_id(block_type: str | None, index: int, blocks: list[dict]) -> str | None:
    if not block_type:
        return None
    prefix = {"CTA_TAG": "cta", "SHORT_OUTRO": "short_outro", "BRIDGE_IN": "bridge_in", "BRIDGE_OUT": "bridge_out", "COMMENT_CTA": "comment_cta"}.get(block_type, block_type.lower())
    occurrence = sum(1 for b in blocks[:index] if b.get("type") == block_type) + 1
    return f"{prefix}_{occurrence:02d}"


def _episode_from_payload(data: dict) -> dict:
    episode = data.get("episode") or {}
    blocks = episode.get("blocks") or []
    variants = episode.get("variants") or []
    if not blocks and not variants:
        raise HTTPException(422, "episode must contain confirmed blocks and variants")
    try:
        content = StructuredContent(schemaVersion=1, episode={**episode, "blocks": blocks, "variants": variants, "bindings": episode.get("bindings") or []})
    except ValidationError as exc:
        raise HTTPException(422, str(exc)) from exc
    return content.model_dump(mode="python")


def _has_alignment(project: Project) -> bool:
    episode = ((project.structuredContent.model_dump() if project.structuredContent else {}).get("episode") or {})
    if episode.get("alignment"):
        return True
    if any((binding.get("audioSlice") if isinstance(binding, dict) else binding.audioSlice) is not None for binding in episode.get("bindings") or []):
        return True
    if any((subtitle.metadata or {}).get("generatedBy") == "fish_timestamp_alignment" for subtitle in project.subtitles):
        return True
    return any((voice.engine == "fish_audio" or voice.api == "fish_audio_timestamp") and voice.file for voice in project.audio.voiceovers)


@router.post("/structured/import/parse")
def parse_import(data: dict):
    text = data.get("text")
    if not isinstance(text, str) or not text.strip():
        raise HTTPException(422, "structured source text must not be empty")
    if len(text) > MAX_SOURCE_CHARS:
        raise HTTPException(413, f"structured source text exceeds {MAX_SOURCE_CHARS} characters")
    document = parse_structured_markdown(text)
    preview_blocks = build_blocks(list(document.sections))
    sections = []
    for index, section in enumerate(document.sections):
        sections.append({"index": index, "sourceHeading": section.source_heading, "detectedType": section.detected_type, "suggestedId": _suggested_id(section.detected_type, index, preview_blocks), "text": section.text, "sourceStartLine": section.source_start_line, "sourceEndLine": section.source_end_line, "warnings": list(section.warnings)})
    return {"title": document.title, "sections": sections, "unknownSectionCount": sum(s.detected_type is None for s in document.sections), "emptySectionCount": sum(not s.text.strip() for s in document.sections), "warnings": list(document.warnings)}


@router.post("/projects/structured")
def create_structured(data: dict):
    episode = _episode_from_payload(data)
    name = str(data.get("name") or episode["episode"].get("title") or "Structured Episode").strip()
    ratio = str((data.get("canvas") or {}).get("ratio") or "9:16")
    if ratio not in {"9:16", "16:9", "1:1", "4:5", "4:3"}:
        raise HTTPException(422, "unsupported canvas ratio")
    project = create_project(name, ratio, template_id=None)
    active_id = episode["episode"].get("activeVariantId")
    variant = next((v for v in episode["episode"].get("variants", []) if v["id"] == active_id), None)
    script = "\n\n".join(next((b["text"] for b in episode["episode"]["blocks"] if b["id"] == bid and b.get("enabled", True)), "") for bid in (variant or {}).get("blockIds", []))
    updated = update_project(project.id, {"templateId": "structured_episode", "structuredContent": episode, "script": script, "composition": None, "assets": [], "segments": [], "subtitles": [], "audio": {"voiceover": {}, "voiceovers": [], "bgm": {"tracks": []}, "sfx": []}})
    return updated.model_dump()


@router.get("/projects/{project_id}/structured/draft")
def get_draft(project_id: str):
    project = get_project(project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    if not project.structuredContent:
        raise HTTPException(409, "Project does not contain structuredContent")
    return {"projectId": project.id, "updatedAt": project.updated_at, "structuredContent": project.structuredContent.model_dump()}


@router.patch("/projects/{project_id}/structured/draft")
def update_draft(project_id: str, data: dict):
    project = get_project(project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    if not project.structuredContent:
        raise HTTPException(409, "Project does not contain structuredContent")
    if _has_alignment(project):
        raise HTTPException(409, "structured_alignment_exists")
    expected = data.get("expectedUpdatedAt")
    if expected is not None and expected != project.updated_at:
        return {"status": "conflict", "expectedUpdatedAt": expected, "actualUpdatedAt": project.updated_at}
    episode = project.structuredContent.model_dump(mode="python")["episode"]
    allowed = {"title", "topic", "symbol", "blocks", "variants", "activeVariantId"}
    if any(key not in allowed and key not in {"expectedUpdatedAt", "invalidateAlignment"} for key in data):
        raise HTTPException(422, "structured draft contains immutable fields")
    candidate = {**episode, **{key: data[key] for key in allowed if key in data}}
    try:
        validated = StructuredContent(schemaVersion=1, episode=candidate)
    except ValidationError as exc:
        raise HTTPException(422, str(exc)) from exc
    active = next((v for v in validated.episode.variants if v.id == validated.episode.activeVariantId), None)
    script = "\n\n".join(next((b.text for b in validated.episode.blocks if b.id == bid and b.enabled), "") for bid in (active.blockIds if active else []))
    updated = update_project(project_id, {"structuredContent": validated.model_dump(), "script": script})
    return {"projectId": updated.id, "updatedAt": updated.updated_at, "structuredContent": updated.structuredContent.model_dump()}
